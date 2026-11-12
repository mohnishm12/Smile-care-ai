from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from src.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_token(
    subject: str, expires_delta: timedelta, token_type: Literal["access", "refresh"]
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str) -> str:
    return _create_token(
        subject, timedelta(minutes=settings.jwt_access_token_expire_minutes), "access"
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject, timedelta(days=settings.jwt_refresh_token_expire_days), "refresh"
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
