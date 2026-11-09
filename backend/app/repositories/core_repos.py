"""Repositories for groups, memberships, applications, allotments, credits, notifications, audit."""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument

from app.core import clock as _clock


# ─────────────────────────── groups ──────────────────────────────────────────

async def create_group(db, doc: dict, session=None) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now(), "updated_at": _clock.now()}
    r = await db["groups"].insert_one(doc, session=session)
    return str(r.inserted_id)


async def get_group(db, group_id: str) -> dict | None:
    return await db["groups"].find_one({"_id": ObjectId(group_id)})


async def get_group_by_leader(db, cycle_id: str, leader_id: str) -> dict | None:
    return await db["groups"].find_one({
        "cycle_id": cycle_id,
        "leader_id": leader_id,
        "status": {"$ne": "DISBANDED"},
    })


async def update_group(db, group_id: str, update: dict, session=None) -> bool:
    update["updated_at"] = _clock.now()
    r = await db["groups"].update_one(
        {"_id": ObjectId(group_id)}, {"$set": update}, session=session
    )
    return r.modified_count > 0


# ─────────────────────────── memberships ─────────────────────────────────────

async def create_membership(db, doc: dict, session=None) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now(), "updated_at": _clock.now()}
    r = await db["memberships"].insert_one(doc, session=session)
    return str(r.inserted_id)


async def get_membership(db, membership_id: str) -> dict | None:
    return await db["memberships"].find_one({"_id": ObjectId(membership_id)})


async def get_accepted_membership(db, cycle_id: str, user_id: str) -> dict | None:
    return await db["memberships"].find_one(
        {"cycle_id": cycle_id, "user_id": user_id, "status": "ACCEPTED"}
    )


async def find_membership_by_user_group(db, group_id: str, user_id: str) -> dict | None:
    return await db["memberships"].find_one({"group_id": group_id, "user_id": user_id})


async def list_memberships_by_group(db, group_id: str) -> list[dict]:
    return await db["memberships"].find({"group_id": group_id}).to_list(length=10)


async def update_membership(db, membership_id: str, update: dict, session=None) -> bool:
    update["updated_at"] = _clock.now()
    r = await db["memberships"].update_one(
        {"_id": ObjectId(membership_id)}, {"$set": update}, session=session
    )
    return r.modified_count > 0


async def decline_other_invites(db, cycle_id: str, user_id: str,
                                except_group_id: str, session=None):
    """Decline all INVITED memberships for user in this cycle except the given group."""
    await db["memberships"].update_many(
        {
            "cycle_id": cycle_id,
            "user_id": user_id,
            "group_id": {"$ne": except_group_id},
            "status": "INVITED",
        },
        {"$set": {"status": "DECLINED", "updated_at": _clock.now()}},
        session=session,
    )


async def list_pending_invites_for_user(db, cycle_id: str, user_id: str) -> list[dict]:
    return await db["memberships"].find(
        {"cycle_id": cycle_id, "user_id": user_id, "status": "INVITED"}
    ).to_list(length=20)


# ─────────────────────────── applications ────────────────────────────────────

async def create_application(db, doc: dict, session=None) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now(), "updated_at": _clock.now()}
    r = await db["applications"].insert_one(doc, session=session)
    return str(r.inserted_id)


async def get_application(db, app_id: str) -> dict | None:
    return await db["applications"].find_one({"_id": ObjectId(app_id)})


async def get_application_by_group(db, cycle_id: str, group_id: str) -> dict | None:
    return await db["applications"].find_one({"cycle_id": cycle_id, "group_id": group_id})


async def update_application(db, app_id: str, update: dict, session=None) -> bool:
    update["updated_at"] = _clock.now()
    r = await db["applications"].update_one(
        {"_id": ObjectId(app_id)}, {"$set": update}, session=session
    )
    return r.modified_count > 0


async def list_submitted_by_cycle(db, cycle_id: str) -> list[dict]:
    return await db["applications"].find(
        {"cycle_id": cycle_id, "status": "SUBMITTED"}
    ).to_list(length=5000)


async def list_waitlisted_by_cycle(db, cycle_id: str) -> list[dict]:
    return await db["applications"].find(
        {"cycle_id": cycle_id, "status": "WAITLISTED"}
    ).sort("order_index", 1).to_list(length=5000)


async def list_allotted_by_cycle(db, cycle_id: str) -> list[dict]:
    return await db["applications"].find(
        {"cycle_id": cycle_id, "status": {"$in": ["ALLOTTED", "CONFIRMED"]}}
    ).to_list(length=5000)


async def mark_unallotted(db, cycle_id: str, session=None):
    """Mark remaining WAITLISTED apps as UNALLOTTED when cycle closes."""
    await db["applications"].update_many(
        {"cycle_id": cycle_id, "status": "WAITLISTED"},
        {"$set": {"status": "UNALLOTTED", "updated_at": _clock.now()}},
        session=session,
    )


# ─────────────────────────── allotments ──────────────────────────────────────

async def create_allotment(db, doc: dict, session=None) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now(), "updated_at": _clock.now()}
    r = await db["allotments"].insert_one(doc, session=session)
    return str(r.inserted_id)


async def get_allotment(db, allotment_id: str) -> dict | None:
    return await db["allotments"].find_one({"_id": ObjectId(allotment_id)})


async def get_active_allotment_for_application(db, cycle_id: str,
                                               application_id: str) -> dict | None:
    return await db["allotments"].find_one(
        {"cycle_id": cycle_id, "application_id": application_id, "is_active": True}
    )


async def get_latest_allotment_for_application(db, cycle_id: str,
                                               application_id: str) -> dict | None:
    """Return active allotment first, else the most recent historical allotment for this app."""
    active = await get_active_allotment_for_application(db, cycle_id, application_id)
    if active:
        return active
    rows = await db["allotments"].find(
        {"cycle_id": cycle_id, "application_id": application_id}
    ).sort("created_at", -1).limit(1).to_list(length=1)
    return rows[0] if rows else None


async def get_active_allotment_for_room(db, cycle_id: str, room_id: str) -> dict | None:
    return await db["allotments"].find_one(
        {"cycle_id": cycle_id, "room_id": room_id, "is_active": True}
    )


async def accept_member(db, allotment_id: str, user_id: str,
                        now: datetime, session=None) -> dict | None:
    """
    Atomically set members.$.accept_status = ACCEPTED for the matching PENDING member.
    Returns the updated document, or None if not found (expired, already answered, not a member).
    """
    doc = await db["allotments"].find_one_and_update(
        {
            "_id": ObjectId(allotment_id),
            "status": "HELD",
            "expires_at": {"$gt": now},
            "members": {"$elemMatch": {"user_id": user_id, "accept_status": "PENDING"}},
        },
        {
            "$set": {
                "members.$.accept_status": "ACCEPTED",
                "members.$.accepted_at": now,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    return doc


async def update_allotment(db, allotment_id: str, update: dict, session=None) -> bool:
    update["updated_at"] = _clock.now()
    r = await db["allotments"].update_one(
        {"_id": ObjectId(allotment_id)}, {"$set": update}, session=session
    )
    return r.modified_count > 0


async def list_expired_held(db, now: datetime) -> list[dict]:
    return await db["allotments"].find(
        {"status": "HELD", "expires_at": {"$lte": now}}
    ).to_list(length=500)


async def list_active_by_cycle(db, cycle_id: str) -> list[dict]:
    return await db["allotments"].find(
        {"cycle_id": cycle_id, "is_active": True}
    ).to_list(length=1000)


async def try_extend_grace(db, allotment_id: str, new_expires_at: datetime,
                           now: datetime) -> bool:
    """
    Single atomic operation: extend hold once if grace_used=False and a member is still PENDING.
    Returns True if the extension was applied.
    """
    r = await db["allotments"].update_one(
        {
            "_id": ObjectId(allotment_id),
            "status": "HELD",
            "grace_used": False,
            "members": {"$elemMatch": {"accept_status": "PENDING"}},
        },
        {"$set": {"grace_used": True, "expires_at": new_expires_at, "updated_at": now}},
    )
    return r.modified_count == 1


# ─────────────────────────── credits ─────────────────────────────────────────

async def get_credit_account(db, user_id: str) -> dict | None:
    return await db["credit_accounts"].find_one({"user_id": user_id})


async def create_credit_account(db, user_id: str, credits: int = 3) -> str:
    doc = {
        "_id": ObjectId(),
        "user_id": user_id,
        "credits": credits,
        "version": 0,
        "created_at": _clock.now(),
        "updated_at": _clock.now(),
    }
    r = await db["credit_accounts"].insert_one(doc)
    return str(r.inserted_id)


async def apply_credit_delta(db, user_id: str, delta: int,
                             c_min: int, c_max: int,
                             now: datetime, session=None):
    """Atomic clamped update using aggregation pipeline."""
    await db["credit_accounts"].update_one(
        {"user_id": user_id},
        [{"$set": {
            "credits": {"$min": [c_max, {"$max": [c_min, {"$add": ["$credits", delta]}]}]},
            "updated_at": now,
        }}],
        session=session,
    )


async def insert_ledger_entry(db, entry: dict, session=None) -> str:
    entry = {**entry, "_id": ObjectId(), "created_at": _clock.now()}
    r = await db["credit_ledger"].insert_one(entry, session=session)
    return str(r.inserted_id)


async def get_ledger(db, user_id: str, skip: int = 0, limit: int = 50) -> list[dict]:
    return await db["credit_ledger"].find(
        {"user_id": user_id}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)


# ─────────────────────────── notifications ────────────────────────────────────

async def create_notification(db, doc: dict, session=None) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now()}
    r = await db["notifications"].insert_one(doc, session=session)
    return str(r.inserted_id)


async def list_notifications(db, user_id: str, unread_only: bool = False,
                             limit: int = 50) -> list[dict]:
    q: dict = {"user_id": user_id}
    if unread_only:
        q["read"] = False
    return await db["notifications"].find(q).sort(
        "created_at", -1
    ).limit(limit).to_list(length=limit)


async def count_unread_notifications(db, user_id: str) -> int:
    return await db["notifications"].count_documents({"user_id": user_id, "read": False})


async def mark_notification_read(db, notification_id: str, user_id: str) -> bool:
    r = await db["notifications"].update_one(
        {"_id": ObjectId(notification_id), "user_id": user_id},
        {"$set": {"read": True}},
    )
    return r.modified_count > 0


# ─────────────────────────── audit ───────────────────────────────────────────

async def create_audit_log(db, doc: dict, session=None) -> str:
    doc = {**doc, "_id": ObjectId(), "ts": doc.get("ts", _clock.now())}
    r = await db["audit_logs"].insert_one(doc, session=session)
    return str(r.inserted_id)


async def list_audit_logs(db, actor_id: str | None = None,
                          target_type: str | None = None,
                          target_id: str | None = None,
                          action: str | None = None,
                          from_dt: datetime | None = None,
                          to_dt: datetime | None = None,
                          skip: int = 0, limit: int = 50) -> list[dict]:
    q: dict = {}
    if actor_id:
        q["actor_id"] = actor_id
    if target_type:
        q["target_type"] = target_type
    if target_id:
        q["target_id"] = target_id
    if action:
        q["action"] = action
    if from_dt or to_dt:
        q["ts"] = {}
        if from_dt:
            q["ts"]["$gte"] = from_dt
        if to_dt:
            q["ts"]["$lte"] = to_dt
    return await db["audit_logs"].find(q).sort(
        "ts", -1
    ).skip(skip).limit(limit).to_list(length=limit)


# ─────────────────────────── idempotency ─────────────────────────────────────

async def get_idempotency(db, user_id: str, key: str) -> dict | None:
    return await db["idempotency_keys"].find_one({"user_id": user_id, "key": key})


async def create_idempotency(db, user_id: str, key: str, request_hash: str,
                             response: dict, status_code: int):
    from datetime import timedelta
    doc = {
        "_id": ObjectId(),
        "user_id": user_id,
        "key": key,
        "request_hash": request_hash,
        "response": response,
        "status_code": status_code,
        "created_at": _clock.now(),
        "expires_at": _clock.now() + timedelta(hours=24),
    }
    try:
        await db["idempotency_keys"].insert_one(doc)
    except Exception:
        pass  # duplicate key — already stored
