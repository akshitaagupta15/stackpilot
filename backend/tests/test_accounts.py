import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import measured
from app.db import Base, SessionRow, User, get_db
from app.main import app
from app.providers import Provider, get_provider

H = {"X-Requested-With": "stackpilot"}
PW = "correct horse battery"


def prof(slug):
    return {"slug": slug, "provider": slug.split("/")[0], "context_window": 32000, "structured_output": True,
            "regions": ["us"], "languages": ["en"], "data_policy": "no_training",
            "pricing_override": {"input_per_mtok": 1.0, "output_per_mtok": 2.0, "verified_on": "2026-10-31"}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    pf = tmp_path / "profiles.json"
    pf.write_text(json.dumps({"models": [prof("a/primary"), prof("b/backup")]}))
    monkeypatch.setattr(measured, "DEFAULT_PROFILES", pf)
    monkeypatch.setenv("COOKIE_SECURE", "0")        # the test client talks plain http

    def override():
        with Session(engine) as s:
            yield s
    fake = lambda slug, msgs, mt: {"text": "hi", "error": None, "latency_ms": 50.0, "input_tokens": 10,
                                   "output_tokens": 5, "finish_reason": "stop"}
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_provider] = lambda: Provider(fake, True)
    yield engine
    app.dependency_overrides.clear()


def signup(c, email="a@example.com", pw=PW):
    return c.post("/auth/signup", json={"email": email, "password": pw}, headers=H)


def new_user(email):
    c = TestClient(app)
    assert signup(c, email).status_code == 200
    return c


def test_signup_login_logout_flow_and_password_storage(env):
    c = TestClient(app)
    r = signup(c)
    assert r.status_code == 200 and r.json()["email"] == "a@example.com"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert c.get("/auth/me").json()["email"] == "a@example.com"
    with Session(env) as s:
        h = s.scalars(select(User)).one().password_hash
        assert h.startswith("$argon2") and PW not in h
    assert c.post("/auth/logout", headers=H).status_code == 200
    assert c.get("/auth/me").status_code == 401
    assert c.post("/auth/login", json={"email": "A@Example.com", "password": PW}, headers=H).status_code == 200
    assert c.get("/auth/me").status_code == 200


def test_validation_duplicates_and_uniform_login_errors(env):
    c = TestClient(app)
    assert signup(c, pw="short").status_code == 422
    assert signup(c, email="not-an-email").status_code == 422
    assert signup(c).status_code == 200
    assert signup(TestClient(app), email="A@EXAMPLE.COM").status_code == 409
    wrong = c.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password-1"}, headers=H)
    unknown = c.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"}, headers=H)
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()


def test_csrf_header_is_required_on_state_changing_routes(env):
    c = TestClient(app)
    assert c.post("/auth/signup", json={"email": "a@example.com", "password": PW}).status_code == 403
    signup(c)
    assert c.post("/account/projects", json={"name": "x"}).status_code == 403
    assert c.post("/auth/logout").status_code == 403


def test_login_is_rate_limited(env):
    c = TestClient(app)
    signup(c)
    bad = {"email": "a@example.com", "password": "wrong-password-1"}
    assert [c.post("/auth/login", json=bad, headers=H).status_code for _ in range(8)] == [401] * 8
    assert c.post("/auth/login", json={"email": "a@example.com", "password": PW}, headers=H).status_code == 429


def test_old_or_expired_sessions_do_not_work(env):
    c = TestClient(app)
    signup(c)
    token = c.cookies.get("sp_session")
    c.post("/auth/logout", headers=H)
    replay = TestClient(app, cookies={"sp_session": token})
    assert replay.get("/auth/me").status_code == 401
    c2 = TestClient(app)
    signup(c2, email="b@example.com")
    with Session(env) as s:
        row = s.scalars(select(SessionRow).order_by(SessionRow.id.desc())).first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        s.commit()
    assert c2.get("/auth/me").status_code == 401


def test_project_limits_and_isolation_between_users(env):
    a, b = new_user("a@example.com"), new_user("b@example.com")
    ids = [a.post("/account/projects", json={"name": n}, headers=H).json()["id"] for n in ("P1", "P2", "P3")]
    assert a.post("/account/projects", json={"name": "P4"}, headers=H).status_code == 409           # project cap
    assert b.post("/account/projects", json={"name": "P1"}, headers=H).status_code == 200            # same name, other user
    c = new_user("c@example.com")
    assert c.post("/account/projects", json={"name": "Dup"}, headers=H).status_code == 200
    assert c.post("/account/projects", json={"name": "Dup"}, headers=H).status_code == 409           # duplicate name, same user
    s2 = c.post("/account/projects", json={"name": "dup!"}, headers=H).json()["slug"]               # different name, same slug base
    assert s2 != c.get("/account/projects").json()[0]["slug"]
    assert b.get(f"/account/projects/{ids[0]}").status_code == 404                                  # not yours looks like missing
    assert b.post(f"/account/projects/{ids[0]}/keys", json={"name": "k"}, headers=H).status_code == 404
    assert len(a.get("/account/projects").json()) == 3 and len(b.get("/account/projects").json()) == 1
    assert TestClient(app).get("/account/projects").status_code == 401


def test_keys_policies_gateway_and_monitoring_end_to_end(env):
    a, b = new_user("a@example.com"), new_user("b@example.com")
    p = a.post("/account/projects", json={"name": "Shop"}, headers=H).json()
    pid, slug = p["id"], p["slug"]
    assert [m["slug"] for m in a.get("/account/models").json()] == ["a/primary", "b/backup"]
    assert TestClient(app).get("/account/models").status_code == 401

    bad = a.post(f"/account/projects/{pid}/policies", json={"primary": "x/unknown"}, headers=H)
    assert bad.status_code == 422
    ok = a.post(f"/account/projects/{pid}/policies", json={"primary": "a/primary", "fallbacks": ["b/backup"]}, headers=H)
    assert ok.status_code == 200

    key = a.post(f"/account/projects/{pid}/keys", json={"name": "server"}, headers=H).json()["api_key"]
    detail = a.get(f"/account/projects/{pid}").json()
    assert key not in json.dumps(detail) and detail["keys"][0]["active"] and detail["policies"][0]["name"] == "default"

    chat = lambda: TestClient(app).post("/gateway/chat", json={"messages": [{"role": "user", "content": "hi"}]}, headers={"X-API-Key": key})
    assert chat().status_code == 200
    assert a.get("/monitor/summary?hours=24").json()["summary"]["requests"] == 1                    # owner sees it
    assert a.get(f"/monitor/summary?hours=24&project={slug}").json()["summary"]["requests"] == 1
    assert b.get(f"/monitor/summary?project={slug}").status_code == 403                              # other user cannot
    assert b.get("/monitor/summary?hours=24").json()["summary"]["requests"] == 0

    assert a.delete(f"/account/projects/{pid}/keys/{detail['keys'][0]['id']}", headers=H).status_code == 200
    assert chat().status_code == 401                                                                  # revoked key stops working
    assert b.delete(f"/account/projects/{pid}/policies/default", headers=H).status_code == 404
    assert a.delete(f"/account/projects/{pid}/policies/default", headers=H).status_code == 200


def test_key_and_policy_caps(env):
    a = new_user("a@example.com")
    pid = a.post("/account/projects", json={"name": "Shop"}, headers=H).json()["id"]
    codes = [a.post(f"/account/projects/{pid}/keys", json={"name": f"k{i}"}, headers=H).status_code for i in range(6)]
    assert codes == [200] * 5 + [409]
    for i in range(5):
        assert a.post(f"/account/projects/{pid}/policies", json={"name": f"p{i}", "primary": "a/primary"}, headers=H).status_code == 200
    assert a.post(f"/account/projects/{pid}/policies", json={"name": "p5", "primary": "a/primary"}, headers=H).status_code == 409
    assert a.post(f"/account/projects/{pid}/policies", json={"name": "p0", "primary": "b/backup"}, headers=H).status_code == 200   # updating is allowed
