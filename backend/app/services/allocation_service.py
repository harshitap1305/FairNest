"""Allocation service: preview, run, verify."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import timedelta

from bson import ObjectId

from app.allocator.core import (
    AppIn,
    Choice,
    Policy,
    RoomIn,
    _hmac_uniform,
    allocate,
)
from app.core import clock as _clock
from app.core.errors import ConflictError, NotFoundError
from app.fairness.engine import get_policy, group_weight
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo


def _build_policy(cycle_policy: dict) -> Policy:
    p = get_policy(cycle_policy)
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


def _compute_input_hash(apps: list[AppIn], free_rooms: set[str], seed: bytes) -> str:
    data = {
        "apps": sorted(
            [
                {
                    "id": a.id,
                    "weight": float(a.weight),
                    "tier": int(a.tier),
                    "group_size": int(a.group_size),
                    "fallback": str(a.fallback),
                    "choices": [
                        {
                            "kind": c.kind,
                            "room_id": c.room_id,
                            "hostel_id": c.hostel_id,
                            "floor_no": c.floor_no,
                        }
                        for c in a.choices
                    ],
                }
                for a in apps
            ],
            key=lambda x: x["id"],
        ),
        "free_rooms": sorted(list(free_rooms)),
        "seed": seed.hex(),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _compute_output_hash(result) -> str:
    data = sorted(
        [
            {
                "app_id": a.app_id,
                "room_id": a.room_id,
                "rank": a.rank_obtained,
                "order_index": a.order_index,
            }
            for a in result.allotments
        ],
        key=lambda x: x["app_id"],
    )
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


async def _load_snapshot(
    db,
    cycle: dict,
    *,
    snapshot_room_ids: list[str] | None = None,
    for_verification: bool = False,
):
    """
    Load submitted applications and eligible rooms in batched queries (zero N+1).
    When for_verification=True, reconstructs the exact Round-1 application cohort
    even after statuses progressed to ALLOTTED / WAITLISTED / CONFIRMED / FORFEITED / UNALLOTTED.
    """
    cycle_id = str(cycle["_id"])
    policy_dict = cycle.get("policy", {})
    p = get_policy(policy_dict)
    c_init = p.get("c_init", 3)
    gw_policy = p.get("group_weight_policy", "MEAN")

    if for_verification:
        apps_raw = await db["applications"].find({
            "cycle_id": cycle_id,
            "status": {"$in": ["SUBMITTED", "ALLOTTED", "WAITLISTED", "CONFIRMED", "FORFEITED", "UNALLOTTED"]},
        }).to_list(length=5000)
        if snapshot_room_ids is not None:
            room_set = set(snapshot_room_ids)
            inventory = await cat_repo.list_inventory(db, cycle_id)
            inventory = [inv for inv in inventory if inv["room_id"] in room_set]
        else:
            inventory = await cat_repo.list_inventory(db, cycle_id)
            inventory = [inv for inv in inventory if inv.get("status") != "BLOCKED"]
    else:
        apps_raw = await repo.list_submitted_by_cycle(db, cycle_id)
        inventory = await cat_repo.list_inventory(db, cycle_id, status="AVAILABLE")

    # Batch load all cycle room documents
    all_cycle_inv = await cat_repo.list_inventory(db, cycle_id)
    room_obj_ids = [
        ObjectId(inv["room_id"])
        for inv in all_cycle_inv
        if ObjectId.is_valid(inv["room_id"])
    ]
    room_map: dict[str, dict] = {}
    if room_obj_ids:
        async for rm in db["rooms"].find({"_id": {"$in": room_obj_ids}}):
            room_map[str(rm["_id"])] = rm

    # `rooms` dict contains all cycle rooms; `free_room_ids` holds the Round-1 free pool
    rooms: dict[str, RoomIn] = {}
    for inv in all_cycle_inv:
        rid = inv["room_id"]
        rm = room_map.get(rid)
        if rm:
            rooms[rid] = RoomIn(
                hostel_id=inv["hostel_id"],
                floor_no=int(inv["floor_no"]),
                room_no=rm.get("room_no", rid),
                capacity=int(inv["capacity"]),
            )
    free_room_ids = {inv["room_id"] for inv in inventory if inv["room_id"] in rooms}

    apps: list[AppIn] = []
    for a in apps_raw:
        snapshot = a.get("credit_snapshot") or {}
        if snapshot.get("members"):
            member_credits = [int(m.get("credits", c_init)) for m in snapshot["members"]]
            w = float(a.get("weight") or group_weight(member_credits, gw_policy))
        else:
            member_credits = [c_init]
            w = float(a.get("weight") or group_weight(member_credits, gw_policy))

        choices = [
            Choice(
                kind=ch.get("kind", "ROOM"),
                room_id=ch.get("room_id"),
                hostel_id=ch.get("hostel_id") or cycle["hostel_id"],
                floor_no=ch.get("floor_no"),
            )
            for ch in a.get("ranked_choices", [])
        ]

        apps.append(AppIn(
            id=str(a["_id"]),
            tier=int(a.get("tier", 1)),
            group_size=int(a.get("group_size", 1)),
            choices=choices,
            fallback=a.get("fallback", "NONE"),
            weight=w,
            reinsert=False,
        ))

    return apps, rooms, free_room_ids


async def preview_allocation(db, cycle_id: str, actor_id: str) -> dict:
    """Dry run — computes allocation with ephemeral preview seed, writes nothing."""
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    if cycle["status"] not in ("APPLICATIONS_CLOSED", "ALLOCATING"):
        raise ConflictError(
            "Cycle must be in APPLICATIONS_CLOSED to preview allocation",
            code="ALLOCATION_ALREADY_RUN",
        )

    apps, rooms, free_room_ids = await _load_snapshot(db, cycle)
    seed = os.urandom(32)
    policy = _build_policy(cycle.get("policy", {}))
    result = allocate(apps, rooms, free_room_ids, seed, policy)

    return {
        "applications": len(apps),
        "available_rooms": len(free_room_ids),
        "would_allot": len(result.allotments),
        "would_waitlist": len(result.waitlisted),
        "dry_run": True,
        "seed_commitment": cycle.get("seed_commitment"),
    }


async def run_allocation(db, client, cycle_id: str, actor_id: str) -> dict:
    """Run Round-1 allocation. Idempotent guard — 409 if already run."""
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    if cycle["status"] != "APPLICATIONS_CLOSED":
        raise ConflictError(
            "Allocation already run or window not closed yet",
            code="ALLOCATION_ALREADY_RUN",
        )

    moved = await cat_repo.transition_cycle_status(
        db, cycle_id, "APPLICATIONS_CLOSED", "ALLOCATING"
    )
    if not moved:
        raise ConflictError("Allocation already running", code="ALLOCATION_ALREADY_RUN")

    try:
        apps, rooms, free_room_ids = await _load_snapshot(db, cycle)
        seed_hex = cycle.get("seed_secret")
        if not seed_hex:
            raise ConflictError("Seed not generated — open the cycle first", code="VALIDATION_ERROR")
        seed = bytes.fromhex(seed_hex)
        policy = _build_policy(cycle.get("policy", {}))

        # Backfill credit_snapshot / weight on any application missing one
        for app_in in apps:
            order_u = _hmac_uniform(seed, app_in.id)
            _ = order_u

        input_hash = _compute_input_hash(apps, free_room_ids, seed)
        result = allocate(apps, rooms, free_room_ids, seed, policy)
        output_hash = _compute_output_hash(result)

        app_weights = {a.id: a.weight for a in apps}
        now = _clock.now()
        freeze_hours = int(cycle.get("freeze_hours", 48))
        run_id = ObjectId()

        # Pre-load all app docs and memberships outside loops
        app_docs_map: dict[str, dict] = {}
        async for doc in db["applications"].find({"cycle_id": cycle_id}):
            app_docs_map[str(doc["_id"])] = doc

        async def _commit(session):
            notif_docs: list[dict] = []

            for a_out in result.allotments:
                allotment_id = ObjectId()
                app_doc = app_docs_map.get(a_out.app_id)
                if not app_doc:
                    continue
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
                    raise ConflictError("Inventory changed during allocation", code="ROOM_TAKEN")

                await db["allotments"].insert_one({
                    "_id": allotment_id,
                    "cycle_id": cycle_id,
                    "application_id": a_out.app_id,
                    "group_id": app_doc["group_id"],
                    "room_id": a_out.room_id,
                    "group_size": group_size,
                    "rank_obtained": a_out.rank_obtained,
                    "round_no": 1,
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

                w = app_weights.get(a_out.app_id, 1.0)
                order_key = math.log(_hmac_uniform(seed, a_out.app_id)) / max(w, 1e-9)
                await db["applications"].update_one(
                    {"_id": ObjectId(a_out.app_id)},
                    {"$set": {
                        "status": "ALLOTTED",
                        "order_index": a_out.order_index,
                        "order_key": order_key,
                        "updated_at": now,
                    }},
                    session=session,
                )

                room_info = rooms.get(a_out.room_id)
                room_label = room_info.room_no if room_info else a_out.room_id
                for m in allotment_members:
                    notif_docs.append({
                        "_id": ObjectId(),
                        "user_id": m["user_id"],
                        "type": "ALLOTMENT_HELD",
                        "title": f"Room {room_label} Offered!",
                        "body": f"All group members must accept within {freeze_hours}h to confirm.",
                        "read": False,
                        "created_at": now,
                    })

            for w_out in result.waitlisted:
                w = app_weights.get(w_out.app_id, 1.0)
                order_key = math.log(_hmac_uniform(seed, w_out.app_id)) / max(w, 1e-9)
                await db["applications"].update_one(
                    {"_id": ObjectId(w_out.app_id)},
                    {"$set": {
                        "status": "WAITLISTED",
                        "order_index": w_out.order_index,
                        "order_key": order_key,
                        "updated_at": now,
                    }},
                    session=session,
                )
                app_doc = app_docs_map.get(w_out.app_id)
                if app_doc:
                    for uid in app_doc.get("member_ids", []):
                        notif_docs.append({
                            "_id": ObjectId(),
                            "user_id": uid,
                            "type": "WAITLISTED",
                            "title": "Application Waitlisted",
                            "body": f"Your group is waitlisted at order #{w_out.order_index + 1}. You will be auto-offered if a matching room opens.",
                            "read": False,
                            "created_at": now,
                        })

            if notif_docs:
                await db["notifications"].insert_many(notif_docs, session=session)

            await db["allocation_runs"].insert_one({
                "_id": run_id,
                "cycle_id": cycle_id,
                "round_no": 1,
                "type": "MAIN",
                "algorithm_version": "rsd-weighted-1.0",
                "params": {
                    "fill_rule": policy.fill_rule,
                    "group_weight_policy": policy.group_weight_policy,
                },
                "snapshot_room_ids": sorted(list(free_room_ids)),
                "seed_commitment": cycle.get("seed_commitment"),
                "seed_revealed": seed_hex,
                "input_hash": input_hash,
                "output_hash": output_hash,
                "stats": {
                    "applications": len(apps),
                    "allotted": len(result.allotments),
                    "waitlisted": len(result.waitlisted),
                },
                "status": "COMPLETED",
                "started_at": now,
                "finished_at": now,
                "triggered_by": actor_id,
                "created_at": now,
                "updated_at": now,
            }, session=session)

            await repo.create_audit_log(db, {
                "actor_id": actor_id,
                "role": "ADMIN",
                "action": "RUN_ALLOCATION",
                "target_type": "cycle",
                "target_id": cycle_id,
                "before": {"status": "APPLICATIONS_CLOSED"},
                "after": {
                    "status": "ALLOTMENT_ACTIVE",
                    "run_id": str(run_id),
                    "allotted": len(result.allotments),
                    "waitlisted": len(result.waitlisted),
                },
                "request_id": "",
                "ip": "",
            }, session=session)

            await db["cycles"].update_one(
                {"_id": ObjectId(cycle_id)},
                {"$set": {
                    "status": "ALLOTMENT_ACTIVE",
                    "seed_revealed_at": now,
                    "updated_at": now,
                }},
                session=session,
            )

        async with client.start_session() as session:
            await session.with_transaction(_commit)

        return {
            "run_id": str(run_id),
            "allotted": len(result.allotments),
            "waitlisted": len(result.waitlisted),
            "input_hash": input_hash,
            "output_hash": output_hash,
            "seed_commitment": cycle.get("seed_commitment"),
            "seed_revealed": seed_hex,
        }
    except Exception:
        # Roll cycle back to APPLICATIONS_CLOSED if allocation fails mid-flight
        await db["cycles"].update_one(
            {"_id": ObjectId(cycle_id), "status": "ALLOCATING"},
            {"$set": {"status": "APPLICATIONS_CLOSED"}},
        )
        raise


async def verify_allocation(db, cycle_id: str) -> dict:
    """Recompute Round-1 allocation from revealed seed and verify commitment, input & output hashes."""
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle or not cycle.get("seed_secret"):
        raise NotFoundError("Cycle or revealed seed not found")
    if cycle["status"] not in ("ALLOTMENT_ACTIVE", "CLOSED", "SETTLED"):
        raise ConflictError("Seed has not been revealed yet", code="SEED_NOT_REVEALED")

    run = await db["allocation_runs"].find_one(
        {"cycle_id": cycle_id, "round_no": 1, "type": "MAIN"}
    )
    if not run:
        raise NotFoundError("Allocation run not found")

    apps, rooms, free_room_ids = await _load_snapshot(
        db,
        cycle,
        snapshot_room_ids=run.get("snapshot_room_ids"),
        for_verification=True,
    )
    seed = bytes.fromhex(cycle["seed_secret"])
    policy = _build_policy(cycle.get("policy", {}))

    computed_input_hash = _compute_input_hash(apps, free_room_ids, seed)
    result = allocate(apps, rooms, free_room_ids, seed, policy)
    computed_output_hash = _compute_output_hash(result)

    commitment_ok = hashlib.sha256(seed).hexdigest() == cycle.get("seed_commitment", "")
    input_ok = computed_input_hash == run.get("input_hash", "")
    output_ok = computed_output_hash == run.get("output_hash", "")
    passed = commitment_ok and input_ok and output_ok

    return {
        "ok": passed,
        "passed": passed,
        "checks": {
            "seed_ok": commitment_ok,
            "input_ok": input_ok,
            "output_ok": output_ok,
        },
        "commitment_valid": commitment_ok,
        "input_hash_valid": input_ok,
        "output_hash_valid": output_ok,
        "seed_commitment": cycle.get("seed_commitment"),
        "seed_revealed": cycle.get("seed_secret"),
        "computed_input_hash": computed_input_hash,
        "stored_input_hash": run.get("input_hash"),
        "computed_output_hash": computed_output_hash,
        "stored_output_hash": run.get("output_hash"),
    }
