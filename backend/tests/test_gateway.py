import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import measured
from app.db import Base, RequestLog, get_db
from app.main import app
from app.providers import Provider, get_provider, get_provider as real_get_provider

ADMIN = {"X-Admin-Token": "secret-admin"}
SECRET_PROMPT = "my-secret-customer-data-12345"


def prof(slug, **kw):
    p = {"slug": slug, "provider": slug.split("/")[0], "context_window": 32000, "structured_output": True,
         "regions": ["us"], "languages": ["en"], "data_policy": "no_training",
         "pricing_override": {"input_per_mtok": 1.0, "output_per_mtok": 2.0, "verified_on": "2026-10-27"}}
    p.update(kw)
    return p


def write_profiles(path, *profiles):
    path.write_text(json.dumps({"models": list(profiles)}), encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    pfile = tmp_path / "profiles.json"
    write_profiles(pfile, prof("a/primary"), prof("b/backup"))
    monkeypatch.setattr(measured, "DEFAULT_PROFILES", pfile)
    monkeypatch.setenv("ADMIN_TOKEN", "secret-admin")
    calls, behaviour = [], {}

    def fake(slug, msgs, max_tokens):
        calls.append(slug)
        return behaviour.get(slug) or {"text": "hello", "error": None, "latency_ms": 120.0,
                                       "input_tokens": 1000, "output_tokens": 100, "finish_reason": "stop"}

    def override_db():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_provider] = lambda: Provider(fake, False)
    yield {"client": TestClient(app), "engine": engine, "calls": calls, "behaviour": behaviour, "pfile": pfile}
    app.dependency_overrides.clear()


def setup_project(c, **policy):
    key = c.post("/admin/keys", json={"name": "t", "project": "shop"}, headers=ADMIN).json()["api_key"]
    body = {"project": "shop", "primary": "a/primary", "fallbacks": ["b/backup"], **policy}
    r = c.post("/admin/policies", json=body, headers=ADMIN)
    return key, r


def chat(c, key, text="hi"):
    return c.post("/gateway/chat", json={"messages": [{"role": "user", "content": text}]}, headers={"X-API-Key": key})


def test_admin_disabled_or_protected(env, monkeypatch):
    c = env["client"]
    assert c.post("/admin/keys", json={"name": "t", "project": "p"}).status_code == 401
    assert c.post("/admin/keys", json={"name": "t", "project": "p"}, headers={"X-Admin-Token": "nope"}).status_code == 401
    monkeypatch.delenv("ADMIN_TOKEN")
    assert c.post("/admin/keys", json={"name": "t", "project": "p"}, headers=ADMIN).status_code == 503


def test_success_path_logs_metadata_and_cost(env):
    c = env["client"]
    key, r = setup_project(c)
    assert r.status_code == 200
    res = chat(c, key)
    d = res.json()
    assert res.status_code == 200 and d["model_used"] == "a/primary" and not d["fallback_used"]
    assert d["cost_usd"] == pytest.approx((1000 * 1.0 + 100 * 2.0) / 1e6) and res.headers["x-request-id"] == d["request_id"]
    with Session(env["engine"]) as s:
        row = s.scalars(select(RequestLog)).one()
        assert row.success and row.project == "shop" and row.served_model == "a/primary"


def test_fallback_when_primary_fails(env):
    c = env["client"]
    key, _ = setup_project(c)
    env["behaviour"]["a/primary"] = {"text": "", "error": "HTTP 429: busy", "latency_ms": 10.0,
                                     "input_tokens": None, "output_tokens": None}
    d = chat(c, key).json()
    assert d["model_used"] == "b/backup" and d["fallback_used"] is True
    assert [a["status"] for a in d["routing"]["attempts"]] == ["failed", "ok"]
    assert env["calls"] == ["a/primary", "b/backup"]


def test_incompatible_fallback_is_never_called_fail_closed(env):
    c = env["client"]
    key, _ = setup_project(c, data_sensitivity="high")
    write_profiles(env["pfile"], prof("a/primary"), prof("b/backup", data_policy="may_train"))  # changes after policy creation
    env["behaviour"]["a/primary"] = {"text": "", "error": "timeout", "latency_ms": 9.0, "input_tokens": None, "output_tokens": None}
    res = chat(c, key)
    assert res.status_code == 502 and env["calls"] == ["a/primary"]
    assert any(a["status"] == "skipped" for a in res.json()["detail"]["attempts"])
    with Session(env["engine"]) as s:
        assert s.scalars(select(RequestLog)).one().success is False


def test_policy_creation_rejects_bad_models(env):
    c = env["client"]
    write_profiles(env["pfile"], prof("a/primary"), prof("b/backup", data_policy="may_train"))
    r = c.post("/admin/policies", json={"project": "shop", "primary": "a/primary", "fallbacks": ["b/backup", "x/unknown"],
                                        "data_sensitivity": "high"}, headers=ADMIN)
    assert r.status_code == 422 and set(r.json()["detail"]["problems"]) == {"b/backup", "x/unknown"}


def test_auth_policy_and_input_validation(env):
    c = env["client"]
    key, _ = setup_project(c)
    assert chat(c, "sp_wrong").status_code == 401
    assert c.post("/gateway/chat", json={"messages": [{"role": "user", "content": "x"}]}).status_code == 401
    r = c.post("/gateway/chat", json={"messages": [{"role": "user", "content": "x"}], "policy": "nope"}, headers={"X-API-Key": key})
    assert r.status_code == 404
    assert c.post("/gateway/chat", json={"messages": []}, headers={"X-API-Key": key}).status_code == 422
    assert c.post("/gateway/chat", json={"messages": [{"role": "hacker", "content": "x"}]}, headers={"X-API-Key": key}).status_code == 422


def test_prompts_and_keys_are_not_stored(env):
    c = env["client"]
    key, _ = setup_project(c)
    chat(c, key, SECRET_PROMPT)
    with Session(env["engine"]) as s:
        dump = json.dumps([{k: str(v) for k, v in r.__dict__.items() if not k.startswith("_")} for r in s.scalars(select(RequestLog))])
        assert SECRET_PROMPT not in dump and key not in dump
    from app.db import ApiKey
    with Session(env["engine"]) as s:
        assert s.scalars(select(ApiKey)).one().key_hash != key


def test_simulator_used_without_provider_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    p = real_get_provider()
    assert p.simulated and p.call("demo/fail-model", [{"role": "user", "content": "x"}], 10)["error"]
    assert p.call("demo/ok", [{"role": "user", "content": "x"}], 10)["error"] is None
    monkeypatch.setenv("OPENROUTER_API_KEY", "k"); monkeypatch.setenv("DEMO_MODE", "1")
    assert real_get_provider().simulated


def test_per_minute_rate_limit(env, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "2")
    c = env["client"]
    key, _ = setup_project(c)
    assert chat(c, key).status_code == 200 and chat(c, key).status_code == 200
    r = chat(c, key)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert len(env["calls"]) == 2          # the blocked request never reached the provider
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "0")   # 0 disables
    assert chat(c, key).status_code == 200


def test_daily_limit_counts_logged_requests(env, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "2")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "0")
    c = env["client"]
    key, _ = setup_project(c)
    chat(c, key); chat(c, key)
    r = chat(c, key)
    assert r.status_code == 429 and "daily" in r.json()["detail"] and len(env["calls"]) == 2
