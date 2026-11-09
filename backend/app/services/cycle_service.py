"""Cycle service: shared lifecycle transitions, validation, and stats."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core import clock as _clock
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.fairness.engine import get_policy, group_weight
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo


# ─────────────────────────── state machine ───────────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT":               {"SCHEDULED", "APPLICATIONS_OPEN", "OPEN", "CANCELLED"},
    "SCHEDULED":           {"APPLICATIONS_OPEN", "OPEN", "CANCELLED"},
    "OPEN":                {"APPLICATIONS_CLOSED", "CANCELLED"},
    "APPLICATIONS_OPEN":   {"APPLICATIONS_CLOSED", "CANCELLED"},
    "APPLICATIONS_CLOSED": {"ALLOCATING", "APPLICATIONS_OPEN", "CANCELLED"},
    "ALLOCATING":          {"ALLOTMENT_ACTIVE", "CANCELLED"},
    "ALLOTMENT_ACTIVE":    {"CLOSED", "CANCELLED"},
    "CLOSED":              {"SETTLED"},
    "SETTLED":             set(),
    "CANCELLED":           set(),
}


def validate_cycle_transition(current_status: str, target_status: str) -> bool:
    """Return True when transitioning from *current_status* to *target_status* is legal."""
    return target_status in _VALID_TRANSITIONS.get(current_status, set())


def _parse_dt(val) -> datetime | None:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def serialize_cycle(doc: dict) -> dict:
    """Serialize cycle doc while hiding seed_secret until seed is revealed (R-ALLOC-2)."""
    if not doc:
        return doc
    r = {**doc}
    if "_id" in r:
        r["_id"] = str(r["_id"])
    revealed_statuses = ("ALLOTMENT_ACTIVE", "CLOSED", "SETTLED")
    if r.get("status") not in revealed_statuses:
        r.pop("seed_secret", None)
        r.pop("seed_revealed", None)
    else:
        if r.get("seed_secret") and not r.get("seed_revealed"):
            r["seed_revealed"] = r["seed_secret"]
    return r


# ─────────────────────────── shared lifecycle ops ────────────────────────────

async def open_cycle_impl(
    db,
    client,
    cycle_id: str,
    actor_id: str = "system",
    *,
    allowed_from: tuple[str, ...] = ("DRAFT", "SCHEDULED", "APPLICATIONS_OPEN_PENDING"),
) -> dict:
    """
    Open a cycle atomically:
    1. Generate seed_secret + sha256 commitment
    2. Snapshot eligible ACTIVE rooms (all or selected room_ids) into room_inventory
       (rejecting if any room is already in another live release -> ROOM_IN_LIVE_RELEASE)
    3. Transition cycle to APPLICATIONS_OPEN
    4. Notify students in scope and create an audit log
    """
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    if cycle["status"] not in allowed_from:
        raise ConflictError(
            f"Cycle must be {allowed_from} to open (current: {cycle['status']})",
            code="VALIDATION_ERROR",
        )

    hostel_id = cycle["hostel_id"]
    selected_room_ids: list[str] = cycle.get("room_ids") or []
    rooms = await cat_repo.list_rooms_by_hostel(db, hostel_id, status="ACTIVE")
    if selected_room_ids:
        selected_set = {str(rid) for rid in selected_room_ids}
        rooms = [r for r in rooms if str(r["_id"]) in selected_set]

    if not rooms:
        raise ValidationError("No ACTIVE rooms selected/available in this hostel to open cycle")

    seed_secret = os.urandom(32).hex()
    seed_commitment = hashlib.sha256(bytes.fromhex(seed_secret)).hexdigest()
    now = _clock.now()

    inventory_docs = [
        {
            "cycle_id": cycle_id,
            "room_id": str(room["_id"]),
            "hostel_id": room["hostel_id"],
            "floor_no": room["floor_no"],
            "capacity": int(room["capacity"]),
            "status": "AVAILABLE",
            "allotment_id": None,
            "is_live": True,
            "version": 0,
        }
        for room in rooms
    ]

    async def _do(session):
        # Double-check room availability in txn (inv_live_room_unique enforces atomicity too)
        room_ids = [d["room_id"] for d in inventory_docs]
        existing_live = await db["room_inventory"].find_one(
            {"room_id": {"$in": room_ids}, "is_live": True},
            session=session,
        )
        if existing_live:
            raise ConflictError(
                f"Room {existing_live['room_id']} is already part of a live release",
                code="ROOM_IN_LIVE_RELEASE",
            )
        try:
            await cat_repo.create_inventory_docs(db, inventory_docs, session=session)
        except DuplicateKeyError:
            raise ConflictError(
                "One or more selected rooms are already in a live release",
                code="ROOM_IN_LIVE_RELEASE",
            )

        update_fields = {
            "status": "APPLICATIONS_OPEN",
            "seed_secret": seed_secret,
            "seed_commitment": seed_commitment,
            "schedule_history": cycle.get("schedule_history", []) + [{
                "at": now,
                "by": actor_id,
                "action": "OPEN",
            }],
        }
        if not cycle.get("apply_open_at"):
            update_fields["apply_open_at"] = now
        await cat_repo.update_cycle(db, cycle_id, update_fields, session=session)

        await repo.create_audit_log(db, {
            "actor_id": actor_id,
            "role": "ADMIN" if actor_id != "system" else "SYSTEM",
            "action": "OPEN_CYCLE",
            "target_type": "cycle",
            "target_id": cycle_id,
            "before": {"status": cycle["status"]},
            "after": {"status": "APPLICATIONS_OPEN", "rooms_snapshotted": len(inventory_docs)},
            "request_id": "",
            "ip": "",
        }, session=session)

    async with client.start_session() as session:
        await session.with_transaction(_do)

    # Queue in-app notification for eligible hostel students (best-effort)
    students = await db["users"].find(
        {"role": "STUDENT", "status": "ACTIVE", "hostel_ids": hostel_id},
        {"_id": 1},
    ).to_list(length=5000)
    if students:
        notif_docs = [
            {
                "_id": ObjectId(),
                "user_id": str(s["_id"]),
                "type": "CYCLE_OPENED",
                "title": f"Applications Open: {cycle.get('name', 'Hostel Allotment')}",
                "body": "You can now form a group and submit your room preferences.",
                "read": False,
                "created_at": now,
            }
            for s in students
        ]
        await db["notifications"].insert_many(notif_docs)

    return {"seed_commitment": seed_commitment, "rooms_snapshotted": len(inventory_docs)}


async def close_window_impl(
    db,
    client,
    cycle_id: str,
    actor_id: str = "system",
) -> dict:
    """
    Close application window (`APPLICATIONS_OPEN` -> `APPLICATIONS_CLOSED`):
    - Lock groups in the cycle
    - Snapshot credits, compute real weight & accessibility tier (0 if any verified member)
      on every SUBMITTED application
    """
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")

    policy = get_policy(cycle.get("policy", {}))
    c_init = policy.get("c_init", 3)
    gw_policy = policy.get("group_weight_policy", "MEAN")
    now = _clock.now()

    async def _do(session):
        moved = await cat_repo.transition_cycle_status(
            db, cycle_id, "APPLICATIONS_OPEN", "APPLICATIONS_CLOSED", session=session
        )
        if not moved:
            raise ConflictError("Cycle is not open", code="WINDOW_NOT_OPEN")

        # Lock active groups for this cycle
        await db["groups"].update_many(
            {"cycle_id": cycle_id, "status": {"$in": ["FORMING", "READY", "SUBMITTED"]}},
            {"$set": {"status": "LOCKED", "updated_at": now}},
            session=session,
        )

        # Snapshot credits and tier onto all SUBMITTED applications
        apps = await db["applications"].find(
            {"cycle_id": cycle_id, "status": "SUBMITTED"}, session=session
        ).to_list(length=5000)

        for app in apps:
            member_ids = app.get("member_ids", [])
            member_credits: list[int] = []
            member_rows: list[dict] = []
            has_accessibility = False
            for uid in member_ids:
                acct = await db["credit_accounts"].find_one({"user_id": uid}, session=session)
                c = acct["credits"] if acct else c_init
                member_credits.append(c)
                member_rows.append({"user_id": uid, "credits": c})
                u = await db["users"].find_one({"_id": ObjectId(uid)}, {"accessibility_verified": 1}, session=session)
                if u and u.get("accessibility_verified"):
                    has_accessibility = True

            w = group_weight(member_credits, gw_policy)
            tier = 0 if has_accessibility else 1
            snapshot = {
                "members": member_rows,
                "group_policy": gw_policy,
                "weight": w,
            }
            await db["applications"].update_one(
                {"_id": app["_id"]},
                {"$set": {
                    "credit_snapshot": snapshot,
                    "weight": w,
                    "tier": tier,
                    "updated_at": now,
                }},
                session=session,
            )

        await repo.create_audit_log(db, {
            "actor_id": actor_id,
            "role": "ADMIN" if actor_id != "system" else "SYSTEM",
            "action": "CLOSE_WINDOW",
            "target_type": "cycle",
            "target_id": cycle_id,
            "before": {"status": "APPLICATIONS_OPEN"},
            "after": {"status": "APPLICATIONS_CLOSED", "snapshotted_apps": len(apps)},
            "request_id": "",
            "ip": "",
        }, session=session)

        return {"message": "Application window closed", "applications_locked": len(apps)}

    async with client.start_session() as session:
        return await session.with_transaction(_do)


async def schedule_cycle_impl(
    db,
    cycle_id: str,
    apply_open_at_raw,
    apply_close_at_raw,
    actor_id: str,
) -> dict:
    """Schedule a DRAFT/SCHEDULED cycle window (`R-RLS-4` minimum window check)."""
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    if cycle["status"] not in ("DRAFT", "SCHEDULED"):
        raise ConflictError("Only DRAFT or SCHEDULED cycles can be scheduled", code="VALIDATION_ERROR")

    open_dt = _parse_dt(apply_open_at_raw)
    close_dt = _parse_dt(apply_close_at_raw)
    if not open_dt or not close_dt:
        raise ValidationError("apply_open_at and apply_close_at are required")

    settings = get_settings()
    now = _clock.now()
    if open_dt < now - timedelta(minutes=1):
        raise ValidationError("apply_open_at cannot be in the past")
    min_delta = timedelta(minutes=settings.MIN_WINDOW_MINUTES)
    if (close_dt - open_dt) < min_delta:
        raise ValidationError(
            f"Application window must be at least {settings.MIN_WINDOW_MINUTES} minutes"
        )

    await cat_repo.update_cycle(db, cycle_id, {
        "status": "SCHEDULED",
        "apply_open_at": open_dt,
        "apply_close_at": close_dt,
        "schedule_history": cycle.get("schedule_history", []) + [{
            "at": now,
            "by": actor_id,
            "action": "SCHEDULE",
            "apply_open_at": open_dt,
            "apply_close_at": close_dt,
        }],
    })
    return serialize_cycle(await cat_repo.get_cycle(db, cycle_id))


async def extend_window_impl(db, cycle_id: str, new_close_raw, reason: str, actor_id: str) -> dict:
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle or cycle["status"] != "APPLICATIONS_OPEN":
        raise ConflictError("Cycle must be APPLICATIONS_OPEN to extend", code="WINDOW_EXTEND_INVALID")
    new_close = _parse_dt(new_close_raw)
    if not new_close:
        raise ValidationError("new_close_at required")
    now = _clock.now()
    current_close = _parse_dt(cycle.get("apply_close_at")) or now
    if new_close <= current_close or new_close <= now:
        raise ConflictError(
            "New close time must be later than current close time and in the future",
            code="WINDOW_EXTEND_INVALID",
        )
    await cat_repo.update_cycle(db, cycle_id, {
        "apply_close_at": new_close,
        "schedule_history": cycle.get("schedule_history", []) + [{
            "at": now,
            "by": actor_id,
            "action": "EXTEND",
            "apply_close_at": new_close,
            "reason": reason,
        }],
    })
    await repo.create_audit_log(db, {
        "actor_id": actor_id,
        "role": "ADMIN",
        "action": "EXTEND_WINDOW",
        "target_type": "cycle",
        "target_id": cycle_id,
        "before": {"apply_close_at": str(current_close)},
        "after": {"apply_close_at": str(new_close), "reason": reason},
        "request_id": "",
        "ip": "",
    })
    return serialize_cycle(await cat_repo.get_cycle(db, cycle_id))


async def reopen_cycle_impl(
    db, cycle_id: str, new_close_raw, reason: str, actor_id: str
) -> dict:
    """Reopen APPLICATIONS_CLOSED -> APPLICATIONS_OPEN only BEFORE allocation has run."""
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    if cycle["status"] != "APPLICATIONS_CLOSED":
        raise ConflictError(
            "Reopen is only permitted from APPLICATIONS_CLOSED before allocation",
            code="REOPEN_NOT_ALLOWED",
        )
    existing_run = await db["allocation_runs"].find_one({"cycle_id": cycle_id})
    if existing_run:
        raise ConflictError(
            "Allocation has already been executed — cannot reopen",
            code="REOPEN_NOT_ALLOWED",
        )
    new_close = _parse_dt(new_close_raw)
    now = _clock.now()
    if new_close and new_close <= now:
        raise ValidationError("New apply_close_at must be in the future")

    update_fields: dict = {
        "status": "APPLICATIONS_OPEN",
        "schedule_history": cycle.get("schedule_history", []) + [{
            "at": now,
            "by": actor_id,
            "action": "REOPEN",
            "apply_close_at": new_close or cycle.get("apply_close_at"),
            "reason": reason,
        }],
    }
    if new_close:
        update_fields["apply_close_at"] = new_close

    await cat_repo.update_cycle(db, cycle_id, update_fields)
    # Unlock submitted/ready groups so applicants can edit again
    await db["groups"].update_many(
        {"cycle_id": cycle_id, "status": "LOCKED"},
        {"$set": {"status": "SUBMITTED", "updated_at": now}},
    )
    await repo.create_audit_log(db, {
        "actor_id": actor_id,
        "role": "ADMIN",
        "action": "REOPEN_CYCLE",
        "target_type": "cycle",
        "target_id": cycle_id,
        "before": {"status": "APPLICATIONS_CLOSED"},
        "after": {"status": "APPLICATIONS_OPEN", "reason": reason},
        "request_id": "",
        "ip": "",
    })
    return serialize_cycle(await cat_repo.get_cycle(db, cycle_id))


async def update_cycle_impl(db, cycle_id: str, body: dict, actor_id: str) -> dict:
    """Update cycle configuration while still DRAFT or SCHEDULED."""
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    if cycle["status"] not in ("DRAFT", "SCHEDULED"):
        raise ConflictError("Can only edit DRAFT or SCHEDULED cycles", code="VALIDATION_ERROR")

    allowed = {"name", "academic_year", "freeze_hours", "policy", "room_ids",
               "apply_open_at", "apply_close_at", "final_deadline_at"}
    update: dict = {}
    for k in allowed:
        if k in body:
            if k in ("apply_open_at", "apply_close_at", "final_deadline_at"):
                update[k] = _parse_dt(body[k])
            else:
                update[k] = body[k]

    if update:
        await cat_repo.update_cycle(db, cycle_id, update)
        await repo.create_audit_log(db, {
            "actor_id": actor_id,
            "role": "ADMIN",
            "action": "UPDATE_CYCLE",
            "target_type": "cycle",
            "target_id": cycle_id,
            "before": {"name": cycle.get("name")},
            "after": {k: str(v) for k, v in update.items()},
            "request_id": "",
            "ip": "",
        })
    return serialize_cycle(await cat_repo.get_cycle(db, cycle_id))


# ─────────────────────────── cycle stats ─────────────────────────────────────

async def get_cycle_stats(db, cycle_id: str) -> dict:
    """Return aggregate counts for a given cycle."""
    n_applications: int = await db["applications"].count_documents({"cycle_id": cycle_id})
    n_groups: int = await db["groups"].count_documents({"cycle_id": cycle_id})
    n_allotments: int = await db["allotments"].count_documents(
        {"cycle_id": cycle_id, "is_active": True}
    )
    n_confirmed: int = await db["allotments"].count_documents(
        {"cycle_id": cycle_id, "status": "CONFIRMED", "is_active": True}
    )
    n_held: int = await db["allotments"].count_documents(
        {"cycle_id": cycle_id, "status": "HELD", "is_active": True}
    )

    return {
        "n_applications": n_applications,
        "n_groups": n_groups,
        "n_allotments": n_allotments,
        "n_confirmed": n_confirmed,
        "n_held": n_held,
    }
