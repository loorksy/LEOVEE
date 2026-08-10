import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import Settings

_password_hasher = PasswordHasher()


class PasswordError(ValueError):
    pass


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _password_hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(
    *,
    settings: Settings,
    user_id: str,
    session_id: str,
) -> tuple[str, int]:
    expires_in = settings.access_token_expire_seconds
    exp = datetime.now(UTC) + timedelta(seconds=expires_in)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, expires_in


def decode_access_token(settings: Settings, token: str) -> dict[str, str]:
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    sub = payload.get("sub")
    sid = payload.get("sid")
    if not isinstance(sub, str) or not isinstance(sid, str):
        raise jwt.InvalidTokenError("Invalid claims")
    return {"sub": sub, "sid": sid}
