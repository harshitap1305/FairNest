"""Idempotency key helpers using MongoDB."""

from __future__ import annotations

from datetime import timedelta

from app.core import clock
from app.core.errors import ConflictError


async def get_idempotency(db, user_id: str, key: str) -> dict | None:
    """
    Retrieve an existing idempotency record for (user_id, key).
    Returns the stored response dict or None.
    """
    return await db["idempotency_keys"].find_one({"user_id": user_id, "key": key})


async def create_idempotency(
    db,
    user_id: str,
    key: str,
    request_hash: str,
    response: dict,
    status_code: int,
) -> None:
    """
    Store an idempotency record. TTL is enforced by a MongoDB TTL index on expires_at.
    Silently ignores DuplicateKeyError (record already exists).
    """
    from pymongo.errors import DuplicateKeyError

    now = clock.now()
    doc = {
        "user_id": user_id,
        "key": key,
        "request_hash": request_hash,
        "response": response,
        "status_code": status_code,
        "created_at": now,
        "expires_at": now + timedelta(hours=24),
    }
    try:
        await db["idempotency_keys"].insert_one(doc)
    except DuplicateKeyError:
        pass  # Already stored; that's fine


async def check_idempotency(
    db, user_id: str, key: str, request_hash: str
) -> dict | None:
    """
    Check for an existing idempotency record.
    - If found and request_hash matches: return stored response.
    - If found with different hash: raise ConflictError (same key, different body).
    - If not found: return None (proceed with operation).
    """
    record = await get_idempotency(db, user_id, key)
    if record is None:
        return None
    if record.get("request_hash") != request_hash:
        raise ConflictError(
            "Idempotency key reused with different request body",
            code="IDEMPOTENCY_CONFLICT",
        )
    return {"response": record["response"], "status_code": record["status_code"]}


async def store_idempotency(
    db,
    user_id: str,
    key: str,
    request_hash: str,
    response_body: dict,
    status_code: int,
) -> None:
    """Alias for create_idempotency for use in route handlers."""
    await create_idempotency(db, user_id, key, request_hash, response_body, status_code)
