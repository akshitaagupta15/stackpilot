import hashlib
import hmac
import math
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import measured
from .db import ApiKey, Policy, RequestLog, get_db
from .gateway import compatibility_problems, route
from .providers import Provider, get_provider
from .ratelimit import limiter

gateway_router = APIRouter(prefix="/gateway", tags=["gateway"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def require_admin(x_admin_token: str | None = Header(default=None)):
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(503, "Admin API is disabled: set the ADMIN_TOKEN environment variable.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "invalid admin token")


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    project: str = Field(min_length=1, max_length=100)


class PolicyIn(BaseModel):
    project: str = Field(min_length=1, max_length=100)
    name: str = Field(default="default", min_length=1, max_length=100)
    primary: str
    fallbacks: list[str] = []
    data_sensitivity: Literal["low", "high"] = "low"
    regions: list[str] = []
    require_structured_output: bool = False
    max_tokens: int = Field(default=800, ge=1, le=4000)


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=20000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=50)
    policy: str = "default"


@admin_router.post("/keys", dependencies=[Depends(require_admin)])
def create_key(body: KeyIn, db: Session = Depends(get_db)):
    plain = "sp_" + secrets.token_urlsafe(32)
    db.add(ApiKey(name=body.name, project=body.project, key_hash=_hash(plain)))
    db.commit()
    return {"api_key": plain, "project": body.project, "note": "Shown once. Only its hash is stored."}


@admin_router.post("/policies", dependencies=[Depends(require_admin)])
def upsert_policy(body: PolicyIn, db: Session = Depends(get_db)):
    profiles = measured.load_profiles(measured.DEFAULT_PROFILES)
    cfg = body.model_dump(exclude={"project", "name"})
    problems = {m: p for m in [body.primary, *body.fallbacks]
                if (p := compatibility_problems(profiles.get(m), cfg))}
    if problems:
        raise HTTPException(422, detail={"message": "policy lists models that violate its own constraints",
                                         "problems": problems})
    row = db.scalar(select(Policy).where(Policy.project == body.project, Policy.name == body.name))
    if row:
        row.config = cfg
    else:
        db.add(Policy(project=body.project, name=body.name, config=cfg))
    db.commit()
    return {"project": body.project, "name": body.name, "config": cfg}


@gateway_router.post("/chat")
def chat(req: ChatRequest, response: Response, x_api_key: str | None = Header(default=None),
         db: Session = Depends(get_db), provider: Provider = Depends(get_provider)):
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == _hash(x_api_key), ApiKey.active == True)) if x_api_key else None  # noqa: E712
    if key is None:
        raise HTTPException(401, "invalid API key")
    key_id, project = key.id, key.project
    per_min = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))
    wait = limiter.check(key_id, per_min)
    if wait:
        raise HTTPException(429, f"rate limit exceeded: {per_min} requests per minute",
                            headers={"Retry-After": str(math.ceil(wait))})
    daily = int(os.environ.get("DAILY_LIMIT", "1000"))
    if daily > 0:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        used = db.scalar(select(func.count()).select_from(RequestLog)
                         .where(RequestLog.api_key_id == key_id, RequestLog.created_at >= today))
        if used >= daily:
            raise HTTPException(429, f"daily limit of {daily} requests reached for this API key")
    pol = db.scalar(select(Policy).where(Policy.project == project, Policy.name == req.policy))
    if pol is None:
        raise HTTPException(404, f"policy '{req.policy}' not found for this project")
    cfg = dict(pol.config)

    profiles = measured.load_profiles(measured.DEFAULT_PROFILES)
    result = route(cfg, profiles, [m.model_dump() for m in req.messages], provider.call)
    rid = uuid.uuid4().hex[:16]
    db.add(RequestLog(request_id=rid, project=project, api_key_id=key_id, policy_name=req.policy,
                      served_model=result.served_model, attempts=result.attempts, success=result.ok,
                      fallback_used=result.fallback_used, simulated=provider.simulated,
                      latency_ms=result.latency_ms, total_ms=result.total_ms,
                      input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                      cost_usd=result.cost_usd, routing_reason=result.reason[:500]))
    db.commit()
    if not result.ok:
        raise HTTPException(502, headers={"X-Request-ID": rid},
                            detail={"message": result.reason, "attempts": result.attempts, "request_id": rid})
    response.headers["X-Request-ID"] = rid
    return {"request_id": rid, "text": result.text, "model_used": result.served_model,
            "fallback_used": result.fallback_used, "simulated": provider.simulated,
            "latency_ms": result.latency_ms,
            "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens},
            "cost_usd": result.cost_usd,
            "routing": {"reason": result.reason, "attempts": result.attempts}}
