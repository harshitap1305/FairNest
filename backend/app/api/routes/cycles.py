"""Cycles routes: CRUD and state machine."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_db, get_current_user, current_admin, current_auditor, get_client
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.scope import assert_staff_scope, assert_student_scope, filter_hostel_ids_for_user
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.services import allocation_service, allotment_service, cycle_service

router = APIRouter(tags=["cycles"])


@router.get("/cycles")
async def list_cycles(
    status: str | None = None,
    hostel_id: str | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    allowed_hostels = filter_hostel_ids_for_user(user)
    if hostel_id:
        if allowed_hostels is not None and hostel_id not in allowed_hostels:
            return []
        query_hostels = [hostel_id]
    else:
        query_hostels = allowed_hostels

    cycles = await cat_repo.list_cycles(db, query_hostels, status=status)
    result = []
    for c in cycles:
        counts = await cat_repo.count_inventory_by_status(db, str(c["_id"]))
        stats = await cycle_service.get_cycle_stats(db, str(c["_id"]))
        result.append({
            **cycle_service.serialize_cycle(c),
            "room_counts": counts,
            "stats": stats,
        })
    return result


@router.get("/cycles/{cycle_id}")
async def get_cycle(cycle_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    if user.get("role") == "STUDENT":
        assert_student_scope(user, c["hostel_id"])
    else:
        assert_staff_scope(user, c["hostel_id"])
    counts = await cat_repo.count_inventory_by_status(db, cycle_id)
    stats = await cycle_service.get_cycle_stats(db, cycle_id)
    return {
        **cycle_service.serialize_cycle(c),
        "room_counts": counts,
        "stats": stats,
    }


@router.post("/admin/cycles")
async def create_cycle(body: dict, user=Depends(current_admin), db=Depends(get_db)):
    settings = get_settings()
    hostel_id = body.get("hostel_id", "")
    if not hostel_id:
        raise ValidationError("hostel_id is required")
    hostel = await cat_repo.get_hostel(db, hostel_id)
    if not hostel:
        raise NotFoundError("Hostel not found")
    assert_staff_scope(user, hostel_id)

    apply_open_at = cycle_service._parse_dt(body.get("apply_open_at"))
    apply_close_at = cycle_service._parse_dt(body.get("apply_close_at"))
    final_deadline_at = cycle_service._parse_dt(body.get("final_deadline_at"))

    cycle_id = await cat_repo.create_cycle(db, {
        "name": body["name"],
        "academic_year": body.get("academic_year", "2026-27"),
        "hostel_id": hostel_id,
        "status": "DRAFT",
        "apply_open_at": apply_open_at,
        "apply_close_at": apply_close_at,
        "final_deadline_at": final_deadline_at,
        "freeze_hours": int(body.get("freeze_hours", settings.FREEZE_HOURS_DEFAULT)),
        "policy": body.get("policy", {}),
        "room_ids": body.get("room_ids", []),
        "schedule_history": [],
        "created_by": str(user["_id"]),
    })
    await repo.create_audit_log(db, {
        "actor_id": str(user["_id"]),
        "role": user["role"],
        "action": "CREATE_CYCLE",
        "target_type": "cycle",
        "target_id": cycle_id,
        "before": None,
        "after": {"name": body["name"], "hostel_id": hostel_id},
        "request_id": "",
        "ip": "",
    })
    return {"id": cycle_id, "_id": cycle_id}


@router.put("/admin/cycles/{cycle_id}")
async def update_cycle(cycle_id: str, body: dict, user=Depends(current_admin), db=Depends(get_db)):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await cycle_service.update_cycle_impl(db, cycle_id, body, str(user["_id"]))


@router.post("/admin/cycles/{cycle_id}/schedule")
async def schedule_cycle(cycle_id: str, body: dict, user=Depends(current_admin), db=Depends(get_db)):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await cycle_service.schedule_cycle_impl(
        db,
        cycle_id,
        body.get("apply_open_at"),
        body.get("apply_close_at"),
        str(user["_id"]),
    )


@router.post("/admin/cycles/{cycle_id}/open")
async def open_cycle(
    cycle_id: str,
    user=Depends(current_admin),
    db=Depends(get_db),
    client=Depends(get_client),
):
    """Open a DRAFT or SCHEDULED cycle: snapshot inventory, generate seed, set APPLICATIONS_OPEN."""
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await cycle_service.open_cycle_impl(
        db, client, cycle_id, str(user["_id"]), allowed_from=("DRAFT", "SCHEDULED")
    )


@router.post("/admin/cycles/{cycle_id}/close-window")
async def close_window(
    cycle_id: str,
    user=Depends(current_admin),
    db=Depends(get_db),
    client=Depends(get_client),
):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await cycle_service.close_window_impl(db, client, cycle_id, str(user["_id"]))


@router.post("/admin/cycles/{cycle_id}/extend")
async def extend_window(cycle_id: str, body: dict, user=Depends(current_admin), db=Depends(get_db)):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await cycle_service.extend_window_impl(
        db, cycle_id, body.get("new_close_at"), body.get("reason", ""), str(user["_id"])
    )


@router.post("/admin/cycles/{cycle_id}/reopen")
async def reopen_cycle(cycle_id: str, body: dict, user=Depends(current_admin), db=Depends(get_db)):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await cycle_service.reopen_cycle_impl(
        db,
        cycle_id,
        body.get("apply_close_at") or body.get("new_close_at"),
        body.get("reason", ""),
        str(user["_id"]),
    )


@router.post("/admin/cycles/{cycle_id}/cancel")
async def cancel_cycle(cycle_id: str, body: dict, user=Depends(current_admin), db=Depends(get_db)):
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, cycle["hostel_id"])
    if cycle["status"] in ("ALLOCATING", "ALLOTMENT_ACTIVE", "CLOSED", "SETTLED", "CANCELLED"):
        raise ConflictError("Cannot cancel at this stage", code="VALIDATION_ERROR")
    await db["room_inventory"].update_many(
        {"cycle_id": cycle_id},
        {"$set": {"is_live": False, "status": "BLOCKED"}},
    )
    await cat_repo.update_cycle(db, cycle_id, {
        "status": "CANCELLED",
        "cancel_reason": body.get("reason", ""),
    })
    await repo.create_audit_log(db, {
        "actor_id": str(user["_id"]),
        "role": user["role"],
        "action": "CANCEL_CYCLE",
        "target_type": "cycle",
        "target_id": cycle_id,
        "before": {"status": cycle["status"]},
        "after": {"status": "CANCELLED", "reason": body.get("reason", "")},
        "request_id": "",
        "ip": "",
    })
    return {"message": "Cycle cancelled"}


@router.post("/admin/cycles/{cycle_id}/preview-allocation")
async def preview_allocation(cycle_id: str, user=Depends(current_admin), db=Depends(get_db)):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await allocation_service.preview_allocation(db, cycle_id, str(user["_id"]))


@router.post("/admin/cycles/{cycle_id}/allocate")
async def run_allocation(
    cycle_id: str,
    user=Depends(current_admin),
    db=Depends(get_db),
    client=Depends(get_client),
):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await allocation_service.run_allocation(db, client, cycle_id, str(user["_id"]))


@router.post("/admin/cycles/{cycle_id}/settle")
async def settle_cycle(
    cycle_id: str,
    user=Depends(current_admin),
    db=Depends(get_db),
    client=Depends(get_client),
):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await allotment_service.settle_cycle(db, client, cycle_id)


@router.get("/cycles/{cycle_id}/audit")
async def get_audit_data(cycle_id: str, user=Depends(current_auditor), db=Depends(get_db)):
    c = await cat_repo.get_cycle(db, cycle_id)
    if not c:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, c["hostel_id"])
    return await allocation_service.verify_allocation(db, cycle_id)
