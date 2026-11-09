"""Allotment routes — NO payment."""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from app.api.deps import (
    current_admin,
    current_warden,
    get_client,
    get_current_user,
    get_db,
)
from app.core.errors import NotFoundError, ValidationError
from app.core.idempotency import check_idempotency, store_idempotency
from app.core.scope import assert_staff_scope, filter_hostel_ids_for_user
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.services import allotment_service

router = APIRouter(tags=["allotments"])


def _hash_body(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


@router.get("/cycles/{cycle_id}/allotments/mine")
async def get_my_allotment_for_cycle(
    cycle_id: str,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    ms = await repo.get_accepted_membership(db, cycle_id, str(user["_id"]))
    if not ms:
        return None
    app = await repo.get_application_by_group(db, cycle_id, ms["group_id"])
    if not app:
        return None
    allotment = await repo.get_latest_allotment_for_application(db, cycle_id, str(app["_id"]))
    return await allotment_service.serialize_allotment(db, allotment)


@router.get("/allotments/mine")
@router.get("/allotments/me")
async def get_my_latest_allotment(
    cycle_id: str | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    uid = str(user["_id"])
    if cycle_id:
        return await get_my_allotment_for_cycle(cycle_id, user, db)
    rows = await db["allotments"].find(
        {"members.user_id": uid}
    ).sort([("is_active", -1), ("created_at", -1)]).limit(1).to_list(length=1)
    if not rows:
        return None
    return await allotment_service.serialize_allotment(db, rows[0])


@router.get("/admin/allotments")
async def list_allotments(
    cycle_id: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 100,
    user=Depends(current_warden),
    db=Depends(get_db),
):
    q: dict = {}
    if cycle_id:
        cycle = await cat_repo.get_cycle(db, cycle_id)
        if not cycle:
            raise NotFoundError("Cycle not found")
        assert_staff_scope(user, cycle["hostel_id"])
        q["cycle_id"] = cycle_id
    else:
        allowed = filter_hostel_ids_for_user(user)
        if allowed is not None:
            cycles = await cat_repo.list_cycles(db, allowed)
            q["cycle_id"] = {"$in": [str(c["_id"]) for c in cycles]}
    if status:
        q["status"] = status

    rows = await db["allotments"].find(q).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    return [await allotment_service.serialize_allotment(db, a) for a in rows]


@router.post("/allotments/{allotment_id}/accept")
async def accept_allotment(
    allotment_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
    db=Depends(get_db),
    client=Depends(get_client),
):
    uid = str(user["_id"])
    req_hash = _hash_body({"op": "accept", "allotment_id": allotment_id})
    if idempotency_key:
        cached = await check_idempotency(db, uid, idempotency_key, req_hash)
        if cached:
            return JSONResponse(content=cached["response"], status_code=cached["status_code"])
    doc = await allotment_service.accept_allotment(db, client, allotment_id, uid)
    out = await allotment_service.serialize_allotment(db, doc)
    if idempotency_key:
        await store_idempotency(db, uid, idempotency_key, req_hash, json.loads(json.dumps(out, default=str)), 200)
    return out


@router.post("/allotments/{allotment_id}/decline")
async def decline_allotment(
    allotment_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
    db=Depends(get_db),
    client=Depends(get_client),
):
    uid = str(user["_id"])
    req_hash = _hash_body({"op": "decline", "allotment_id": allotment_id})
    if idempotency_key:
        cached = await check_idempotency(db, uid, idempotency_key, req_hash)
        if cached:
            return JSONResponse(content=cached["response"], status_code=cached["status_code"])
    doc = await allotment_service.decline_allotment(db, client, allotment_id, uid)
    out = await allotment_service.serialize_allotment(db, doc)
    if idempotency_key:
        await store_idempotency(db, uid, idempotency_key, req_hash, json.loads(json.dumps(out, default=str)), 200)
    return out


@router.post("/allotments/{allotment_id}/cancel")
async def cancel_allotment(
    allotment_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
    db=Depends(get_db),
    client=Depends(get_client),
):
    uid = str(user["_id"])
    req_hash = _hash_body({"op": "cancel", "allotment_id": allotment_id})
    if idempotency_key:
        cached = await check_idempotency(db, uid, idempotency_key, req_hash)
        if cached:
            return JSONResponse(content=cached["response"], status_code=cached["status_code"])
    doc = await allotment_service.cancel_allotment(db, client, allotment_id, uid)
    out = await allotment_service.serialize_allotment(db, doc)
    if idempotency_key:
        await store_idempotency(db, uid, idempotency_key, req_hash, json.loads(json.dumps(out, default=str)), 200)
    return out


@router.post("/admin/allotments/{allotment_id}/revoke")
async def revoke_allotment(
    allotment_id: str,
    body: dict,
    user=Depends(current_warden),
    db=Depends(get_db),
    client=Depends(get_client),
):
    reason = (body.get("reason") or "").strip()
    if len(reason) < 10:
        raise ValidationError("Reason must be at least 10 characters")
    existing = await repo.get_allotment(db, allotment_id)
    if not existing:
        raise NotFoundError("Allotment not found")
    cycle = await cat_repo.get_cycle(db, existing["cycle_id"])
    if cycle:
        assert_staff_scope(user, cycle["hostel_id"])
    doc = await allotment_service.revoke_allotment(db, client, allotment_id, reason, str(user["_id"]))
    return await allotment_service.serialize_allotment(db, doc)


@router.post("/admin/allotments/{allotment_id}/extend")
async def extend_hold(
    allotment_id: str,
    body: dict,
    user=Depends(current_warden),
    db=Depends(get_db),
):
    reason = (body.get("reason") or "").strip()
    if len(reason) < 10:
        raise ValidationError("Reason must be at least 10 characters")
    existing = await repo.get_allotment(db, allotment_id)
    if not existing:
        raise NotFoundError("Allotment not found")
    cycle = await cat_repo.get_cycle(db, existing["cycle_id"])
    if cycle:
        assert_staff_scope(user, cycle["hostel_id"])
    extra_hours = int(body.get("extra_hours", 24))
    doc = await allotment_service.extend_hold(db, allotment_id, reason, str(user["_id"]), extra_hours)
    return await allotment_service.serialize_allotment(db, doc)


@router.post("/admin/cycles/{cycle_id}/cascade")
async def trigger_cascade(
    cycle_id: str,
    user=Depends(current_admin),
    db=Depends(get_db),
    client=Depends(get_client),
):
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, cycle["hostel_id"])
    return await allotment_service.run_cascade(db, client, cycle_id, actor_id=str(user["_id"]))


@router.post("/admin/applications/{application_id}/assign")
async def manual_assign_application(
    application_id: str,
    body: dict,
    user=Depends(current_admin),
    db=Depends(get_db),
    client=Depends(get_client),
):
    cycle_id = body.get("cycle_id", "")
    room_id = body.get("room_id", "")
    if not cycle_id or not room_id:
        raise ValidationError("cycle_id and room_id are required")
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, cycle["hostel_id"])
    doc = await allotment_service.manual_assign(db, client, cycle_id, application_id, room_id, str(user["_id"]))
    return await allotment_service.serialize_allotment(db, doc)
