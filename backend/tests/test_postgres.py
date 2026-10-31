"""Runs only when TEST_DATABASE_URL points at a real Postgres (CI does this).
Local:  set TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/dbname"""
import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import measured
from app.db import Base, RequestLog, get_db, normalize_url
from app.main import app
from app.seed_demo import seed

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
ADMIN = {"X-Admin-Token": "pg-admin"}


@pytest.fixture
def pg(monkeypatch, tmp_path):
    engine = create_engine(normalize_url(URL), pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    pf = tmp_path / "profiles.json"
    prof = lambda slug: {"slug": slug, "provider": "demo", "context_window": 32000, "structured_output": True,
                         "regions": ["us"], "languages": ["en"], "data_policy": "no_training",
                         "pricing_override": {"input_per_mtok": 1.0, "output_per_mtok": 2.0, "verified_on": "2026-10-27"}}
    pf.write_text(json.dumps({"models": [prof("demo/fail-model"), prof("demo/backup")]}))
    monkeypatch.setattr(measured, "DEFAULT_PROFILES", pf)
    monkeypatch.setenv("ADMIN_TOKEN", "pg-admin")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def override():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_db] = override
    yield {"c": TestClient(app), "engine": engine}
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_gateway_flow_on_postgres(pg):
    c = pg["c"]
    key = c.post("/admin/keys", json={"name": "t", "project": "shop"}, headers=ADMIN).json()["api_key"]
    pol = {"project": "shop", "primary": "demo/fail-model", "fallbacks": ["demo/backup"]}
    assert c.post("/admin/policies", json=pol, headers=ADMIN).status_code == 200
    assert c.post("/admin/policies", json={**pol, "max_tokens": 500}, headers=ADMIN).status_code == 200   # upsert
    r = c.post("/gateway/chat", json={"messages": [{"role": "user", "content": "hi"}]}, headers={"X-API-Key": key})
    assert r.status_code == 200 and r.json()["model_used"] == "demo/backup" and r.json()["fallback_used"]
    with Session(pg["engine"]) as s:
        row = s.scalars(select(RequestLog)).one()
        assert row.attempts[0]["status"] == "failed" and row.created_at.tzinfo is not None


def test_monitoring_on_postgres(pg):
    with Session(pg["engine"]) as s:
        seed(s, n=300)
    c = pg["c"]
    d = c.get("/monitor/summary?hours=168", headers=ADMIN).json()["summary"]
    assert d["requests"] == 300 and d["latency_ms"]["p95"] > 0
    assert len(c.get("/monitor/models?hours=168", headers=ADMIN).json()["models"]) >= 2
    pts = c.get("/monitor/timeseries?hours=168&bucket=day", headers=ADMIN).json()["points"]
    assert sum(p["requests"] for p in pts) == 300
    assert c.get("/ready").json()["database"] == "ok"
