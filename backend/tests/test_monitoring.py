import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import monitoring
from app.db import ApiKey, Base, RequestLog, get_db
from app.main import app
from app.ratelimit import RateLimiter
from app.seed_demo import seed

NOW = datetime.now(timezone.utc)
ADMIN = {"X-Admin-Token": "adm"}


def row(minutes_ago, project="shop", ok=True, lat=100.0, cost=0.01, served="m2", fallback=False, attempts=None):
    return RequestLog(request_id="r", created_at=NOW - timedelta(minutes=minutes_ago), project=project, api_key_id=1,
                      policy_name="default", served_model=served if ok else None,
                      attempts=attempts or [{"model": served, "status": "ok" if ok else "failed"}],
                      success=ok, fallback_used=fallback, simulated=False, latency_ms=lat if ok else None,
                      total_ms=lat, input_tokens=100 if ok else None, output_tokens=10 if ok else None,
                      cost_usd=cost if ok else None, routing_reason="x")


@pytest.fixture
def mon(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("ADMIN_TOKEN", "adm")

    def override():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_db] = override
    yield {"c": TestClient(app), "engine": engine}
    app.dependency_overrides.clear()


def add(engine, *rows):
    with Session(engine) as s:
        s.add_all(rows)
        s.commit()


def test_summary_numbers_are_exact(mon):
    rows = [row(10 + i, lat=100.0 * (i + 1), fallback=i < 3) for i in range(10)] + [row(5, ok=False), row(6, ok=False)]
    add(mon["engine"], *rows)
    d = mon["c"].get("/monitor/summary?hours=1", headers=ADMIN).json()["summary"]
    assert d["requests"] == 12 and d["success_rate"] == pytest.approx(10 / 12, abs=1e-4)
    assert d["latency_ms"]["p50"] == 500.0 and d["latency_ms"]["p95"] == 1000.0 and d["latency_ms"]["n"] == 10
    assert d["fallback_rate"] == pytest.approx(3 / 12, abs=1e-4)
    assert d["cost_usd"]["total"] == pytest.approx(0.10) and d["cost_usd"]["projected_30_day"] == pytest.approx(0.10 * 24 * 30, rel=1e-3)


def test_window_excludes_old_rows_and_empty_is_safe(mon):
    add(mon["engine"], row(30), row(60 * 5))
    d = mon["c"].get("/monitor/summary?hours=1", headers=ADMIN).json()["summary"]
    assert d["requests"] == 1
    e = mon["c"].get("/monitor/summary?hours=1&project=nobody", headers=ADMIN).json()["summary"]
    assert e["requests"] == 0 and e["success_rate"] is None and e["latency_ms"]["p95"] is None


def test_model_health_and_alerts(mon):
    bad = [{"model": "m1", "status": "failed"}, {"model": "m2", "status": "ok"}]
    add(mon["engine"], *[row(i + 1, attempts=bad, fallback=True) for i in range(25)])
    res = mon["c"].get("/monitor/summary?hours=1", headers=ADMIN).json()
    models = {m["model"]: m for m in mon["c"].get("/monitor/models?hours=1", headers=ADMIN).json()["models"]}
    assert models["m1"]["status"] == "down" and models["m2"]["status"] == "healthy" and models["m2"]["requests_served"] == 25
    msgs = " | ".join(a["message"] for a in res["alerts"])
    assert "m1 is down" in msgs and "Fallback used" in msgs


def test_auth_and_project_scoping(mon):
    add(mon["engine"], row(5, project="shop"), row(5, project="shop"), row(5, project="other"))
    key = "sp_test"
    add(mon["engine"], ApiKey(name="k", project="shop", key_hash=hashlib.sha256(key.encode()).hexdigest()))
    c, k = mon["c"], {"X-API-Key": key}
    assert c.get("/monitor/summary").status_code == 401
    assert c.get("/monitor/summary", headers={"X-API-Key": "sp_bad"}).status_code == 401
    assert c.get("/monitor/summary", headers=k).json()["summary"]["requests"] == 2
    assert c.get("/monitor/summary?project=other", headers=k).status_code == 403
    assert c.get("/monitor/summary", headers=ADMIN).json()["summary"]["requests"] == 3
    assert c.get("/monitor/summary?project=other", headers=ADMIN).json()["summary"]["requests"] == 1
    assert len(c.get("/monitor/recent?limit=1", headers=k).json()["requests"]) == 1


def test_timeseries_covers_window_and_counts_everything(mon):
    add(mon["engine"], *[row(m) for m in (5, 20, 70, 130)], row(15, ok=False))
    pts = mon["c"].get("/monitor/timeseries?hours=3&bucket=hour", headers=ADMIN).json()["points"]
    assert sum(p["requests"] for p in pts) == 5 and sum(p["failures"] for p in pts) == 1 and len(pts) in (4, 5)


def test_seed_is_reproducible_labelled_and_realistic():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    fixed = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as s:
        assert seed(s, n=400, now=fixed) == 400
        rows = list(s.scalars(select(RequestLog)))
    assert all(r.simulated and r.project == "demo" and r.routing_reason == "seeded demo data" for r in rows)
    summ = monitoring.summarize(rows, 168)
    assert 0.9 < summ["success_rate"] <= 1.0 and 0 < summ["fallback_rate"] < 0.3
    with Session(create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})) as s2:
        Base.metadata.create_all(s2.get_bind())
        seed(s2, n=400, now=fixed)
        again = sorted(r.latency_ms or 0 for r in s2.scalars(select(RequestLog)))
    assert again == sorted(r.latency_ms or 0 for r in rows)


def test_rate_limiter_unit():
    rl = RateLimiter()
    assert [rl.check("a", 2, 60, now=t) for t in (0, 1)] == [0.0, 0.0]
    assert rl.check("a", 2, 60, now=2) == pytest.approx(58.0)
    assert rl.check("b", 2, 60, now=2) == 0.0          # separate key
    assert rl.check("a", 2, 60, now=61) == 0.0          # window slid
    assert rl.check("a", 0, 60, now=0) == 0.0           # 0 = disabled
