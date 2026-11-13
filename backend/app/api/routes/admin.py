"""Admin routes: users, role grants, reports, audit logs."""

from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import (
    current_admin,
    current_auditor,
    current_super_admin,
    current_warden,
    get_db,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.scope import assert_staff_scope, filter_hostel_ids_for_user
from app.core import clock as _clock
from app.fairness.engine import (
    average_rank,
    group_vs_solo_success,
    jain_index,
    success_by_credit_band,
    top_k_rate,
)
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.repositories import users as user_repo
from app.services import overview_service, user_service

router = APIRouter(tags=["admin"])

_SENSITIVE_USER_FIELDS = {"password_hash", "activation_token_hash", "reset_token_hash"}


def _safe_user(doc: dict, credits: int | None = None) -> dict:
    out = {k: v for k, v in doc.items() if k not in _SENSITIVE_USER_FIELDS}
    out["_id"] = str(doc["_id"])
    if credits is not None:
        out["credits"] = credits
    return out


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/admin/users")
async def list_users(
    role: str | None = None,
    status: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
    user=Depends(current_admin),
    db=Depends(get_db),
):
    allowed = filter_hostel_ids_for_user(user)
    hostel_filter = allowed if (allowed is not None and role in (None, "STUDENT")) else None
    users = await user_repo.list_users(
        db, skip=skip, limit=limit, role=role, status=status, search=search, hostel_ids=hostel_filter
    )
    return [_safe_user(u) for u in users]


@router.get("/warden/users")
async def list_warden_students(
    search: str | None = None,
    accessibility_verified: bool | None = None,
    skip: int = 0,
    limit: int = 100,
    user=Depends(current_warden),
    db=Depends(get_db),
):
    """Scoped student directory for Wardens (used for Accessibility verification queue)."""
    allowed = filter_hostel_ids_for_user(user)
    users = await user_repo.list_users(
        db, skip=skip, limit=limit, role="STUDENT", search=search, hostel_ids=allowed
    )
    if accessibility_verified is not None:
        users = [u for u in users if bool(u.get("accessibility_verified")) == accessibility_verified]
    return [_safe_user(u) for u in users]


@router.post("/admin/users/import")
async def import_students(
    file: UploadFile = File(...),
    user=Depends(current_super_admin),
    db=Depends(get_db),
):
    content = await file.read()
    res = await user_service.import_students_csv(db, content.decode("utf-8-sig"))
    await repo.create_audit_log(db, {
        "actor_id": str(user["_id"]),
        "role": user["role"],
        "action": "IMPORT_STUDENTS_CSV",
        "target_type": "user",
        "target_id": "bulk",
        "before": None,
        "after": {"created": res["created"], "updated": res["updated"], "errors": len(res["errors"])},
        "request_id": "",
        "ip": "",
    })
    return {
        "created": res["created"],
        "updated": res["updated"],
        "errors": len(res["errors"]),
        "details": res["errors"][:20],
        "activation_tokens": res.get("activation_tokens", []),
    }


@router.post("/admin/role-grants")
async def grant_role(body: dict, user=Depends(current_admin), db=Depends(get_db)):
    return await user_service.grant_role_by_email(
        db,
        email=body.get("email", ""),
        role=body.get("role", ""),
        hostel_ids=body.get("hostel_ids", []),
        actor=user,
    )


@router.get("/admin/role-grants")
async def list_role_grants(
    status: str | None = None,
    email: str | None = None,
    user=Depends(current_admin),
    db=Depends(get_db),
):
    grants = await user_repo.list_role_grants(db, status=status, email=email)
    return [{**g, "_id": str(g["_id"])} for g in grants]


@router.delete("/admin/role-grants/{grant_id}")
async def revoke_role_grant(
    grant_id: str,
    user=Depends(current_super_admin),
    db=Depends(get_db),
):
    grant = await db["role_grants"].find_one({"_id": ObjectId(grant_id)})
    if not grant:
        raise NotFoundError("Role grant not found")
    # Protect against locking out the last active SUPER_ADMIN
    if grant.get("role") == "SUPER_ADMIN":
        count = await db["users"].count_documents({"role": "SUPER_ADMIN", "status": "ACTIVE"})
        if count <= 1:
            raise ConflictError("Cannot revoke the last active SUPER_ADMIN", code="LAST_SUPER_ADMIN")

    await user_repo.revoke_grant(db, grant_id, str(user["_id"]), _clock.now())
    if grant.get("applied_user_id") and str(user["_id"]) != grant["applied_user_id"]:
        await user_repo.update_user(db, grant["applied_user_id"], {
            "role": "STUDENT",
            "managed_hostel_ids": [],
        })
        await user_repo.bump_token_version(db, grant["applied_user_id"])

    await repo.create_audit_log(db, {
        "actor_id": str(user["_id"]),
        "role": user["role"],
        "action": "REVOKE_ROLE_GRANT",
        "target_type": "role_grant",
        "target_id": grant_id,
        "before": {"status": grant.get("status"), "role": grant.get("role")},
        "after": {"status": "REVOKED"},
        "request_id": "",
        "ip": "",
    })
    return {"message": "Grant revoked"}


@router.put("/admin/users/{user_id}/hostels")
async def update_user_hostels(
    user_id: str,
    body: dict,
    user=Depends(current_super_admin),
    db=Depends(get_db),
):
    target = await user_repo.find_user_by_id(db, user_id)
    if not target:
        raise NotFoundError("User not found")
    update: dict = {}
    if "hostel_ids" in body:
        for hid in body["hostel_ids"]:
            if not await cat_repo.get_hostel(db, hid):
                raise NotFoundError(f"Hostel {hid} not found")
        update["hostel_ids"] = body["hostel_ids"]
    if "managed_hostel_ids" in body:
        for hid in body["managed_hostel_ids"]:
            if not await cat_repo.get_hostel(db, hid):
                raise NotFoundError(f"Hostel {hid} not found")
        update["managed_hostel_ids"] = body["managed_hostel_ids"]
    if update:
        await user_repo.update_user(db, user_id, update)
        await user_repo.bump_token_version(db, user_id)
        await repo.create_audit_log(db, {
            "actor_id": str(user["_id"]),
            "role": user["role"],
            "action": "UPDATE_USER_HOSTELS",
            "target_type": "user",
            "target_id": user_id,
            "before": {
                "hostel_ids": target.get("hostel_ids", []),
                "managed_hostel_ids": target.get("managed_hostel_ids", []),
            },
            "after": update,
            "request_id": "",
            "ip": "",
        })
    return {"message": "Hostel assignments updated"}


@router.put("/admin/users/{user_id}/enable")
async def enable_user(user_id: str, user=Depends(current_admin), db=Depends(get_db)):
    target = await user_repo.find_user_by_id(db, user_id)
    if not target:
        raise NotFoundError("User not found")
    await user_repo.update_user(db, user_id, {"status": "ACTIVE"})
    return {"message": "User enabled"}


@router.put("/admin/users/{user_id}/disable")
async def disable_user(user_id: str, user=Depends(current_admin), db=Depends(get_db)):
    target = await user_repo.find_user_by_id(db, user_id)
    if not target:
        raise NotFoundError("User not found")
    if target.get("role") == "SUPER_ADMIN":
        if user.get("role") != "SUPER_ADMIN":
            raise ForbiddenError("Only SUPER_ADMIN can disable a SUPER_ADMIN")
        count = await db["users"].count_documents({"role": "SUPER_ADMIN", "status": "ACTIVE"})
        if count <= 1:
            raise ConflictError("Cannot disable the last active SUPER_ADMIN", code="LAST_SUPER_ADMIN")
    await user_repo.update_user(db, user_id, {"status": "DISABLED"})
    await user_repo.bump_token_version(db, user_id)
    return {"message": "User disabled"}


@router.put("/admin/users/{user_id}/unlock")
async def unlock_user(user_id: str, user=Depends(current_admin), db=Depends(get_db)):
    target = await user_repo.find_user_by_id(db, user_id)
    if not target:
        raise NotFoundError("User not found")
    await user_repo.update_user(db, user_id, {"status": "ACTIVE", "locked_until": None, "failed_logins": 0})
    return {"message": "User unlocked"}


@router.put("/warden/users/{user_id}/accessibility")
async def verify_accessibility(
    user_id: str,
    body: dict,
    user=Depends(current_warden),
    db=Depends(get_db),
):
    target = await user_repo.find_user_by_id(db, user_id)
    if not target:
        raise NotFoundError("Student not found")
    allowed = filter_hostel_ids_for_user(user)
    if allowed is not None and not set(target.get("hostel_ids", [])).intersection(allowed):
        raise ForbiddenError("Student is outside your managed hostels", code="HOSTEL_SCOPE_DENIED")
    verified = bool(body.get("verified", False))
    await user_repo.update_user(db, user_id, {"accessibility_verified": verified})
    await repo.create_audit_log(db, {
        "actor_id": str(user["_id"]),
        "role": user["role"],
        "action": "VERIFY_ACCESSIBILITY",
        "target_type": "user",
        "target_id": user_id,
        "before": {"accessibility_verified": target.get("accessibility_verified", False)},
        "after": {"accessibility_verified": verified, "note": body.get("note", "")},
        "request_id": "",
        "ip": "",
    })
    return {"message": "Accessibility status updated", "accessibility_verified": verified}


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/reports/overview")
async def operations_overview(user=Depends(current_warden), db=Depends(get_db)):
    """Live operations snapshot for the caller's hostels: per-cycle KPIs + items needing attention."""
    return await overview_service.build_overview(db, filter_hostel_ids_for_user(user))


@router.get("/reports/occupancy")
async def occupancy_report(
    cycle_id: str | None = None,
    user=Depends(current_warden),
    db=Depends(get_db),
):
    allowed = filter_hostel_ids_for_user(user)
    if cycle_id:
        cycle = await cat_repo.get_cycle(db, cycle_id)
        if not cycle:
            raise NotFoundError("Cycle not found")
        assert_staff_scope(user, cycle["hostel_id"])
        counts = await cat_repo.count_inventory_by_status(db, cycle_id)
        inventory = await cat_repo.list_inventory(db, cycle_id)
    else:
        cycles = await cat_repo.list_cycles(db, allowed)
        cycle_ids = [str(c["_id"]) for c in cycles]
        inventory = await db["room_inventory"].find(
            {"cycle_id": {"$in": cycle_ids}} if cycle_ids else {"_id": None}
        ).to_list(length=5000)
        counts = {"AVAILABLE": 0, "HELD": 0, "CONFIRMED": 0, "BLOCKED": 0}
        for inv in inventory:
            st = inv.get("status", "AVAILABLE")
            counts[st] = counts.get(st, 0) + 1

    hostels = await cat_repo.list_hostels(db)
    hostel_map = {str(h["_id"]): h for h in hostels}

    by_floor: dict = {}
    by_hostel: dict = {}
    total_beds = 0
    occupied_beds = 0
    held_beds = 0

    for inv in inventory:
        cap = int(inv.get("capacity", 1))
        st = inv.get("status", "AVAILABLE").lower()
        total_beds += cap
        if st == "confirmed":
            occupied_beds += cap
        elif st == "held":
            held_beds += cap

        fkey = f"floor_{inv['floor_no']}"
        by_floor.setdefault(fkey, {
            "floor_no": inv["floor_no"], "available": 0, "held": 0, "confirmed": 0, "blocked": 0,
            "total_beds": 0, "occupied_beds": 0, "held_beds": 0,
        })
        by_floor[fkey][st] = by_floor[fkey].get(st, 0) + 1
        by_floor[fkey]["total_beds"] += cap
        if st == "confirmed":
            by_floor[fkey]["occupied_beds"] += cap
        elif st == "held":
            by_floor[fkey]["held_beds"] += cap

        hid = inv["hostel_id"]
        hinfo = hostel_map.get(hid, {})
        by_hostel.setdefault(hid, {
            "hostel_id": hid,
            "hostel_name": hinfo.get("name", hid),
            "hostel_code": hinfo.get("code", ""),
            "total_beds": 0,
            "occupied_beds": 0,
            "held_beds": 0,
            "available_beds": 0,
        })
        by_hostel[hid]["total_beds"] += cap
        if st == "confirmed":
            by_hostel[hid]["occupied_beds"] += cap
        elif st == "held":
            by_hostel[hid]["held_beds"] += cap
        elif st == "available":
            by_hostel[hid]["available_beds"] += cap

    return {
        "total": counts,
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "held_beds": held_beds,
        "by_floor": by_floor,
        "by_hostel": list(by_hostel.values()),
    }


@router.get("/reports/fairness")
async def fairness_report(
    cycle_id: str | None = None,
    user=Depends(current_auditor),
    db=Depends(get_db),
):
    allowed = filter_hostel_ids_for_user(user)
    if cycle_id:
        cycle = await cat_repo.get_cycle(db, cycle_id)
        if not cycle:
            raise NotFoundError("Cycle not found")
        assert_staff_scope(user, cycle["hostel_id"])
        cycle_filter = {"cycle_id": cycle_id}
        cycles = [cycle]
    else:
        cycles = await cat_repo.list_cycles(db, allowed)
        cids = [str(c["_id"]) for c in cycles]
        cycle_filter = {"cycle_id": {"$in": cids}} if cids else {"cycle_id": "__none__"}

    allotments = await db["allotments"].find(cycle_filter).to_list(length=5000)
    confirmed = [a for a in allotments if a.get("status") == "CONFIRMED"]
    apps = await db["applications"].find(
        {**cycle_filter, "status": {"$ne": "WITHDRAWN"}}
    ).to_list(length=5000)

    total = len(apps)
    confirmed_count = sum(1 for a in apps if a.get("status") == "CONFIRMED")
    allotted_count = sum(1 for a in apps if a.get("status") in ("ALLOTTED", "CONFIRMED"))

    # Per-student binary outcome for Jain's fairness index + band analysis
    student_history = []
    group_outcomes = []
    student_success_map: dict[str, list[float]] = {}
    for a in apps:
        got = a.get("status") in ("ALLOTTED", "CONFIRMED")
        group_outcomes.append({"group_size": a.get("group_size", 1), "got_room": got})
        snap = (a.get("credit_snapshot") or {}).get("members", [])
        cred_map = {m["user_id"]: m.get("credits", 3) for m in snap}
        for uid in a.get("member_ids", []):
            student_history.append({"credits": cred_map.get(uid, 3), "got_room": got})
            student_success_map.setdefault(uid, []).append(1.0 if got else 0.0)

    per_student_rates = [sum(v) / len(v) for v in student_success_map.values()] if student_success_map else []
    jain_val = jain_index(per_student_rates)
    bands = success_by_credit_band(student_history)
    gvs = group_vs_solo_success(group_outcomes)

    rank_counts: dict[str, int] = {}
    for a in confirmed:
        r = str(a.get("rank_obtained", "fallback"))
        rank_counts[r] = rank_counts.get(r, 0) + 1

    demand_by_size: dict[int, int] = {}
    for a in apps:
        s = int(a.get("group_size", 1))
        demand_by_size[s] = demand_by_size.get(s, 0) + 1

    inv_rows = await db["room_inventory"].find(cycle_filter).to_list(length=5000)
    supply_by_cap: dict[int, int] = {}
    for inv in inv_rows:
        c = int(inv.get("capacity", 1))
        supply_by_cap[c] = supply_by_cap.get(c, 0) + 1

    all_sizes = sorted(set(demand_by_size.keys()) | set(supply_by_cap.keys()))
    demand_vs_supply = [
        {"size": s, "demand": demand_by_size.get(s, 0), "supply": supply_by_cap.get(s, 0)}
        for s in all_sizes
    ]

    credit_accounts = await db["credit_accounts"].find({}).to_list(length=5000)
    credit_hist: dict[int, int] = {}
    for acct in credit_accounts:
        c = int(acct.get("credits", 3))
        credit_hist[c] = credit_hist.get(c, 0) + 1

    return {
        "total_applications": total,
        "allotted": allotted_count,
        "confirmed": confirmed_count,
        "success_rate": confirmed_count / total if total else 0.0,
        "average_rank": average_rank(confirmed),
        "top_1_rate": top_k_rate(confirmed, k=1),
        "top_3_rate": top_k_rate(confirmed, k=3),
        "jain_index": jain_val,
        "success_by_band": [{"band": k, "success_rate": round(v, 4)} for k, v in bands.items()],
        "group_vs_solo": gvs,
        "rank_distribution": [
            {"rank": r, "count": cnt}
            for r, cnt in sorted(rank_counts.items(), key=lambda x: str(x[0]))
        ],
        "demand_vs_supply": demand_vs_supply,
        "credit_distribution": [
            {"credits": c, "count": cnt} for c, cnt in sorted(credit_hist.items())
        ],
    }


@router.get("/reports/rejections")
async def rejection_report(
    cycle_id: str | None = None,
    user=Depends(current_auditor),
    db=Depends(get_db),
):
    allowed = filter_hostel_ids_for_user(user)
    q: dict = {"status": {"$in": ["DECLINED", "EXPIRED", "CANCELLED", "REVOKED"]}}
    if cycle_id:
        cycle = await cat_repo.get_cycle(db, cycle_id)
        if not cycle:
            raise NotFoundError("Cycle not found")
        assert_staff_scope(user, cycle["hostel_id"])
        q["cycle_id"] = cycle_id
    elif allowed is not None:
        cycles = await cat_repo.list_cycles(db, allowed)
        q["cycle_id"] = {"$in": [str(c["_id"]) for c in cycles]}

    rows = await db["allotments"].find(q).to_list(length=5000)
    counts = {"DECLINED": 0, "EXPIRED": 0, "CANCELLED": 0, "REVOKED": 0}
    for r in rows:
        st = r.get("status")
        if st in counts:
            counts[st] += 1
    return {"total_released": len(rows), "by_status": counts}


@router.get("/admin/audit-logs")
async def get_audit_logs(
    actor_id: str | None = None,
    target_type: str | None = None,
    entity_type: str | None = None,
    action: str | None = None,
    skip: int = 0,
    limit: int = 50,
    user=Depends(current_auditor),
    db=Depends(get_db),
):
    ttype = target_type or entity_type
    logs = await repo.list_audit_logs(
        db, actor_id=actor_id, target_type=ttype, action=action, skip=skip, limit=limit
    )
    # Enrich actor emails
    actor_ids = list({ObjectId(log["actor_id"]) for log in logs if ObjectId.is_valid(log.get("actor_id", ""))})
    email_map: dict[str, str] = {}
    if actor_ids:
        async for u in db["users"].find({"_id": {"$in": actor_ids}}, {"email": 1}):
            email_map[str(u["_id"])] = u.get("email", "")
    return [
        {
            **log,
            "_id": str(log["_id"]),
            "actor_email": email_map.get(log.get("actor_id", ""), log.get("actor_id", "")),
        }
        for log in logs
    ]
