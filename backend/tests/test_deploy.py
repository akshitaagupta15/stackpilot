import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db import ApiKey, Base, Policy, RequestLog, get_db, normalize_url
from app.main import app
from app.seed_demo import PROJECT, SEED_REASON, ensure_demo


def mem_engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e


def test_normalize_url():
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalize_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_ready_ok_and_503_when_db_down():
    e = mem_engine()

    def ok():
        with Session(e) as s:
            yield s

    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("db is down")
    app.dependency_overrides[get_db] = ok
    c = TestClient(app)
    try:
        assert c.get("/health").json() == {"status": "ok"}
        r = c.get("/ready")
        assert r.status_code == 200 and r.json()["database"] == "ok"
        app.dependency_overrides[get_db] = lambda: Broken()
        assert c.get("/ready").status_code == 503
        assert c.get("/health").status_code == 200          # liveness does not depend on the database
    finally:
        app.dependency_overrides.clear()


def test_cors_allows_only_configured_origin():
    c = TestClient(app)
    hdr = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-api-key,content-type"}
    ok = c.options("/gateway/chat", headers={"Origin": "http://localhost:3000", **hdr})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    bad = c.options("/gateway/chat", headers={"Origin": "https://evil.example", **hdr})
    assert "access-control-allow-origin" not in bad.headers


def test_ensure_demo_is_idempotent_refreshes_when_stale_and_keeps_other_rows():
    e = mem_engine()
    t0 = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    with Session(e) as s:
        a = ensure_demo(s, n=200, viewer_key="sp_demo_k", now=t0)
        assert a == {"seeded": 200, "key_created": True}
        s.add(RequestLog(request_id="visitor", project=PROJECT, api_key_id=1, policy_name="default", served_model="m",
                         attempts=[], success=True, fallback_used=False, simulated=True, total_ms=1.0,
                         routing_reason="a visitor's simulated call", created_at=t0))
        s.commit()
        assert ensure_demo(s, n=200, viewer_key="sp_demo_k", now=t0 + timedelta(hours=1)) == {"seeded": 0, "key_created": False}
        b = ensure_demo(s, n=200, viewer_key="sp_demo_k", now=t0 + timedelta(days=2))   # stale -> refreshed
        assert b["seeded"] == 200
        seeded = s.scalar(select(func.count()).select_from(RequestLog).where(RequestLog.routing_reason == SEED_REASON))
        assert seeded == 200 and s.scalar(select(func.count()).select_from(RequestLog).where(RequestLog.request_id == "visitor")) == 1
        assert s.scalars(select(ApiKey)).one().key_hash == hashlib.sha256(b"sp_demo_k").hexdigest()
        pol = s.scalars(select(Policy)).one()
        assert (pol.project, pol.name, pol.config["primary"]) == ("demo", "default", "demo/fail-model")


def test_startup_seeding_runs_only_when_enabled(monkeypatch):
    e = mem_engine()
    monkeypatch.setattr(main_module, "get_engine", lambda: e)
    monkeypatch.setenv("DEMO_SEED_N", "150")
    monkeypatch.setenv("DEMO_VIEWER_KEY", "sp_demo_boot")
    monkeypatch.delenv("SEED_DEMO_ON_START", raising=False)
    with TestClient(app):
        pass
    with Session(e) as s:
        assert s.scalar(select(func.count()).select_from(RequestLog)) == 0
    monkeypatch.setenv("SEED_DEMO_ON_START", "1")
    with TestClient(app):
        pass
    with Session(e) as s:
        assert s.scalar(select(func.count()).select_from(RequestLog)) == 150 and s.scalars(select(ApiKey)).one()


def test_startup_survives_seeding_failure(monkeypatch):
    def boom():
        raise RuntimeError("database not reachable")
    monkeypatch.setattr(main_module, "get_engine", boom)
    monkeypatch.setenv("SEED_DEMO_ON_START", "1")
    with TestClient(app) as c:                       # must still start
        assert c.get("/health").status_code == 200
