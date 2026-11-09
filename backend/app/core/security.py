"""Security utilities: password hashing, JWT, token helpers."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.core import clock
from app.core.config import get_settings
from app.core.errors import UnauthorizedError

_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches hashed. Never raises — returns False on mismatch."""
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: str, role: str, token_version: int) -> str:
    """Create a signed HS256 JWT access token."""
    settings = get_settings()
    now_dt = clock.now()
    payload = {
        "sub": user_id,
        "role": role,
        "tv": token_version,
        "jti": str(uuid.uuid4()),
        "iat": now_dt,
        "exp": now_dt + timedelta(minutes=settings.JWT_ACCESS_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token. Raises UnauthorizedError on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "role", "tv", "exp", "iat"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired", code="TOKEN_EXPIRED")
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError(f"Invalid token: {exc}", code="TOKEN_INVALID")


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a token string."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_opaque_token() -> str:
    """Generate a 32-byte random opaque token as a hex string."""
    return os.urandom(32).hex()
