"""Groups and applications routes."""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user, get_db
from app.core.errors import NotFoundError
from app.core.idempotency import check_idempotency, store_idempotency
from app.services import group_service

router = APIRouter(tags=["groups"])


def _hash_body(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _serialize(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    return {**doc, "_id": str(doc["_id"])}


@router.post("/cycles/{cycle_id}/groups")
async def create_group(
    cycle_id: str,
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    solo = bool(body.get("solo", False))
    name = body.get("name", "")
    group = await group_service.create_group(db, cycle_id, str(user["_id"]), name, solo)
    return _serialize(group)


@router.get("/cycles/{cycle_id}/groups/mine")
async def get_my_group(cycle_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    return await group_service.get_my_group(db, cycle_id, str(user["_id"]))


@router.get("/cycles/{cycle_id}/invites/mine")
async def get_my_invites(cycle_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    return await group_service.list_my_invites(db, cycle_id, str(user["_id"]))


@router.post("/groups/{group_id}/invites")
async def invite_member(
    group_id: str,
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    identifier = body.get("roll_no") or body.get("email") or body.get("identifier", "")
    ms = await group_service.invite_member(db, group_id, identifier, str(user["_id"]))
    return _serialize(ms)


@router.post("/invites/{membership_id}/accept")
async def accept_invite(
    membership_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    uid = str(user["_id"])
    req_hash = _hash_body({"op": "accept_invite", "id": membership_id})
    if idempotency_key:
        cached = await check_idempotency(db, uid, idempotency_key, req_hash)
        if cached:
            return JSONResponse(content=cached["response"], status_code=cached["status_code"])
    result = _serialize(await group_service.accept_invite(db, membership_id, uid))
    if idempotency_key:
        await store_idempotency(db, uid, idempotency_key, req_hash, json.loads(json.dumps(result, default=str)), 200)
    return result


@router.post("/invites/{membership_id}/decline")
async def decline_invite(
    membership_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    uid = str(user["_id"])
    req_hash = _hash_body({"op": "decline_invite", "id": membership_id})
    if idempotency_key:
        cached = await check_idempotency(db, uid, idempotency_key, req_hash)
        if cached:
            return JSONResponse(content=cached["response"], status_code=cached["status_code"])
    await group_service.decline_invite(db, membership_id, uid)
    resp = {"message": "Invite declined"}
    if idempotency_key:
        await store_idempotency(db, uid, idempotency_key, req_hash, resp, 200)
    return resp


@router.delete("/groups/{group_id}/members/{target_user_id}")
async def remove_member(
    group_id: str,
    target_user_id: str,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    await group_service.remove_member(db, group_id, target_user_id, str(user["_id"]))
    return {"message": "Member removed"}


@router.delete("/groups/{group_id}")
async def disband_group(group_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    await group_service.disband_group(db, group_id, str(user["_id"]))
    return {"message": "Group disbanded"}


@router.put("/groups/{group_id}/application")
async def save_application(
    group_id: str,
    body: dict,
    if_match: Optional[str] = Header(None, alias="If-Match"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cycle_id = body.get("cycle_id")
    if not cycle_id:
        grp = await group_service._get_group_or_404(db, group_id)
        cycle_id = grp["cycle_id"]
    ranked_choices = body.get("ranked_choices", [])
    fallback = body.get("fallback", "NONE")
    version = int(if_match) if if_match else body.get("version")
    app = await group_service.save_application(
        db, group_id, cycle_id, ranked_choices, fallback, str(user["_id"]), version
    )
    return _serialize(app)


@router.post("/groups/{group_id}/application/submit")
async def submit_application(
    group_id: str,
    body: dict | None = None,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    body = body or {}
    cycle_id = body.get("cycle_id")
    if not cycle_id:
        grp = await group_service._get_group_or_404(db, group_id)
        cycle_id = grp["cycle_id"]
    uid = str(user["_id"])
    req_hash = _hash_body({"op": "submit_app", "group_id": group_id, "cycle_id": cycle_id, "body": body})
    if idempotency_key:
        cached = await check_idempotency(db, uid, idempotency_key, req_hash)
        if cached:
            return JSONResponse(content=cached["response"], status_code=cached["status_code"])

    app = _serialize(await group_service.submit_application(
        db,
        group_id,
        cycle_id,
        uid,
        ranked_choices=body.get("ranked_choices"),
        fallback=body.get("fallback"),
    ))
    if idempotency_key:
        await store_idempotency(db, uid, idempotency_key, req_hash, json.loads(json.dumps(app, default=str)), 200)
    return app


@router.post("/groups/{group_id}/application/withdraw")
async def withdraw_application(
    group_id: str,
    body: dict | None = None,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    body = body or {}
    cycle_id = body.get("cycle_id")
    if not cycle_id:
        grp = await group_service._get_group_or_404(db, group_id)
        cycle_id = grp["cycle_id"]
    uid = str(user["_id"])
    req_hash = _hash_body({"op": "withdraw_app", "group_id": group_id, "cycle_id": cycle_id})
    if idempotency_key:
        cached = await check_idempotency(db, uid, idempotency_key, req_hash)
        if cached:
            return JSONResponse(content=cached["response"], status_code=cached["status_code"])

    await group_service.withdraw_application(db, group_id, cycle_id, uid)
    resp = {"message": "Application withdrawn"}
    if idempotency_key:
        await store_idempotency(db, uid, idempotency_key, req_hash, resp, 200)
    return resp


@router.get("/groups/{group_id}/application")
async def get_application(
    group_id: str,
    cycle_id: str | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    from app.repositories.core_repos import get_application_by_group, find_membership_by_user_group
    grp = await group_service._get_group_or_404(db, group_id)
    ms = await find_membership_by_user_group(db, group_id, str(user["_id"]))
    if user.get("role") == "STUDENT" and (not ms or ms["status"] != "ACCEPTED"):
        raise NotFoundError("Application not found")
    cid = cycle_id or grp["cycle_id"]
    app = await get_application_by_group(db, cid, group_id)
    if not app:
        raise NotFoundError("Application not found")
    return _serialize(app)
