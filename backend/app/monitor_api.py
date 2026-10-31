import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import monitoring
from .db import ApiKey, RequestLog, get_db

router = APIRouter(prefix="/monitor", tags=["monitoring"])
MAX_ROWS = 50_000


def get_scope(x_admin_token: str | None = Header(default=None), x_api_key: str | None = Header(default=None),
              db: Session = Depends(get_db)) -> dict:
    """Admin sees every project; an API key sees only its own project."""
    expected = os.environ.get("ADMIN_TOKEN")
    if x_admin_token and expected and hmac.compare_digest(x_admin_token, expected):
        return {"admin": True, "project": None}
    if x_api_key:
        h = hashlib.sha256(x_api_key.encode()).hexdigest()
        key = db.scalar(select(ApiKey).where(ApiKey.key_hash == h, ApiKey.active == True))  # noqa: E712
        if key:
            return {"admin": False, "project": key.project}
    raise HTTPException(401, "provide a valid X-Admin-Token or X-API-Key")


def load(db: Session, scope: dict, project: str | None, hours: int):
    if scope["admin"]:
        proj = project
    else:
        if project and project != scope["project"]:
            raise HTTPException(403, "this API key can only view its own project")
        proj = scope["project"]
    until = datetime.now(timezone.utc)
    since = until - timedelta(hours=hours)
    q = select(RequestLog).where(RequestLog.created_at >= since)
    if proj:
        q = q.where(RequestLog.project == proj)
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
