"""Allotment service: accept, decline, cancel, revoke, manual assign, cascade, settlement (NO payment)."""

from __future__ import annotations

from datetime import timedelta

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.allocator.core import AppIn, Choice, Policy, RoomIn, assign_in_order
from app.core import clock as _clock
from app.core.errors import ConflictError, NotFoundError
from app.fairness.engine import delta_for_outcome, get_policy
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.repositories import users as user_repo


async def serialize_allotment(db, doc: dict | None) -> dict | None:
    """Serialize allotment with room, floor, hostel, and member names/rolls (no payment fields)."""
    if not doc:
        return None
    res = {**doc, "_id": str(doc["_id"]), "id": str(doc["_id"])}

    room = await cat_repo.get_room(db, doc["room_id"]) if doc.get("room_id") else None
    hostel = await cat_repo.get_hostel(db, room["hostel_id"]) if room else None
    if room:
        res["room"] = {
            "_id": str(room["_id"]),
            "room_no": room.get("room_no", ""),
            "floor_no": room.get("floor_no"),
            "capacity": room.get("capacity"),
            "hostel_id": room.get("hostel_id"),
            "hostel_name": hostel.get("name", "") if hostel else "",
        }
        res["room_no"] = room.get("room_no", "")
        res["floor_no"] = room.get("floor_no")
        res["hostel_name"] = hostel.get("name", "") if hostel else ""

    enriched_members = []
    for m in doc.get("members", []):
        u = await user_repo.find_user_by_id(db, m["user_id"]) if ObjectId.is_valid(m["user_id"]) else None
        enriched_members.append({
            **m,
            "name": u.get("name", "") if u else "",
            "roll_no": u.get("roll_no", "") if u else "",
            "email": u.get("email", "") if u else "",
        })
    res["members"] = enriched_members
    return res


# ─────────────────────────── accept ──────────────────────────────────────────

async def accept_allotment(db, client, allotment_id: str, user_id: str) -> dict:
    """
    Member accepts their allotment. No payment.
    When ALL members have accepted → CONFIRMED.
    Idempotent if this member already accepted while HELD/CONFIRMED.
    """
    now = _clock.now()

    async def _do(session):
        doc = await repo.accept_member(db, allotment_id, user_id, now, session=session)
        if doc is None:
            existing = await db["allotments"].find_one(
                {"_id": ObjectId(allotment_id)}, session=session
            )
            if not existing:
                raise NotFoundError("Allotment not found")
            member_map = {m["user_id"]: m for m in existing.get("members", [])}
            caller_m = member_map.get(user_id)
            if not caller_m:
                raise NotFoundError("Allotment not found")
            if caller_m.get("accept_status") == "ACCEPTED":
                if existing["status"] == "CONFIRMED":
                    return existing
                if existing["status"] == "HELD" and existing.get("expires_at") and existing["expires_at"] > now:
                    return existing
            raise ConflictError(
                "Cannot accept — hold expired or allotment no longer active",
                code="HOLD_EXPIRED",
            )

        all_accepted = all(m["accept_status"] == "ACCEPTED" for m in doc["members"])
        if all_accepted:
            confirmed = await cat_repo.confirm_room(
                db, doc["cycle_id"], doc["room_id"], allotment_id, session=session
            )
            if not confirmed:
                raise ConflictError("Room state changed unexpectedly", code="ROOM_TAKEN")
            await repo.update_allotment(db, allotment_id, {
                "status": "CONFIRMED",
                "confirmed_at": now,
            }, session=session)
            await db["applications"].update_one(
                {"_id": ObjectId(doc["application_id"])},
                {"$set": {"status": "CONFIRMED", "updated_at": now}},
                session=session,
            )
            for m in doc["members"]:
                await repo.create_notification(db, {
                    "user_id": m["user_id"],
                    "type": "ALLOTMENT_CONFIRMED",
                    "title": "Room Allotment Confirmed",
                    "body": "All group members accepted. Your room booking is confirmed.",
                    "read": False,
                }, session=session)
            return await db["allotments"].find_one({"_id": ObjectId(allotment_id)}, session=session)
        return doc

    async with client.start_session() as session:
        result = await session.with_transaction(_do)
    return result


# ─────────────────────────── decline ─────────────────────────────────────────

async def decline_allotment(db, client, allotment_id: str, user_id: str) -> dict:
    """Any member can decline a HELD allotment. Releases room, forfeits app, triggers cascade."""
    now = _clock.now()

    async def _do(session):
        allotment = await db["allotments"].find_one({"_id": ObjectId(allotment_id)}, session=session)
        if not allotment:
            raise NotFoundError("Allotment not found")
        member_ids = [m["user_id"] for m in allotment.get("members", [])]
        if user_id not in member_ids:
            raise NotFoundError("Allotment not found")
        if allotment["status"] != "HELD":
            raise ConflictError("Can only decline a HELD allotment", code="HOLD_EXPIRED")

        released = await cat_repo.release_room(
            db, allotment["cycle_id"], allotment["room_id"],
            allotment_id, from_status="HELD", session=session,
        )
        if not released:
            raise ConflictError("Room release conflict", code="CONFLICT")

        # Mark declining member explicitly & set allotment DECLINED
        updated_members = []
        for m in allotment.get("members", []):
            if m["user_id"] == user_id:
                updated_members.append({**m, "accept_status": "DECLINED"})
            else:
                updated_members.append(m)

        await repo.update_allotment(db, allotment_id, {
            "status": "DECLINED",
            "is_active": False,
            "release_reason": "DECLINED",
            "members": updated_members,
        }, session=session)

        await db["applications"].update_one(
            {"_id": ObjectId(allotment["application_id"])},
            {"$set": {
                "status": "FORFEITED",
                "last_allotment_status": "DECLINED",
                "updated_at": now,
            }},
            session=session,
        )

        for uid in member_ids:
            await repo.create_notification(db, {
                "user_id": uid,
                "type": "ALLOTMENT_DECLINED",
                "title": "Allotment Declined",
                "body": "A group member declined the room offer; the room was released.",
                "read": False,
            }, session=session)

        await repo.create_audit_log(db, {
            "actor_id": user_id,
            "role": "STUDENT",
            "action": "DECLINE_ALLOTMENT",
            "target_type": "allotment",
            "target_id": allotment_id,
            "before": {"status": "HELD"},
            "after": {"status": "DECLINED"},
            "request_id": "",
            "ip": "",
        }, session=session)

        return await db["allotments"].find_one({"_id": ObjectId(allotment_id)}, session=session)

    async with client.start_session() as session:
        updated = await session.with_transaction(_do)

    await run_cascade(db, client, updated["cycle_id"])
    return updated


# ─────────────────────────── cancel (after confirm) ──────────────────────────

async def cancel_allotment(db, client, allotment_id: str, user_id: str) -> dict:
    """Cancel a CONFIRMED allotment (member-initiated before final deadline)."""
    now = _clock.now()

    async def _do(session):
        allotment = await db["allotments"].find_one({"_id": ObjectId(allotment_id)}, session=session)
        if not allotment:
            raise NotFoundError("Allotment not found")
        member_ids = [m["user_id"] for m in allotment.get("members", [])]
        if user_id not in member_ids:
            raise NotFoundError("Allotment not found")
        if allotment["status"] != "CONFIRMED":
            raise ConflictError("Can only cancel a CONFIRMED allotment", code="VALIDATION_ERROR")

        cycle = await cat_repo.get_cycle(db, allotment["cycle_id"])
        if cycle and cycle.get("final_deadline_at") and now > cycle["final_deadline_at"]:
            raise ConflictError("Cancellation cutoff deadline has passed", code="CANCEL_CUTOFF_PASSED")
        if cycle and cycle.get("status") in ("CLOSED", "SETTLED"):
            raise ConflictError("Cycle is closed; cannot cancel allotment", code="CANCEL_CUTOFF_PASSED")

        await cat_repo.release_room(
            db, allotment["cycle_id"], allotment["room_id"],
            allotment_id, from_status="CONFIRMED", session=session,
        )
        await repo.update_allotment(db, allotment_id, {
            "status": "CANCELLED",
            "is_active": False,
            "release_reason": "MEMBER_CANCELLED",
        }, session=session)
        await db["applications"].update_one(
            {"_id": ObjectId(allotment["application_id"])},
            {"$set": {
                "status": "FORFEITED",
                "last_allotment_status": "CANCELLED",
                "updated_at": now,
            }},
            session=session,
        )

        for uid in member_ids:
            await repo.create_notification(db, {
                "user_id": uid,
                "type": "ALLOTMENT_CANCELLED",
                "title": "Booking Cancelled",
                "body": "Your confirmed room booking was cancelled and the room was released.",
                "read": False,
            }, session=session)

        await repo.create_audit_log(db, {
            "actor_id": user_id,
            "role": "STUDENT",
            "action": "CANCEL_ALLOTMENT",
            "target_type": "allotment",
            "target_id": allotment_id,
            "before": {"status": "CONFIRMED"},
            "after": {"status": "CANCELLED"},
            "request_id": "",
            "ip": "",
        }, session=session)

        return await db["allotments"].find_one({"_id": ObjectId(allotment_id)}, session=session)

    async with client.start_session() as session:
        updated = await session.with_transaction(_do)

    await run_cascade(db, client, updated["cycle_id"])
    return updated


# ─────────────────────────── revoke (admin / warden) ─────────────────────────

async def revoke_allotment(db, client, allotment_id: str, reason: str, actor_id: str) -> dict:
    """Admin/warden revokes. No credit penalty. Priority reinsert in cascade."""
    now = _clock.now()

    async def _do(session):
        allotment = await db["allotments"].find_one({"_id": ObjectId(allotment_id)}, session=session)
        if not allotment:
            raise NotFoundError("Allotment not found")
        if allotment["status"] not in ("HELD", "CONFIRMED"):
            raise ConflictError("Can only revoke HELD or CONFIRMED allotments", code="VALIDATION_ERROR")

        from_status = allotment["status"]
        await cat_repo.release_room(
            db, allotment["cycle_id"], allotment["room_id"],
            allotment_id, from_status=from_status, session=session,
        )
        await repo.update_allotment(db, allotment_id, {
            "status": "REVOKED",
            "is_active": False,
            "release_reason": f"REVOKED: {reason}",
        }, session=session)
        await db["applications"].update_one(
            {"_id": ObjectId(allotment["application_id"])},
            {"$set": {
                "status": "WAITLISTED",
                "reinsert": True,
                "last_allotment_status": "REVOKED",
                "updated_at": now,
            }},
            session=session,
        )
        for m in allotment.get("members", []):
            await repo.create_notification(db, {
                "user_id": m["user_id"],
                "type": "ALLOTMENT_REVOKED",
                "title": "Allotment Revoked by Administration",
                "body": f"Reason: {reason}. Your application has been reinserted at the top of the waitlist with no credit penalty.",
                "read": False,
            }, session=session)

        await repo.create_audit_log(db, {
            "actor_id": actor_id,
            "role": "ADMIN",
            "action": "REVOKE_ALLOTMENT",
            "target_type": "allotment",
            "target_id": allotment_id,
            "before": {"status": from_status},
            "after": {"status": "REVOKED", "reason": reason},
            "request_id": "",
            "ip": "",
        }, session=session)

        return await db["allotments"].find_one({"_id": ObjectId(allotment_id)}, session=session)

    async with client.start_session() as session:
        updated = await session.with_transaction(_do)

    await run_cascade(db, client, updated["cycle_id"])
    return updated


async def extend_hold(
    db, allotment_id: str, reason: str, actor_id: str, extra_hours: int = 24
) -> dict:
    """Admin/warden one-time hold extension."""
    allotment = await repo.get_allotment(db, allotment_id)
    if not allotment:
        raise NotFoundError("Allotment not found")
    if allotment["status"] != "HELD":
        raise ConflictError("Can only extend a HELD allotment", code="VALIDATION_ERROR")
    if allotment.get("admin_extended"):
        raise ConflictError("Hold already extended once", code="VALIDATION_ERROR")
    hours = max(1, min(72, int(extra_hours or 24)))
    new_expires = allotment["expires_at"] + timedelta(hours=hours)
    await repo.update_allotment(db, allotment_id, {
        "expires_at": new_expires,
        "admin_extended": True,
        "reminder_sent_at": None,  # re-arm the expiry reminder for the new deadline
        "admin_extend_reason": reason,
        "admin_extend_by": actor_id,
    })
    for m in allotment.get("members", []):
        await repo.create_notification(db, {
            "user_id": m["user_id"],
            "type": "HOLD_EXTENDED",
            "title": "Room Hold Extended",
            "body": f"Your confirmation deadline was extended by {hours}h. Reason: {reason}",
            "read": False,
        })
    await repo.create_audit_log(db, {
        "actor_id": actor_id,
        "role": "ADMIN",
        "action": "EXTEND_HOLD",
        "target_type": "allotment",
        "target_id": allotment_id,
        "before": {"expires_at": str(allotment["expires_at"])},
        "after": {"expires_at": str(new_expires), "reason": reason},
        "request_id": "",
        "ip": "",
    })
    return await repo.get_allotment(db, allotment_id)


async def manual_assign(
    db,
    client,
    cycle_id: str,
    target_id: str,
    room_id: str,
    actor_id: str,
) -> dict:
    """Manually assign an AVAILABLE room to a WAITLISTED/UNALLOTTED/SUBMITTED application (or group_id)."""
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")

    app_doc = None
    if ObjectId.is_valid(target_id):
        app_doc = await db["applications"].find_one({"_id": ObjectId(target_id), "cycle_id": cycle_id})
    if not app_doc:
        app_doc = await db["applications"].find_one({"cycle_id": cycle_id, "group_id": target_id})
    if not app_doc:
        raise NotFoundError("Application not found in cycle")
    if app_doc["status"] not in ("WAITLISTED", "UNALLOTTED", "SUBMITTED"):
        raise ConflictError("Application already holds an allotment or was forfeited", code="CONFLICT")

    inv = await cat_repo.get_inventory(db, cycle_id, room_id)
    if not inv or inv["status"] != "AVAILABLE":
        raise ConflictError("Selected room is not AVAILABLE", code="ROOM_TAKEN")

    room = await cat_repo.get_room(db, room_id)
    if not room:
        raise NotFoundError("Room not found")

    group_size = int(app_doc.get("group_size", 1))
    fill_rule = cycle.get("policy", {}).get("fill_rule", "EXACT")
    if (fill_rule == "EXACT" and int(inv["capacity"]) != group_size) or (
        fill_rule == "AT_MOST" and group_size > int(inv["capacity"])
    ):
        raise ConflictError("Room capacity does not match group size", code="ROOM_NOT_ELIGIBLE")

    now = _clock.now()
    expires_at = now + timedelta(hours=int(cycle.get("freeze_hours", 48)))
    allotment_id = ObjectId()

    async def _do(session):
        held = await cat_repo.hold_room(db, cycle_id, room_id, str(allotment_id), session=session)
        if not held:
            raise ConflictError("Room no longer available", code="ROOM_TAKEN")

        members_raw = await db["memberships"].find(
            {"group_id": app_doc["group_id"], "status": "ACCEPTED"}, session=session
        ).to_list(length=10)
        allotment_members = [
            {"user_id": m["user_id"], "accept_status": "PENDING", "accepted_at": None}
            for m in members_raw
        ]

        await db["allotments"].insert_one({
            "_id": allotment_id,
            "cycle_id": cycle_id,
            "application_id": str(app_doc["_id"]),
            "group_id": app_doc["group_id"],
            "room_id": room_id,
            "group_size": group_size,
            "rank_obtained": len(app_doc.get("ranked_choices", [])) + 1,
            "round_no": 99,
            "status": "HELD",
            "is_active": True,
            "manual": True,
            "held_at": now,
            "expires_at": expires_at,
            "grace_used": False,
            "members": allotment_members,
            "created_at": now,
            "updated_at": now,
        }, session=session)

        await db["applications"].update_one(
            {"_id": app_doc["_id"]},
            {"$set": {"status": "ALLOTTED", "reinsert": False, "updated_at": now}},
            session=session,
        )

        for m in allotment_members:
            await repo.create_notification(db, {
                "user_id": m["user_id"],
                "type": "ALLOTMENT_HELD",
                "title": f"Room {room.get('room_no', room_id)} Assigned",
                "body": "An administrator offered a room to your group. Please accept before deadline.",
                "read": False,
            }, session=session)

        await repo.create_audit_log(db, {
            "actor_id": actor_id,
            "role": "ADMIN",
            "action": "MANUAL_ASSIGN",
            "target_type": "allotment",
            "target_id": str(allotment_id),
            "before": None,
            "after": {"cycle_id": cycle_id, "application_id": str(app_doc["_id"]), "room_id": room_id},
            "request_id": "",
            "ip": "",
        }, session=session)

        return await db["allotments"].find_one({"_id": allotment_id}, session=session)

    async with client.start_session() as session:
        return await session.with_transaction(_do)


# ─────────────────────────── cascade ─────────────────────────────────────────

def _build_policy_from_dict(policy_dict: dict) -> Policy:
    p = get_policy(policy_dict)
    return Policy(
        fill_rule=p.get("fill_rule", "EXACT"),
        group_weight_policy=p.get("group_weight_policy", "MEAN"),
        c_init=p.get("c_init", 3),
        c_min=p.get("c_min", 0),
        c_max=p.get("c_max", 10),
        rank_deltas=p.get("rank_deltas", {}),
        unallotted_delta=p.get("unallotted_delta", 2),
        forfeit_delta=p.get("forfeit_delta", -2),
        late_cancel_delta=p.get("late_cancel_delta", -1),
        carry_over_factor=p.get("carry_over_factor", 0.5),
    )


async def run_cascade(db, client, cycle_id: str, actor_id: str = "system") -> dict:
    """
    Re-offer released rooms to WAITLISTED applications strictly in original order_index order
    (reinsert=True first), without recomputing Efraimidis-Spirakis random keys (R-CASC-1).
    """
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle or cycle["status"] not in ("ALLOTMENT_ACTIVE", "APPLICATIONS_CLOSED"):
        return {"cascade_allotted": 0, "allotted": 0, "round_no": 1, "remaining_waitlisted": 0}

    waitlisted_apps = await repo.list_waitlisted_by_cycle(db, cycle_id)
    if not waitlisted_apps:
        return {"cascade_allotted": 0, "allotted": 0, "round_no": 1, "remaining_waitlisted": 0}

    available_inv = await cat_repo.list_inventory(db, cycle_id, status="AVAILABLE")
    if not available_inv:
        return {"cascade_allotted": 0, "allotted": 0, "round_no": 1, "remaining_waitlisted": len(waitlisted_apps)}

    # Batch load all cycle rooms so floor/fallback hostel resolution has full map
    all_cycle_inv = await cat_repo.list_inventory(db, cycle_id)
    room_obj_ids = [ObjectId(i["room_id"]) for i in all_cycle_inv if ObjectId.is_valid(i["room_id"])]
    room_docs: dict[str, dict] = {}
    if room_obj_ids:
        async for rm in db["rooms"].find({"_id": {"$in": room_obj_ids}}):
            room_docs[str(rm["_id"])] = rm

    rooms: dict[str, RoomIn] = {}
    for inv in all_cycle_inv:
        rm = room_docs.get(inv["room_id"])
        if rm:
            rooms[inv["room_id"]] = RoomIn(
                hostel_id=inv["hostel_id"],
                floor_no=int(inv["floor_no"]),
                room_no=rm.get("room_no", inv["room_id"]),
                capacity=int(inv["capacity"]),
            )

    free_room_ids = {inv["room_id"] for inv in available_inv if inv["room_id"] in rooms}
    if not free_room_ids:
        return {"cascade_allotted": 0, "allotted": 0, "round_no": 1, "remaining_waitlisted": len(waitlisted_apps)}

    policy = _build_policy_from_dict(cycle.get("policy", {}))

    app_map: dict[str, dict] = {str(a["_id"]): a for a in waitlisted_apps}
    apps_in: list[AppIn] = []
    for a in waitlisted_apps:
        choices = [
            Choice(
                kind=ch.get("kind", "ROOM"),
                room_id=ch.get("room_id"),
                hostel_id=ch.get("hostel_id") or cycle["hostel_id"],
                floor_no=ch.get("floor_no"),
            )
            for ch in a.get("ranked_choices", [])
        ]
        apps_in.append(AppIn(
            id=str(a["_id"]),
            tier=int(a.get("tier", 1)),
            group_size=int(a.get("group_size", 1)),
            choices=choices,
            fallback=a.get("fallback", "NONE"),
            weight=float(a.get("weight", 1.0) or 1.0),
            reinsert=bool(a.get("reinsert", False)),
            order_index=a.get("order_index"),
        ))

    # Deterministic cascade preserving original Round-1 order_index (no seed re-randomisation)
    result = assign_in_order(apps_in, rooms, free_room_ids, policy)
    if not result.allotments:
        return {"cascade_allotted": 0, "allotted": 0, "round_no": 1, "remaining_waitlisted": len(waitlisted_apps)}

    # Determine next round number
    last_run = await db["allocation_runs"].find({"cycle_id": cycle_id}).sort("round_no", -1).limit(1).to_list(1)
    next_round = (last_run[0]["round_no"] + 1) if last_run else 2

    now = _clock.now()
    freeze_hours = int(cycle.get("freeze_hours", 48))
    run_id = ObjectId()
    actually_created = 0

    async def _commit(session):
        nonlocal actually_created
        actually_created = 0
        notif_docs: list[dict] = []

        for a_out in result.allotments:
            app_doc = app_map.get(a_out.app_id)
            if not app_doc:
                continue
            allotment_id = ObjectId()
            group_size = int(app_doc.get("group_size", 1))
            members_raw = await db["memberships"].find(
                {"group_id": app_doc["group_id"], "status": "ACCEPTED"},
                session=session,
            ).to_list(length=10)
            allotment_members = [
                {"user_id": m["user_id"], "accept_status": "PENDING", "accepted_at": None}
                for m in members_raw
            ]
            expires_at = now + timedelta(hours=freeze_hours)

            held = await cat_repo.hold_room(
                db, cycle_id, a_out.room_id, str(allotment_id), session=session
            )
            if not held:
                continue

            await db["allotments"].insert_one({
                "_id": allotment_id,
                "cycle_id": cycle_id,
                "application_id": a_out.app_id,
                "group_id": app_doc["group_id"],
                "room_id": a_out.room_id,
                "group_size": group_size,
                "rank_obtained": a_out.rank_obtained,
                "round_no": next_round,
                "status": "HELD",
                "is_active": True,
                "held_at": now,
                "expires_at": expires_at,
                "grace_used": False,
                "members": allotment_members,
                "run_id": str(run_id),
                "order_index": a_out.order_index,
                "created_at": now,
                "updated_at": now,
            }, session=session)

            await db["applications"].update_one(
                {"_id": ObjectId(a_out.app_id)},
                {"$set": {"status": "ALLOTTED", "reinsert": False, "updated_at": now}},
                session=session,
            )
            actually_created += 1

            room_info = rooms.get(a_out.room_id)
            room_label = room_info.room_no if room_info else a_out.room_id
            for m in allotment_members:
                notif_docs.append({
                    "_id": ObjectId(),
                    "user_id": m["user_id"],
                    "type": "CASCADE_OFFER",
                    "title": f"Waitlist Offer: Room {room_label}",
                    "body": f"A room opened up from cascade (Round {next_round}). Accept within {freeze_hours}h.",
                    "read": False,
                    "created_at": now,
                })

        if actually_created > 0:
            await db["allocation_runs"].insert_one({
                "_id": run_id,
                "cycle_id": cycle_id,
                "round_no": next_round,
                "type": "CASCADE",
                "algorithm_version": "rsd-weighted-1.0",
                "params": {"fill_rule": policy.fill_rule},
                "seed_commitment": cycle.get("seed_commitment"),
                "seed_revealed": cycle.get("seed_secret"),
                "stats": {"cascade_allotted": actually_created},
                "status": "COMPLETED",
                "started_at": now,
                "finished_at": now,
                "triggered_by": actor_id,
                "created_at": now,
                "updated_at": now,
            }, session=session)
            if notif_docs:
                await db["notifications"].insert_many(notif_docs, session=session)

    async with client.start_session() as session:
        await session.with_transaction(_commit)

    remaining_waitlisted = await db["applications"].count_documents(
        {"cycle_id": cycle_id, "status": "WAITLISTED"}
    )
    return {
        "cascade_allotted": actually_created,
        "allotted": actually_created,
        "round_no": next_round,
        "remaining_waitlisted": remaining_waitlisted,
    }


# ─────────────────────────── credit settlement ───────────────────────────────

async def settle_cycle(db, client, cycle_id: str) -> dict:
    """
    Settle credits for all members of a CLOSED (or finalized ALLOTMENT_ACTIVE with 0 HELD) cycle. Idempotent.
    CONFIRMED → rank delta; UNALLOTTED → +2; FORFEITED (DECLINED/EXPIRED) → -2;
    LATE_CANCELLED → -1; REVOKED (even if still unallotted) → 0.
    """
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    if cycle["status"] == "ALLOTMENT_ACTIVE":
        held_count = await db["allotments"].count_documents(
            {"cycle_id": cycle_id, "status": "HELD"}
        )
        if held_count > 0:
            raise ConflictError(
                "Cycle still has active HELD allotments; resolve or expire holds before settling",
                code="VALIDATION_ERROR",
            )
        await cat_repo.update_cycle(db, cycle_id, {"status": "CLOSED", "closed_at": _clock.now()})
    elif cycle["status"] not in ("CLOSED", "SETTLED"):
        raise ConflictError("Cycle must be CLOSED before settling", code="VALIDATION_ERROR")

    p = get_policy(cycle.get("policy", {}))
    c_min, c_max = p["c_min"], p["c_max"]
    settled_count = 0
    now = _clock.now()

    # Release live room inventory locks for closed/settled cycle
    await db["room_inventory"].update_many(
        {"cycle_id": cycle_id, "is_live": True},
        {"$set": {"is_live": False, "updated_at": now}},
    )

    # Ensure any lingering WAITLISTED apps become UNALLOTTED
    await repo.mark_unallotted(db, cycle_id)

    all_apps = await db["applications"].find({"cycle_id": cycle_id}).to_list(length=10000)
    for app in all_apps:
        app_status = app.get("status", "")
        if app_status in ("DRAFT", "WITHDRAWN"):
            continue

        allotment = await repo.get_latest_allotment_for_application(db, cycle_id, str(app["_id"]))
        last_status = app.get("last_allotment_status") or (allotment["status"] if allotment else None)

        if allotment and allotment["status"] == "CONFIRMED":
            outcome = "CONFIRMED"
            rank = allotment.get("rank_obtained")
            n_choices = len(app.get("ranked_choices", []))
        elif last_status == "CANCELLED":
            outcome = "LATE_CANCELLED"
            rank = None
            n_choices = 0
        elif app_status == "FORFEITED" or last_status in ("EXPIRED", "DECLINED"):
            outcome = "FORFEITED"
            rank = None
            n_choices = 0
        elif last_status == "REVOKED":
            outcome = "REVOKED"
            rank = None
            n_choices = 0
        elif app_status in ("UNALLOTTED", "WAITLISTED"):
            outcome = "UNALLOTTED"
            rank = None
            n_choices = 0
        else:
            continue

        delta, event_type = delta_for_outcome(p, outcome, rank, n_choices)

        for user_id in app.get("member_ids", []):
            async def _settle_one(session, uid=user_id, d=delta, et=event_type, aid=str(app["_id"])):
                already = await db["credit_ledger"].find_one(
                    {"cycle_id": cycle_id, "user_id": uid, "event_type": et},
                    {"_id": 1},
                    session=session,
                )
                if already:
                    return False
                acct = await db["credit_accounts"].find_one({"user_id": uid}, session=session)
                cb = acct["credits"] if acct else p["c_init"]
                ca = max(c_min, min(c_max, cb + d))
                await repo.insert_ledger_entry(db, {
                    "user_id": uid,
                    "cycle_id": cycle_id,
                    "event_type": et,
                    "delta": d,
                    "credits_before": cb,
                    "credits_after": ca,
                    "ref_id": aid,
                    "reason": f"Cycle settlement: {et}",
                }, session=session)
                await repo.apply_credit_delta(db, uid, d, c_min, c_max, now, session=session)
                return True

            async with client.start_session() as session:
                try:
                    applied = await session.with_transaction(_settle_one)
                    if applied:
                        settled_count += 1
                except DuplicateKeyError:
                    pass  # Concurrent settle already recorded this ledger entry idempotently

    await cat_repo.update_cycle(db, cycle_id, {"status": "SETTLED"})
    return {"settled_members": settled_count, "settled_users": settled_count}
