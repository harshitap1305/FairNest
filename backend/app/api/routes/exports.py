"""CSV export routes for staff: allotment rosters and audit logs."""

from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Depends

from app.api.deps import current_auditor, current_warden, get_db
from app.core import clock as _clock
from app.core.csv_export import csv_response
from app.core.errors import NotFoundError
from app.core.scope import assert_staff_scope
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo

router = APIRouter(tags=["exports"])

MAX_EXPORT_ROWS = 10_000

ALLOTMENT_HEADERS = [
    "cycle", "hostel", "floor_no", "room_no", "capacity", "allotment_status", "round_no",
    "rank_obtained", "member_name", "roll_no", "email", "accept_status", "accepted_at",
    "held_at", "expires_at", "release_reason", "allotment_id",
]


async def _docs_by_id(db, collection: str, ids, projection=None) -> dict[str, dict]:
    oids = [ObjectId(i) for i in {str(i) for i in ids} if ObjectId.is_valid(i)]
    if not oids:
        return {}
    rows = await db[collection].find({"_id": {"$in": oids}}, projection).to_list(length=len(oids))
    return {str(r["_id"]): r for r in rows}


@router.get("/admin/cycles/{cycle_id}/allotments.csv")
async def export_allotments_csv(
    cycle_id: str,
    status: str | None = None,
    user=Depends(current_warden),
    db=Depends(get_db),
):
    """One row per group member, ready for the hostel office's room register."""
    cycle = await cat_repo.get_cycle(db, cycle_id) if ObjectId.is_valid(cycle_id) else None
    if not cycle:
        raise NotFoundError("Cycle not found")
    assert_staff_scope(user, cycle["hostel_id"])

    q: dict = {"cycle_id": cycle_id}
    if status:
        q["status"] = status.upper()
    allotments = await db["allotments"].find(q).sort("created_at", 1).to_list(length=MAX_EXPORT_ROWS)

    rooms = await _docs_by_id(db, "rooms", [a.get("room_id") for a in allotments])
    users = await _docs_by_id(
        db, "users",
        [m["user_id"] for a in allotments for m in a.get("members", [])],
        {"name": 1, "roll_no": 1, "email": 1},
    )
    hostel = await cat_repo.get_hostel(db, cycle["hostel_id"])
    hostel_name = (hostel or {}).get("name", "")

    def sort_key(a):
        r = rooms.get(str(a.get("room_id")), {})
        return (r.get("floor_no") or 0, str(r.get("room_no", "")), str(a["_id"]))

    rows = []
    for a in sorted(allotments, key=sort_key):
        room = rooms.get(str(a.get("room_id")), {})
        for m in a.get("members", []) or [{}]:
            u = users.get(str(m.get("user_id")), {})
            rows.append([
                cycle.get("name", ""), hostel_name, room.get("floor_no"), room.get("room_no"),
                room.get("capacity"), a.get("status"), a.get("round_no"), a.get("rank_obtained"),
                u.get("name"), u.get("roll_no"), u.get("email"), m.get("accept_status"),
                m.get("accepted_at"), a.get("held_at"), a.get("expires_at"), a.get("release_reason"),
                str(a["_id"]),
            ])

    stamp = _clock.now().strftime("%Y%m%d")
    name = f"allotments_{cycle.get('name', cycle_id)}_{stamp}.csv"
    return csv_response(name, ALLOTMENT_HEADERS, rows)


@router.get("/admin/audit-logs.csv")
async def export_audit_logs_csv(
    actor_id: str | None = None,
    target_type: str | None = None,
    action: str | None = None,
    limit: int = 5000,
    user=Depends(current_auditor),
    db=Depends(get_db),
):
    """Audit trail export using the same filters as the audit log explorer."""
    limit = max(1, min(limit, MAX_EXPORT_ROWS))
    logs = await repo.list_audit_logs(
        db, actor_id=actor_id, target_type=target_type, action=action, limit=limit
    )
    actors = await _docs_by_id(db, "users", [log.get("actor_id") for log in logs], {"email": 1})
    rows = [
        [
            log.get("ts"), log.get("action"), log.get("role"),
            actors.get(str(log.get("actor_id")), {}).get("email") or log.get("actor_id"),
            log.get("target_type"), log.get("target_id"), log.get("ip"), log.get("request_id"),
            log.get("before"), log.get("after"),
        ]
        for log in logs
    ]
    headers = ["timestamp", "action", "role", "actor", "target_type", "target_id", "ip",
               "request_id", "before", "after"]
    return csv_response(f"audit_logs_{_clock.now().strftime('%Y%m%d_%H%M')}.csv", headers, rows)
