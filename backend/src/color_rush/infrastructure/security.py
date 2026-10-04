from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from jwt import InvalidTokenError
from jwt import decode as jwt_decode
from jwt import encode as jwt_encode

from color_rush.domain.enums import AdminRole
from color_rush.domain.errors import AuthError


def _fernet(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret_key: str, payload: str) -> str:
    return _fernet(secret_key).encrypt(payload.encode("utf-8")).decode("ascii")


def decrypt_secret(secret_key: str, token: str) -> str:
    return _fernet(secret_key).decrypt(token.encode("ascii")).decode("utf-8")


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str, *, iterations: int = 120_000) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2${iterations}${salt}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iter_s, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iter_s))
    return hmac.compare_digest(derived.hex(), digest)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def create_access_token(
    *,
    secret_key: str,
    user_id: UUID,
    role: AdminRole,
    ttl_seconds: int,
    now: datetime | None = None,
) -> str:
    issued = now or datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "typ": "access",
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt_encode(payload, secret_key, algorithm="HS256")


def decode_access_token(secret_key: str, token: str) -> dict[str, Any]:
    return _decode_typed_token(secret_key, token, expected_type="access")


def create_overlay_ws_token(
    *,
    secret_key: str,
    ticket_id: UUID,
    game_id: UUID,
    session_id: UUID | None,
    ttl_seconds: int,
    now: datetime | None = None,
) -> str:
    issued = now or datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "sub": str(ticket_id),
        "game_id": str(game_id),
        "session_id": str(session_id) if session_id else None,
        "typ": "overlay_ws",
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt_encode(payload, secret_key, algorithm="HS256")


def decode_overlay_ws_token(secret_key: str, token: str) -> dict[str, Any]:
    return _decode_typed_token(secret_key, token, expected_type="overlay_ws")


def _decode_typed_token(secret_key: str, token: str, *, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt_decode(token, secret_key, algorithms=["HS256"])
    except InvalidTokenError as exc:
        raise AuthError("invalid or expired token") from exc
    if payload.get("typ") != expected_type:
        raise AuthError("invalid token type")
    return payload
