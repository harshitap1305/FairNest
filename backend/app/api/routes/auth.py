"""Auth routes: login, activate, refresh, logout, sessions, password, profile, fairness."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_db, get_current_user
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.rate_limit import check_identifier, check_login, check_sensitive
from app.fairness.engine import delta_for_outcome, get_policy
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.repositories import users as user_repo
from app.services import auth_service

router = APIRouter(tags=["auth"])

REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, token: str):
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        max_age=settings.REFRESH_DAYS * 86400,
        path="/api/v1/auth",
    )


def _check_origin_csrf(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin:
        settings = get_settings()
        allowed = settings.cors_origins_list
        if allowed and origin not in allowed:
            raise ForbiddenError("Untrusted Origin", code="CSRF_ORIGIN_MISMATCH")


@router.post("/auth/login")
async def login(body: dict, request: Request, response: Response, db=Depends(get_db)):
    identifier = body.get("identifier", "")
    password = body.get("password", "")
    ip = request.client.host if request.client else ""
    check_login(ip or "unknown")
    if identifier:
        check_identifier(identifier.strip().lower())
    user_agent = request.headers.get("user-agent", "")
    access_token, refresh_opaque = await auth_service.login(db, identifier, password, ip, user_agent)
    _set_refresh_cookie(response, refresh_opaque)
    user = await user_repo.find_user_by_identifier(db, identifier)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": str(user["_id"]),
        "role": user["role"],
        "name": user.get("name", ""),
    }


@router.post("/auth/activate")
async def activate(body: dict, request: Request, db=Depends(get_db)):
    ip = request.client.host if request.client else ""
    check_sensitive(ip or "unknown")
    token = body.get("token", "")
    password = body.get("password", "")
    await auth_service.activate_account(db, token, password, ip=ip)
    return {"message": "Account activated successfully"}


@router.post("/auth/refresh")
async def refresh(request: Request, response: Response, db=Depends(get_db)):
    _check_origin_csrf(request)
    cookie_token = request.cookies.get(REFRESH_COOKIE)
    if not cookie_token:
        raise UnauthorizedError("No refresh token", code="TOKEN_INVALID")
    new_access, new_opaque = await auth_service.refresh_token(db, cookie_token)
    _set_refresh_cookie(response, new_opaque)
    return {"access_token": new_access, "token_type": "bearer"}


@router.post("/auth/logout")
async def logout(request: Request, response: Response, db=Depends(get_db)):
    _check_origin_csrf(request)
    cookie_token = request.cookies.get(REFRESH_COOKIE)
    if cookie_token:
        await auth_service.logout(db, cookie_token)
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return {"message": "Logged out"}


@router.post("/auth/logout-all")
async def logout_all(response: Response, user=Depends(get_current_user), db=Depends(get_db)):
    await auth_service.logout_all(db, str(user["_id"]))
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return {"message": "All sessions revoked"}


@router.get("/auth/sessions")
async def list_sessions(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    return await auth_service.list_sessions(
        db, str(user["_id"]), current_refresh_token=request.cookies.get(REFRESH_COOKIE)
    )


@router.get("/me/security-activity")
async def get_security_activity(limit: int = 20, user=Depends(get_current_user), db=Depends(get_db)):
    """Sign-ins, failed attempts and password/session changes on the caller's account."""
    return await auth_service.list_security_activity(db, str(user["_id"]), limit=limit)


@router.delete("/auth/sessions/{family_id}")
async def revoke_session(family_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    revoked = await auth_service.revoke_session(db, str(user["_id"]), family_id)
    if not revoked:
        raise NotFoundError("Session not found")
    return {"message": "Session revoked"}


@router.post("/auth/forgot")
async def forgot_password(body: dict, request: Request, db=Depends(get_db)):
    ip = request.client.host if request.client else ""
    check_sensitive(ip or "unknown")
    await auth_service.forgot_password(db, body.get("email", ""))
    return {"message": "If that email exists, a reset link has been sent"}


@router.post("/auth/reset")
async def reset_password(body: dict, request: Request, db=Depends(get_db)):
    ip = request.client.host if request.client else ""
    check_sensitive(ip or "unknown")
    new_pw = body.get("new_password") or body.get("password", "")
    await auth_service.reset_password(db, body.get("token", ""), new_pw, ip=ip)
    return {"message": "Password reset successfully"}


@router.post("/auth/change-password")
async def change_password(body: dict, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    ip = request.client.host if request.client else ""
    old_pw = body.get("old_password") or body.get("current_password", "")
    new_pw = body.get("new_password") or body.get("password", "")
    await auth_service.change_password(db, str(user["_id"]), old_pw, new_pw, ip=ip)
    return {"message": "Password changed"}


@router.get("/me")
async def get_me(user=Depends(get_current_user), db=Depends(get_db)):
    settings = get_settings()
    acct = await repo.get_credit_account(db, str(user["_id"]))
    return {
        "id": str(user["_id"]),
        "roll_no": user.get("roll_no"),
        "email": user.get("email"),
        "name": user.get("name"),
        "role": user.get("role"),
        "hostel_ids": user.get("hostel_ids", []),
        "managed_hostel_ids": user.get("managed_hostel_ids", []),
        "status": user.get("status"),
        "gender": user.get("gender"),
        "year": user.get("year"),
        "program": user.get("program"),
        "accessibility_verified": user.get("accessibility_verified", False),
        "credits": acct["credits"] if acct else settings.C_INIT,
        "last_login_at": str(user["last_login_at"]) if user.get("last_login_at") else None,
    }


@router.get("/me/credits")
async def get_my_credits(
    skip: int = 0, limit: int = 50,
    user=Depends(get_current_user), db=Depends(get_db)
):
    settings = get_settings()
    acct = await repo.get_credit_account(db, str(user["_id"]))
    ledger = await repo.get_ledger(db, str(user["_id"]), skip, limit)
    return {
        "credits": acct["credits"] if acct else settings.C_INIT,
        "ledger": [{**e, "_id": str(e["_id"])} for e in ledger],
    }


@router.get("/me/fairness")
async def get_my_fairness(
    cycle_id: str | None = None,
    user=Depends(get_current_user), db=Depends(get_db)
):
    """Per-student fairness explanation: weight, tier, order position, and choice breakdown."""
    settings = get_settings()
    user_id = str(user["_id"])
    acct = await repo.get_credit_account(db, user_id)
    current_credits = acct["credits"] if acct else settings.C_INIT

    cycle = None
    app_doc = None
    if cycle_id:
        cycle = await cat_repo.get_cycle(db, cycle_id)
        if not cycle:
            raise NotFoundError("Cycle not found")
        if user.get("role") == "STUDENT" and cycle["hostel_id"] not in user.get("hostel_ids", []):
            raise NotFoundError("Cycle not found")
        ms = await repo.get_accepted_membership(db, cycle_id, user_id)
        if ms:
            app_doc = await repo.get_application_by_group(db, cycle_id, ms["group_id"])
    else:
        # Pick the most recent cycle the student applied to, else most recent visible cycle
        apps = await db["applications"].find(
            {"member_ids": user_id}
        ).sort("updated_at", -1).limit(1).to_list(length=1)
        if apps:
            app_doc = apps[0]
            cycle = await cat_repo.get_cycle(db, app_doc["cycle_id"])
        else:
            hostel_ids = user.get("hostel_ids", []) if user.get("role") == "STUDENT" else None
            cycles = await cat_repo.list_cycles(db, hostel_ids)
            cycle = cycles[0] if cycles else None

    if not cycle:
        return {
            "credits": current_credits,
            "policy": get_policy({}),
            "cycle": None,
            "application": None,
            "allotment": None,
            "choice_explanations": [],
        }

    cid = str(cycle["_id"])
    p = get_policy(cycle.get("policy", {}))

    if not app_doc:
        return {
            "credits": current_credits,
            "policy": p,
            "cycle": {"_id": cid, "name": cycle["name"], "status": cycle["status"]},
            "application": None,
            "allotment": None,
            "choice_explanations": [],
        }

    allotment = await repo.get_latest_allotment_for_application(db, cid, str(app_doc["_id"]))
    total_applicants = await db["applications"].count_documents(
        {"cycle_id": cid, "status": {"$ne": "WITHDRAWN"}}
    )

    choice_explanations = []
    choices = app_doc.get("ranked_choices", [])
    obtained_rank = allotment.get("rank_obtained") if allotment else None

    for idx, ch in enumerate(choices, start=1):
        kind = ch.get("kind", "ROOM")
        if kind == "ROOM" and ch.get("room_id"):
            room = await cat_repo.get_room(db, ch["room_id"])
            inv = await cat_repo.get_inventory(db, cid, ch["room_id"])
            room_label = room["room_no"] if room else ch["room_id"]
            if obtained_rank == idx:
                reason = "Allotted at this preference"
            elif inv and inv.get("status") == "BLOCKED":
                reason = "Room blocked / unavailable at allocation time"
            elif inv and inv.get("status") in ("HELD", "CONFIRMED"):
                reason = "Taken by a higher-ordered application"
            else:
                reason = "Not reached or unavailable"
            choice_explanations.append({
                "rank": idx,
                "kind": "ROOM",
                "target": f"Room {room_label}",
                "status": "MATCHED" if obtained_rank == idx else "SKIPPED",
                "reason": reason,
            })
        elif kind == "FLOOR":
            floor_no = ch.get("floor_no")
            invs = await cat_repo.list_inventory(db, cid, hostel_id=cycle["hostel_id"], floor_no=floor_no)
            if obtained_rank == idx:
                reason = "Allotted a room on this floor"
            elif not invs or all(i.get("status") == "BLOCKED" for i in invs):
                reason = f"Floor {floor_no} had no available fitting rooms at allocation time"
            else:
                reason = "All matching rooms on this floor were taken earlier in order"
            choice_explanations.append({
                "rank": idx,
                "kind": "FLOOR",
                "target": f"Floor {floor_no}",
                "status": "MATCHED" if obtained_rank == idx else "SKIPPED",
                "reason": reason,
            })

    # Expected delta summary
    expected_delta = 0
    expected_event = ""
    if allotment:
        st = allotment["status"]
        if st == "CONFIRMED":
            expected_delta, expected_event = delta_for_outcome(p, "CONFIRMED", obtained_rank, len(choices))
        elif st == "HELD":
            expected_delta, expected_event = delta_for_outcome(p, "CONFIRMED", obtained_rank, len(choices))
        elif st in ("DECLINED", "EXPIRED"):
            expected_delta, expected_event = delta_for_outcome(p, "FORFEITED")
        elif st == "CANCELLED":
            expected_delta, expected_event = delta_for_outcome(p, "LATE_CANCELLED")
        elif st == "REVOKED":
            expected_delta, expected_event = delta_for_outcome(p, "REVOKED")
    elif app_doc["status"] == "UNALLOTTED":
        expected_delta, expected_event = delta_for_outcome(p, "UNALLOTTED")
    elif app_doc["status"] == "FORFEITED":
        expected_delta, expected_event = delta_for_outcome(p, "FORFEITED")

    allotment_summary = None
    if allotment:
        room_doc = await cat_repo.get_room(db, allotment["room_id"])
        allotment_summary = {
            "_id": str(allotment["_id"]),
            "status": allotment["status"],
            "room_id": allotment["room_id"],
            "room_no": room_doc.get("room_no", "") if room_doc else "",
            "floor_no": room_doc.get("floor_no") if room_doc else None,
            "rank_obtained": allotment.get("rank_obtained"),
            "round_no": allotment.get("round_no", 1),
        }

    return {
        "credits": current_credits,
        "policy": p,
        "cycle": {"_id": cid, "name": cycle["name"], "status": cycle["status"]},
        "application": {
            "_id": str(app_doc["_id"]),
            "status": app_doc["status"],
            "group_size": app_doc.get("group_size", 1),
            "tier": app_doc.get("tier", 1),
            "weight": app_doc.get("weight"),
            "order_index": app_doc.get("order_index"),
            "total_applicants": total_applicants,
            "fallback": app_doc.get("fallback", "NONE"),
            "credit_snapshot": app_doc.get("credit_snapshot"),
        },
        "allotment": allotment_summary,
        "expected_credit_delta": expected_delta,
        "expected_event_type": expected_event,
        "choice_explanations": choice_explanations,
    }


@router.get("/me/notifications")
async def get_my_notifications(
    unread_only: bool = False,
    unread: bool = False,
    type: str | None = None,
    limit: int = 50,
    user=Depends(get_current_user), db=Depends(get_db)
):
    limit = max(1, min(limit, 200))
    notifications = await repo.list_notifications(
        db, str(user["_id"]), unread_only or unread, limit=limit, type_=type
    )
    return [{**n, "_id": str(n["_id"])} for n in notifications]


@router.get("/me/notifications/unread-count")
async def get_unread_count(user=Depends(get_current_user), db=Depends(get_db)):
    count = await repo.count_unread_notifications(db, str(user["_id"]))
    return {"unread_count": count}


@router.get("/me/notifications/summary")
async def get_notification_summary(user=Depends(get_current_user), db=Depends(get_db)):
    """Unread total plus a per-type breakdown, used by the inbox filter chips."""
    by_type = await repo.notification_type_counts(db, str(user["_id"]))
    return {"unread_count": sum(by_type.values()), "unread_by_type": by_type}


@router.post("/me/notifications/read-all")
async def mark_all_notifications_read(user=Depends(get_current_user), db=Depends(get_db)):
    updated = await repo.mark_all_notifications_read(db, str(user["_id"]))
    return {"message": "All notifications marked as read", "updated": updated}


@router.post("/me/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user=Depends(get_current_user), db=Depends(get_db)
):
    found = await repo.mark_notification_read(db, notification_id, str(user["_id"]))
    if not found:
        raise NotFoundError("Notification not found")
    return {"message": "Marked as read"}
