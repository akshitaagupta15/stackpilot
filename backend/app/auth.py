"""Password hashing and server-side sessions. The browser only ever holds a random cookie value."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import SessionRow, User
from .monitoring import utc

COOKIE_NAME = "sp_session"
SESSION_DAYS = 7
_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("not-a-real-password")      # lets us spend the same time when the email is unknown
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def normalize_email(email: str) -> str:
    e = email.strip().lower()
    if len(e) > 254 or not _EMAIL.match(e):
        raise ValueError("enter a valid email address")
    return e


def check_password_strength(password: str) -> str:
    if not 10 <= len(password) <= 128:
        raise ValueError("password must be 10 to 128 characters")
    return password


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_time(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessionRow(user_id=user_id, token_hash=_h(token),
                      expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
    db.commit()
    return token


def resolve_session(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = db.scalar(select(SessionRow).where(SessionRow.token_hash == _h(token)))
    if row is None:
        return None
    if utc(row.expires_at) < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(SessionRow).where(SessionRow.token_hash == _h(token)))
        db.commit()
