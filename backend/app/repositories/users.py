"""All repository functions for FairNest — users, tokens, role grants."""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument

from app.core import clock as _clock


# ─────────────────────────── users ───────────────────────────────────────────

async def find_user_by_id(db, user_id: str) -> dict | None:
    return await db["users"].find_one({"_id": ObjectId(user_id)})


async def find_user_by_email(db, email: str) -> dict | None:
    return await db["users"].find_one({"email": email.strip().lower()})


async def find_user_by_roll_no(db, roll_no: str) -> dict | None:
    return await db["users"].find_one({"roll_no": roll_no.strip()})


async def find_user_by_identifier(db, identifier: str) -> dict | None:
    """Find by email OR roll_no."""
    q = {"$or": [
        {"email": identifier.strip().lower()},
        {"roll_no": identifier.strip()},
    ]}
    return await db["users"].find_one(q)


async def find_user_by_activation_token(db, token_hash: str) -> dict | None:
    return await db["users"].find_one({"activation_token_hash": token_hash})


async def find_user_by_reset_token(db, token_hash: str) -> dict | None:
    return await db["users"].find_one({"reset_token_hash": token_hash})


async def create_user(db, doc: dict) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now(), "updated_at": _clock.now()}
    r = await db["users"].insert_one(doc)
    return str(r.inserted_id)


async def update_user(db, user_id: str, update: dict, session=None) -> bool:
    update.setdefault("updated_at", _clock.now())
    r = await db["users"].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update},
        session=session,
    )
    return r.modified_count > 0


async def increment_failed_logins(db, user_id: str) -> int:
    doc = await db["users"].find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$inc": {"failed_logins": 1}, "$set": {"updated_at": _clock.now()}},
        return_document=ReturnDocument.AFTER,
    )
    return doc["failed_logins"] if doc else 0


async def reset_failed_logins(db, user_id: str, session=None):
    await db["users"].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"failed_logins": 0, "locked_until": None, "updated_at": _clock.now()}},
        session=session,
    )


async def list_users(
    db,
    skip: int = 0,
    limit: int = 50,
    role: str | None = None,
    status: str | None = None,
    search: str | None = None,
    hostel_ids: list[str] | None = None,
) -> list[dict]:
    import re
    q: dict = {}
    if role:
        q["role"] = role
    if status:
        q["status"] = status
    if hostel_ids is not None:
        q["hostel_ids"] = {"$in": hostel_ids}
    if search:
        esc = re.escape(search.strip())
        q["$or"] = [
            {"email": {"$regex": esc, "$options": "i"}},
            {"roll_no": {"$regex": esc, "$options": "i"}},
            {"name": {"$regex": esc, "$options": "i"}},
        ]
    cursor = db["users"].find(q).sort("created_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def bump_token_version(db, user_id: str, session=None):
    await db["users"].update_one(
        {"_id": ObjectId(user_id)},
        {"$inc": {"token_version": 1}, "$set": {"updated_at": _clock.now()}},
        session=session,
    )


# ─────────────────────────── refresh tokens ───────────────────────────────────

async def create_refresh_token(db, user_id: str, family_id: str,
                               token_hash: str, expires_at: datetime,
                               ip: str = "", user_agent: str = "") -> str:
    doc = {
        "_id": ObjectId(),
        "user_id": user_id,
        "family_id": family_id,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "revoked": False,
        "replaced_by": None,
        "ip": ip,
        "user_agent": user_agent,
        "created_at": _clock.now(),
    }
    r = await db["refresh_tokens"].insert_one(doc)
    return str(r.inserted_id)


async def find_refresh_token(db, token_hash: str) -> dict | None:
    return await db["refresh_tokens"].find_one({"token_hash": token_hash})


async def revoke_refresh_token(db, token_hash: str, replaced_by: str | None = None):
    await db["refresh_tokens"].update_one(
        {"token_hash": token_hash},
        {"$set": {"revoked": True, "replaced_by": replaced_by}},
    )


async def revoke_token_family(db, family_id: str):
    await db["refresh_tokens"].update_many(
        {"family_id": family_id},
        {"$set": {"revoked": True}},
    )


async def list_active_sessions(db, user_id: str) -> list[dict]:
    now = _clock.now()
    cursor = db["refresh_tokens"].find({
        "user_id": user_id,
        "revoked": False,
        "expires_at": {"$gt": now},
    }).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def revoke_session_by_family(db, user_id: str, family_id: str) -> bool:
    r = await db["refresh_tokens"].update_many(
        {"user_id": user_id, "family_id": family_id, "revoked": False},
        {"$set": {"revoked": True}},
    )
    return r.modified_count > 0


# ─────────────────────────── role grants ──────────────────────────────────────

async def create_role_grant(db, doc: dict) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now()}
    r = await db["role_grants"].insert_one(doc)
    return str(r.inserted_id)


async def find_pending_grant(db, email: str) -> dict | None:
    return await db["role_grants"].find_one({"email": email.lower(), "status": "PENDING"})


async def find_active_grant(db, email: str, role: str) -> dict | None:
    return await db["role_grants"].find_one(
        {"email": email.lower(), "role": role, "status": "ACTIVE"}
    )


async def apply_grant(db, grant_id: str, user_id: str, now: datetime, session=None):
    await db["role_grants"].update_one(
        {"_id": ObjectId(grant_id)},
        {"$set": {"status": "ACTIVE", "applied_user_id": user_id, "applied_at": now}},
        session=session,
    )


async def revoke_grant(db, grant_id: str, revoked_by: str, now: datetime):
    await db["role_grants"].update_one(
        {"_id": ObjectId(grant_id)},
        {"$set": {"status": "REVOKED", "revoked_by": revoked_by, "revoked_at": now}},
    )


async def list_role_grants(db, status: str | None = None, email: str | None = None) -> list[dict]:
    q: dict = {}
    if status:
        q["status"] = status
    if email:
        q["email"] = email.lower()
    return await db["role_grants"].find(q).to_list(length=200)
