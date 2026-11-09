"""Group and application services."""

from __future__ import annotations

from app.core import clock as _clock
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.scope import assert_student_eligible_for_hostel
from app.fairness.engine import get_policy, group_weight
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.repositories import users as user_repo


# ─────────────────────────── groups ──────────────────────────────────────────

async def create_group(db, cycle_id: str, leader_id: str, name: str, solo: bool = False) -> dict:
    cycle = await _get_open_cycle(db, cycle_id)
    leader = await user_repo.find_user_by_id(db, leader_id)
    if not leader:
        raise NotFoundError("User not found")
    await assert_student_eligible_for_hostel(db, leader, cycle["hostel_id"])

    existing = await repo.get_accepted_membership(db, cycle_id, leader_id)
    if existing:
        raise ConflictError("You are already in a group for this cycle", code="ALREADY_IN_GROUP")

    now = _clock.now()
    # If solo, create directly as READY
    group_status = "READY" if solo else "FORMING"
    group_doc = {
        "cycle_id": cycle_id,
        "leader_id": leader_id,
        "name": (name or "").strip() or (f"{leader.get('name', 'Student')}'s Group" if not solo else "Solo Application"),
        "status": group_status,
        "solo": bool(solo),
        "size": 1,
        "gender": leader.get("gender", ""),
    }
    group_id = await repo.create_group(db, group_doc)
    await repo.create_membership(db, {
        "cycle_id": cycle_id,
        "group_id": group_id,
        "user_id": leader_id,
        "role": "LEADER",
        "status": "ACCEPTED",
        "invited_at": now,
        "responded_at": now,
    })
    return await repo.get_group(db, group_id)


async def invite_member(db, group_id: str, identifier: str, leader_id: str) -> dict:
    group = await _get_group_or_404(db, group_id)
    _assert_leader(group, leader_id)
    await _get_open_cycle(db, group["cycle_id"])
    _assert_group_modifiable(group)
    if group.get("solo"):
        raise ConflictError("Cannot invite members to a solo group", code="VALIDATION_ERROR")

    members = await repo.list_memberships_by_group(db, group_id)
    active_or_invited = [m for m in members if m["status"] in ("ACCEPTED", "INVITED")]
    if len(active_or_invited) >= 4:
        raise ConflictError("Group is full (max 4 members/invites)", code="GROUP_FULL")

    ident = (identifier or "").strip()
    if not ident:
        raise ValidationError("Roll number or email is required")
    invitee = await user_repo.find_user_by_identifier(db, ident)
    if not invitee:
        raise NotFoundError("Student not found")
    if str(invitee["_id"]) == leader_id:
        raise ConflictError("Cannot invite yourself", code="VALIDATION_ERROR")
    if invitee.get("role") != "STUDENT":
        raise ConflictError("Only students can be invited to room groups", code="NOT_ELIGIBLE")
    if invitee.get("status") != "ACTIVE":
        raise ValidationError("Student account is not active")

    cycle = await _get_cycle(db, group["cycle_id"])
    try:
        await assert_student_eligible_for_hostel(db, invitee, cycle["hostel_id"])
    except NotFoundError:
        raise ConflictError("Student is not eligible for this hostel/cycle", code="NOT_ELIGIBLE")

    invitee_id = str(invitee["_id"])
    if await repo.get_accepted_membership(db, group["cycle_id"], invitee_id):
        raise ConflictError("Student is already in a group", code="ALREADY_IN_GROUP")

    existing_ms = await repo.find_membership_by_user_group(db, group_id, invitee_id)
    if existing_ms and existing_ms["status"] == "INVITED":
        raise ConflictError("Invite already pending for this student", code="INVITE_ALREADY_PENDING")

    now = _clock.now()
    membership_id = await repo.create_membership(db, {
        "cycle_id": group["cycle_id"],
        "group_id": group_id,
        "user_id": invitee_id,
        "role": "MEMBER",
        "status": "INVITED",
        "invited_at": now,
    })
    if group.get("status") in ("READY", "SUBMITTED"):
        await repo.update_group(db, group_id, {"status": "FORMING"})
    # Notify invitee
    await repo.create_notification(db, {
        "user_id": invitee_id,
        "type": "GROUP_INVITE",
        "title": f"Group Invite: {group.get('name', 'Group')}",
        "body": "You have been invited to join a hostel room group.",
        "read": False,
    })
    return await repo.get_membership(db, membership_id)


async def list_my_invites(db, cycle_id: str, user_id: str) -> list[dict]:
    invites = await repo.list_pending_invites_for_user(db, cycle_id, user_id)
    enriched = []
    for inv in invites:
        group = await repo.get_group(db, inv["group_id"])
        if not group or group.get("status") == "DISBANDED":
            continue
        leader = await user_repo.find_user_by_id(db, group["leader_id"])
        enriched.append({
            **inv,
            "_id": str(inv["_id"]),
            "group_name": group.get("name", ""),
            "group_size": group.get("size", 1),
            "leader_name": leader.get("name", "") if leader else "",
            "leader_roll_no": leader.get("roll_no", "") if leader else "",
        })
    return enriched


async def accept_invite(db, membership_id: str, user_id: str) -> dict:
    ms = await repo.get_membership(db, membership_id)
    if not ms or ms["user_id"] != user_id:
        raise NotFoundError("Invite not found")
    if ms["status"] != "INVITED":
        raise ConflictError("Invite already answered", code="ALREADY_ANSWERED")

    await _get_open_cycle(db, ms["cycle_id"])
    group = await _get_group_or_404(db, ms["group_id"])
    _assert_group_modifiable(group)
    if group.get("status") == "DISBANDED":
        raise ConflictError("Group has been disbanded", code="GROUP_DISBANDED")

    user = await user_repo.find_user_by_id(db, user_id)
    cycle = await _get_cycle(db, ms["cycle_id"])
    await assert_student_eligible_for_hostel(db, user, cycle["hostel_id"])

    now = _clock.now()
    await repo.decline_other_invites(db, ms["cycle_id"], user_id, ms["group_id"])
    await repo.update_membership(db, membership_id, {"status": "ACCEPTED", "responded_at": now})

    members = await repo.list_memberships_by_group(db, ms["group_id"])
    accepted = [m for m in members if m["status"] == "ACCEPTED"]
    no_pending = not any(m["status"] == "INVITED" for m in members)
    new_status = "READY" if (no_pending and len(accepted) > 0) else "FORMING"
    await repo.update_group(db, ms["group_id"], {"size": len(accepted), "status": new_status})
    return await repo.get_group(db, ms["group_id"])


async def decline_invite(db, membership_id: str, user_id: str) -> dict:
    ms = await repo.get_membership(db, membership_id)
    if not ms or ms["user_id"] != user_id:
        raise NotFoundError("Invite not found")
    if ms["status"] != "INVITED":
        raise ConflictError("Invite already answered", code="ALREADY_ANSWERED")
    await repo.update_membership(db, membership_id, {"status": "DECLINED", "responded_at": _clock.now()})
    members = await repo.list_memberships_by_group(db, ms["group_id"])
    accepted = [m for m in members if m["status"] == "ACCEPTED"]
    no_pending = not any(m["status"] == "INVITED" for m in members)
    group = await repo.get_group(db, ms["group_id"])
    if group and group.get("status") == "FORMING" and no_pending and accepted:
        await repo.update_group(db, ms["group_id"], {"status": "READY"})
    return await repo.get_membership(db, membership_id)


async def remove_member(db, group_id: str, target_user_id: str, actor_id: str) -> None:
    group = await _get_group_or_404(db, group_id)
    if actor_id != target_user_id:
        _assert_leader(group, actor_id)
    if target_user_id == group["leader_id"]:
        raise ConflictError("Leader cannot leave. Disband the group instead.", code="LEADER_CANNOT_LEAVE")
    await _get_open_cycle(db, group["cycle_id"])
    _assert_group_modifiable(group)
    ms = await repo.find_membership_by_user_group(db, group_id, target_user_id)
    if not ms or ms["status"] not in ("ACCEPTED", "INVITED"):
        raise NotFoundError("Member not found in group")
    action = "REMOVED" if actor_id != target_user_id else "LEFT"
    await repo.update_membership(db, str(ms["_id"]), {"status": action, "responded_at": _clock.now()})
    members = await repo.list_memberships_by_group(db, group_id)
    accepted = [m for m in members if m["status"] == "ACCEPTED"]
    no_pending = not any(m["status"] == "INVITED" for m in members)
    new_status = "READY" if (no_pending and accepted) else "FORMING"
    await repo.update_group(db, group_id, {"size": len(accepted), "status": new_status})


async def disband_group(db, group_id: str, leader_id: str) -> None:
    group = await _get_group_or_404(db, group_id)
    _assert_leader(group, leader_id)
    await _get_open_cycle(db, group["cycle_id"])
    _assert_group_modifiable(group)
    now = _clock.now()
    await repo.update_group(db, group_id, {"status": "DISBANDED", "size": 0})
    # Release all ACCEPTED / INVITED memberships so users can join or create other groups
    await db["memberships"].update_many(
        {"group_id": group_id, "status": {"$in": ["ACCEPTED", "INVITED"]}},
        {"$set": {"status": "LEFT", "updated_at": now}},
    )
    app = await repo.get_application_by_group(db, group["cycle_id"], group_id)
    if app and app.get("status") in ("DRAFT", "SUBMITTED"):
        await repo.update_application(db, str(app["_id"]), {"status": "WITHDRAWN"})


async def get_my_group(db, cycle_id: str, user_id: str) -> dict | None:
    user = await user_repo.find_user_by_id(db, user_id)
    cycle = await _get_cycle(db, cycle_id)
    if user:
        await assert_student_eligible_for_hostel(db, user, cycle["hostel_id"])

    ms = await repo.get_accepted_membership(db, cycle_id, user_id)
    if not ms:
        return None
    group = await repo.get_group(db, ms["group_id"])
    if not group or group.get("status") == "DISBANDED":
        return None
    members_raw = await repo.list_memberships_by_group(db, ms["group_id"])
    enriched = []
    for m in members_raw:
        if m["status"] in ("LEFT", "REMOVED", "DECLINED"):
            continue
        u = await user_repo.find_user_by_id(db, m["user_id"])
        acct = await repo.get_credit_account(db, m["user_id"])
        enriched.append({
            **m,
            "_id": str(m["_id"]),
            "name": u.get("name", "") if u else "",
            "roll_no": u.get("roll_no", "") if u else "",
            "email": u.get("email", "") if u else "",
            "accessibility_verified": u.get("accessibility_verified", False) if u else False,
            "credits": acct["credits"] if acct else 3,
        })
    app_doc = await repo.get_application_by_group(db, cycle_id, str(group["_id"]))
    return {
        **group,
        "_id": str(group["_id"]),
        "members": enriched,
        "application": {**app_doc, "_id": str(app_doc["_id"])} if app_doc else None,
    }


# ─────────────────────────── applications ────────────────────────────────────

async def _validate_choices(
    db, cycle: dict, group_size: int, ranked_choices: list[dict], fallback: str
) -> list[dict]:
    if fallback not in ("ANY_ELIGIBLE", "NONE"):
        raise ValidationError("fallback must be ANY_ELIGIBLE or NONE")
    if len(ranked_choices) > 10:
        raise ValidationError("Maximum 10 ranked choices allowed")

    cycle_id = str(cycle["_id"])
    fill_rule = cycle.get("policy", {}).get("fill_rule", "EXACT")
    seen_targets: set[tuple] = set()
    normalized: list[dict] = []

    for idx, ch in enumerate(ranked_choices, start=1):
        kind = ch.get("kind", "ROOM")
        if kind == "ROOM":
            rid = ch.get("room_id")
            if not rid:
                raise ValidationError(f"Choice #{idx} is missing room_id")
            if ("ROOM", rid) in seen_targets:
                raise ValidationError(f"Duplicate room choice at rank {idx}")
            seen_targets.add(("ROOM", rid))
            inv = await db["room_inventory"].find_one({"cycle_id": cycle_id, "room_id": rid})
            if not inv or inv.get("status") == "BLOCKED":
                raise ConflictError(f"Room {rid} is not available in this release", code="ROOM_NOT_ELIGIBLE")
            cap = int(inv["capacity"])
            if (fill_rule == "EXACT" and cap != group_size) or (fill_rule == "AT_MOST" and group_size > cap):
                raise ConflictError(
                    f"Room capacity ({cap}) does not match group size ({group_size})",
                    code="ROOM_NOT_ELIGIBLE",
                )
            normalized.append({"kind": "ROOM", "room_id": rid, "rank": idx})
        elif kind == "FLOOR":
            fno = ch.get("floor_no")
            hid = ch.get("hostel_id") or cycle["hostel_id"]
            if fno is None:
                raise ValidationError(f"Floor choice #{idx} is missing floor_no")
            fno = int(fno)
            if ("FLOOR", hid, fno) in seen_targets:
                raise ValidationError(f"Duplicate floor choice at rank {idx}")
            seen_targets.add(("FLOOR", hid, fno))
            if hid != cycle["hostel_id"]:
                raise ConflictError("Floor hostel mismatch for cycle", code="ROOM_NOT_ELIGIBLE")
            invs = await cat_repo.list_inventory(db, cycle_id, hostel_id=hid, floor_no=fno)
            fitting = [
                i for i in invs
                if i.get("status") != "BLOCKED"
                and (
                    (fill_rule == "EXACT" and int(i["capacity"]) == group_size)
                    or (fill_rule == "AT_MOST" and group_size <= int(i["capacity"]))
                )
            ]
            if not fitting:
                raise ConflictError(
                    f"Floor {fno} has no eligible rooms for group size {group_size}",
                    code="ROOM_NOT_ELIGIBLE",
                )
            normalized.append({"kind": "FLOOR", "hostel_id": hid, "floor_no": fno, "rank": idx})
        else:
            raise ValidationError(f"Invalid choice kind: {kind}")

    return normalized


async def _compute_snapshot_and_tier(db, cycle: dict, member_ids: list[str]) -> tuple[dict, float, int]:
    p = get_policy(cycle.get("policy", {}))
    c_init = p.get("c_init", 3)
    gw_policy = p.get("group_weight_policy", "MEAN")
    member_credits: list[int] = []
    member_rows: list[dict] = []
    has_accessibility = False
    for uid in member_ids:
        acct = await repo.get_credit_account(db, uid)
        c = acct["credits"] if acct else c_init
        member_credits.append(c)
        member_rows.append({"user_id": uid, "credits": c})
        u = await user_repo.find_user_by_id(db, uid)
        if u and u.get("accessibility_verified"):
            has_accessibility = True
    w = group_weight(member_credits, gw_policy)
    tier = 0 if has_accessibility else 1
    return {"members": member_rows, "group_policy": gw_policy, "weight": w}, w, tier


async def save_application(
    db,
    group_id: str,
    cycle_id: str,
    ranked_choices: list[dict],
    fallback: str,
    leader_id: str,
    version: int | None = None,
) -> dict:
    group = await _get_group_or_404(db, group_id)
    _assert_leader(group, leader_id)
    _assert_group_modifiable(group)
    cycle = await _get_open_cycle(db, cycle_id)
    if group["cycle_id"] != cycle_id:
        raise NotFoundError("Group does not belong to this cycle")

    members = await repo.list_memberships_by_group(db, group_id)
    member_ids = [m["user_id"] for m in members if m["status"] == "ACCEPTED"]
    group_size = len(member_ids) or group.get("size", 1)

    normalized_choices = await _validate_choices(db, cycle, group_size, ranked_choices, fallback)
    snapshot, weight, tier = await _compute_snapshot_and_tier(db, cycle, member_ids)

    existing = await repo.get_application_by_group(db, cycle_id, group_id)
    now = _clock.now()
    # Keep SUBMITTED if already submitted & ready, otherwise DRAFT until explicit submit
    next_status = "SUBMITTED" if (existing and existing.get("status") == "SUBMITTED") else "DRAFT"

    if existing:
        if version is not None and existing.get("version", 0) != version:
            raise ConflictError("Application was modified by another request", code="VERSION_CONFLICT")
        await repo.update_application(db, str(existing["_id"]), {
            "ranked_choices": normalized_choices,
            "fallback": fallback,
            "member_ids": member_ids,
            "group_size": group_size,
            "credit_snapshot": snapshot,
            "weight": weight,
            "tier": tier,
            "status": next_status,
            "version": existing.get("version", 0) + 1,
        })
        return await repo.get_application(db, str(existing["_id"]))

    app_id = await repo.create_application(db, {
        "cycle_id": cycle_id,
        "group_id": group_id,
        "member_ids": member_ids,
        "group_size": group_size,
        "ranked_choices": normalized_choices,
        "fallback": fallback,
        "credit_snapshot": snapshot,
        "weight": weight,
        "tier": tier,
        "status": next_status,
        "submitted_at": now if next_status == "SUBMITTED" else None,
        "version": 1,
    })
    return await repo.get_application(db, app_id)


async def submit_application(
    db,
    group_id: str,
    cycle_id: str,
    leader_id: str,
    ranked_choices: list[dict] | None = None,
    fallback: str | None = None,
) -> dict:
    group = await _get_group_or_404(db, group_id)
    _assert_leader(group, leader_id)
    cycle = await _get_open_cycle(db, cycle_id)
    _assert_group_modifiable(group)

    members = await repo.list_memberships_by_group(db, group_id)
    pending = [m for m in members if m["status"] == "INVITED"]
    if pending:
        raise ConflictError("All members must accept before submitting", code="GROUP_NOT_READY")

    member_ids = [m["user_id"] for m in members if m["status"] == "ACCEPTED"]
    if not member_ids:
        raise ConflictError("Group has no accepted members", code="GROUP_NOT_READY")
    group_size = len(member_ids)

    app = await repo.get_application_by_group(db, cycle_id, group_id)
    choices_to_use = ranked_choices if ranked_choices is not None else (app.get("ranked_choices", []) if app else [])
    fallback_to_use = fallback if fallback is not None else (app.get("fallback", "NONE") if app else "NONE")

    if not choices_to_use:
        raise ValidationError("At least 1 ranked room or floor preference is required to submit")

    normalized_choices = await _validate_choices(db, cycle, group_size, choices_to_use, fallback_to_use)
    snapshot, weight, tier = await _compute_snapshot_and_tier(db, cycle, member_ids)
    now = _clock.now()

    if app:
        await repo.update_application(db, str(app["_id"]), {
            "ranked_choices": normalized_choices,
            "fallback": fallback_to_use,
            "member_ids": member_ids,
            "group_size": group_size,
            "credit_snapshot": snapshot,
            "weight": weight,
            "tier": tier,
            "status": "SUBMITTED",
            "submitted_at": now,
            "version": app.get("version", 0) + 1,
        })
        app_id = str(app["_id"])
    else:
        app_id = await repo.create_application(db, {
            "cycle_id": cycle_id,
            "group_id": group_id,
            "member_ids": member_ids,
            "group_size": group_size,
            "ranked_choices": normalized_choices,
            "fallback": fallback_to_use,
            "credit_snapshot": snapshot,
            "weight": weight,
            "tier": tier,
            "status": "SUBMITTED",
            "submitted_at": now,
            "version": 1,
        })

    await repo.update_group(db, group_id, {"status": "SUBMITTED", "size": group_size})
    return await repo.get_application(db, app_id)


async def withdraw_application(db, group_id: str, cycle_id: str, leader_id: str) -> None:
    group = await _get_group_or_404(db, group_id)
    _assert_leader(group, leader_id)
    await _get_open_cycle(db, cycle_id)
    app = await repo.get_application_by_group(db, cycle_id, group_id)
    if not app:
        raise NotFoundError("No application found")
    await repo.update_application(db, str(app["_id"]), {"status": "WITHDRAWN"})
    await repo.update_group(db, group_id, {"status": "READY"})


# ─────────────────────────── helpers ─────────────────────────────────────────

async def _get_open_cycle(db, cycle_id: str) -> dict:
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    if cycle["status"] in ("DRAFT", "SCHEDULED"):
        raise ConflictError("Application window has not opened yet", code="WINDOW_NOT_OPEN")
    if cycle["status"] != "APPLICATIONS_OPEN":
        raise ConflictError("Application window is closed", code="WINDOW_CLOSED")
    return cycle


async def _get_cycle(db, cycle_id: str) -> dict:
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    return cycle


async def _get_group_or_404(db, group_id: str) -> dict:
    group = await repo.get_group(db, group_id)
    if not group:
        raise NotFoundError("Group not found")
    return group


def _assert_leader(group: dict, user_id: str):
    if group.get("leader_id") != user_id:
        raise ForbiddenError("Only the group leader can perform this action")


def _assert_group_modifiable(group: dict):
    if group.get("status") in ("LOCKED", "DISBANDED"):
        raise ConflictError("Group cannot be modified", code="GROUP_LOCKED")
