import hashlib
import os
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import measured
from .auth import (COOKIE_NAME, SESSION_DAYS, burn_time, check_password_strength, create_session, end_session,
                   hash_password, normalize_email, resolve_session, verify_password)
from .db import ApiKey, Policy, Project, User, get_db
from .gateway_api import PolicyBody, save_policy
from .ratelimit import limiter

MAX_PROJECTS, MAX_KEYS, MAX_POLICIES = 3, 5, 5


def csrf(x_requested_with: str | None = Header(default=None)):
    """Cross-site pages cannot add a custom header without a CORS preflight, which we do not allow."""
    if x_requested_with != "stackpilot":
        raise HTTPException(403, "missing CSRF header")


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    return xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")


def current_user(db: Session = Depends(get_db), sp_session: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> User:
    user = resolve_session(db, sp_session)
    if user is None:
        raise HTTPException(401, "not logged in")
    return user


def set_session_cookie(response: Response, token: str):
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/",
                        secure=os.environ.get("COOKIE_SECURE", "1") != "0")


class Credentials(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return normalize_email(v)


class SignupIn(Credentials):
    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        return check_password_strength(v)


def public(user: User) -> dict:
    return {"id": user.id, "email": user.email}


# ---------------------------------------------------------------- /auth
auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/signup", dependencies=[Depends(csrf)])
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if limiter.check(f"signup:{client_ip(request)}", 10, 3600):
        raise HTTPException(429, "too many sign-ups from this address; try again later")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "an account with this email already exists")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    set_session_cookie(response, create_session(db, user.id))
    return public(user)


@auth_router.post("/login", dependencies=[Depends(csrf)])
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    if limiter.check(f"login-email:{body.email}", 8, 900) or limiter.check(f"login-ip:{client_ip(request)}", 40, 900):
        raise HTTPException(429, "too many login attempts; wait a few minutes")
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        burn_time(body.password)
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "invalid email or password")
    set_session_cookie(response, create_session(db, user.id))
    return public(user)


@auth_router.post("/logout", dependencies=[Depends(csrf)])
def logout(response: Response, db: Session = Depends(get_db), sp_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    end_session(db, sp_session)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax",
                           secure=os.environ.get("COOKIE_SECURE", "1") != "0")
    return {"ok": True}


@auth_router.get("/me")
def me(user: User = Depends(current_user)):
    return public(user)


# ---------------------------------------------------------------- /account
account_router = APIRouter(prefix="/account", tags=["account"])
CurrentUser = Annotated[User, Depends(current_user)]


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def owned_project(db: Session, user: User, pid: int) -> Project:
    p = db.get(Project, pid)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "project not found")          # same answer for "missing" and "not yours"
    return p


def project_json(p: Project) -> dict:
    return {"id": p.id, "name": p.name, "slug": p.slug, "created_at": p.created_at.isoformat() if p.created_at else None}


@account_router.get("/models")
def models(user: CurrentUser):
    """Models a policy may use (from model_profiles.json)."""
    return [{"slug": s, "provider": p.get("provider"), "regions": p.get("regions", []), "data_policy": p.get("data_policy"),
             "structured_output": p.get("structured_output"), "free_tier": bool(p.get("free_tier", False))}
            for s, p in measured.load_profiles(measured.DEFAULT_PROFILES).items()]


@account_router.get("/projects")
def list_projects(user: CurrentUser, db: Session = Depends(get_db)):
    return [project_json(p) for p in db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.id))]


@account_router.post("/projects", dependencies=[Depends(csrf)])
def create_project(body: ProjectIn, user: CurrentUser, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name cannot be empty")
    if db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == user.id)) >= MAX_PROJECTS:
        raise HTTPException(409, f"you can have at most {MAX_PROJECTS} projects")
    if db.scalar(select(Project).where(Project.owner_id == user.id, Project.name == name)):
        raise HTTPException(409, "you already have a project with this name")
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "project"
    slug, n = f"u{user.id}-{base}", 1
    while db.scalar(select(Project).where(Project.slug == slug)):
        n += 1
        slug = f"u{user.id}-{base}-{n}"
    p = Project(owner_id=user.id, name=name, slug=slug)
    db.add(p)
    db.commit()
    return project_json(p)


@account_router.get("/projects/{pid}")
def project_detail(pid: int, user: CurrentUser, db: Session = Depends(get_db)):
    p = owned_project(db, user, pid)
    keys = db.scalars(select(ApiKey).where(ApiKey.project == p.slug).order_by(ApiKey.id))
    pols = db.scalars(select(Policy).where(Policy.project == p.slug).order_by(Policy.id))
    return {**project_json(p),
            "keys": [{"id": k.id, "name": k.name, "active": k.active, "created_at": k.created_at.isoformat()} for k in keys],
            "policies": [{"name": x.name, "config": x.config} for x in pols]}


@account_router.post("/projects/{pid}/keys", dependencies=[Depends(csrf)])
def create_key(pid: int, body: KeyIn, user: CurrentUser, db: Session = Depends(get_db)):
    p = owned_project(db, user, pid)
    active = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.project == p.slug, ApiKey.active == True))  # noqa: E712
    if active >= MAX_KEYS:
        raise HTTPException(409, f"at most {MAX_KEYS} active keys per project; revoke one first")
    plain = "sp_" + secrets.token_urlsafe(32)
    db.add(ApiKey(name=body.name.strip(), project=p.slug, key_hash=hashlib.sha256(plain.encode()).hexdigest()))
    db.commit()
    return {"api_key": plain, "note": "Shown once. Only its hash is stored, so it cannot be shown again."}


@account_router.delete("/projects/{pid}/keys/{kid}", dependencies=[Depends(csrf)])
def revoke_key(pid: int, kid: int, user: CurrentUser, db: Session = Depends(get_db)):
    p = owned_project(db, user, pid)
    k = db.get(ApiKey, kid)
    if k is None or k.project != p.slug:
        raise HTTPException(404, "key not found")
    k.active = False
    db.commit()
    return {"ok": True}


@account_router.post("/projects/{pid}/policies", dependencies=[Depends(csrf)])
def save_project_policy(pid: int, body: PolicyBody, user: CurrentUser, db: Session = Depends(get_db)):
    p = owned_project(db, user, pid)
    exists = db.scalar(select(Policy).where(Policy.project == p.slug, Policy.name == body.name))
    if not exists and db.scalar(select(func.count()).select_from(Policy).where(Policy.project == p.slug)) >= MAX_POLICIES:
        raise HTTPException(409, f"at most {MAX_POLICIES} policies per project")
    return {"name": body.name, "config": save_policy(db, p.slug, body)}


@account_router.delete("/projects/{pid}/policies/{name}", dependencies=[Depends(csrf)])
def delete_policy(pid: int, name: str, user: CurrentUser, db: Session = Depends(get_db)):
    p = owned_project(db, user, pid)
    row = db.scalar(select(Policy).where(Policy.project == p.slug, Policy.name == name))
    if row is None:
        raise HTTPException(404, "policy not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
