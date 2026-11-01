import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import monitoring
from .auth import COOKIE_NAME, resolve_session
from .db import ApiKey, Project, RequestLog, get_db

router = APIRouter(prefix="/monitor", tags=["monitoring"])
MAX_ROWS = 50_000


def get_scope(x_admin_token: str | None = Header(default=None), x_api_key: str | None = Header(default=None),
              sp_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
              db: Session = Depends(get_db)) -> dict:
    """Admin sees everything; an API key sees its project; a logged-in user sees their own projects."""
    expected = os.environ.get("ADMIN_TOKEN")
    if x_admin_token and expected and hmac.compare_digest(x_admin_token, expected):
        return {"admin": True, "projects": None}
    if x_api_key:
        h = hashlib.sha256(x_api_key.encode()).hexdigest()
        key = db.scalar(select(ApiKey).where(ApiKey.key_hash == h, ApiKey.active == True))  # noqa: E712
        if key:
            return {"admin": False, "projects": {key.project}}
    user = resolve_session(db, sp_session)
    if user:
        slugs = db.scalars(select(Project.slug).where(Project.owner_id == user.id))
        return {"admin": False, "projects": set(slugs)}
    raise HTTPException(401, "log in, or provide a valid X-Admin-Token or X-API-Key")


def load(db: Session, scope: dict, project: str | None, hours: int):
    if scope["admin"]:
        projs = {project} if project else None
    else:
        if project and project not in scope["projects"]:
            raise HTTPException(403, "you can only view your own projects")
        projs = {project} if project else scope["projects"]
    proj = next(iter(projs)) if projs and len(projs) == 1 else None
    until = datetime.now(timezone.utc)
    since = until - timedelta(hours=hours)
    q = select(RequestLog).where(RequestLog.created_at >= since)
    if projs is not None:
        q = q.where(RequestLog.project.in_(projs))
    rows = list(db.scalars(q.order_by(RequestLog.created_at.desc()).limit(MAX_ROWS)))
    return rows, since, until, proj


@router.get("/summary")
def summary(hours: int = Query(24, ge=1, le=720), project: str | None = None,
            scope: dict = Depends(get_scope), db: Session = Depends(get_db)):
    rows, since, until, proj = load(db, scope, project, hours)
    s = monitoring.summarize(rows, hours)
    return {"window_hours": hours, "project": proj or "all", "summary": s,
            "alerts": monitoring.alerts(s, monitoring.by_model(rows))}


@router.get("/models")
def models(hours: int = Query(24, ge=1, le=720), project: str | None = None,
           scope: dict = Depends(get_scope), db: Session = Depends(get_db)):
    rows, *_ = load(db, scope, project, hours)
    return {"window_hours": hours, "models": monitoring.by_model(rows)}


@router.get("/timeseries")
def timeseries(hours: int = Query(24, ge=1, le=720), bucket: Literal["hour", "day"] = "hour",
               project: str | None = None, scope: dict = Depends(get_scope), db: Session = Depends(get_db)):
    rows, since, until, _ = load(db, scope, project, hours)
    return {"window_hours": hours, "bucket": bucket, "points": monitoring.timeseries(rows, since, until, bucket)}


@router.get("/recent")
def recent(limit: int = Query(50, ge=1, le=200), hours: int = Query(24, ge=1, le=720),
           project: str | None = None, scope: dict = Depends(get_scope), db: Session = Depends(get_db)):
    rows, *_ = load(db, scope, project, hours)
    return {"requests": [{"request_id": r.request_id, "time": monitoring.utc(r.created_at).isoformat(),
                          "project": r.project, "served_model": r.served_model, "success": r.success,
                          "fallback_used": r.fallback_used, "latency_ms": r.latency_ms, "cost_usd": r.cost_usd,
                          "reason": r.routing_reason, "attempts": r.attempts} for r in rows[:limit]]}
