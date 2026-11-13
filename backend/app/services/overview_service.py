"""Operations overview for staff: what is happening right now across scoped cycles."""

from __future__ import annotations

from datetime import timedelta

from bson import ObjectId

from app.core import clock as _clock

ACTIVE_CYCLE_STATES = (
    "DRAFT", "SCHEDULED", "APPLICATIONS_OPEN", "APPLICATIONS_CLOSED", "ALLOCATING",
    "ALLOTMENT_ACTIVE", "CLOSED",
)
EXPIRING_SOON_HOURS = 6
CLOSING_SOON_HOURS = 24


async def _count_by(db, collection: str, match: dict, field: str) -> dict[str, dict[str, int]]:
    """{cycle_id: {value_of_field: count}} for documents matching ``match``."""
    cursor = await db[collection].aggregate([
        {"$match": match},
        {"$group": {"_id": {"c": "$cycle_id", "v": f"${field}"}, "n": {"$sum": 1}}},
    ])
    out: dict[str, dict[str, int]] = {}
    async for row in cursor:
        out.setdefault(row["_id"]["c"], {})[str(row["_id"]["v"])] = row["n"]
    return out


async def build_overview(db, hostel_ids: list[str] | None) -> dict:
    now = _clock.now()
    q: dict = {"status": {"$in": list(ACTIVE_CYCLE_STATES)}}
    if hostel_ids is not None:
        q["hostel_id"] = {"$in": hostel_ids}
    cycles = await db["cycles"].find(q).sort("created_at", -1).to_list(length=50)
    cycle_ids = [str(c["_id"]) for c in cycles]
    in_cycles = {"cycle_id": {"$in": cycle_ids}}

    apps = await _count_by(db, "applications", in_cycles, "status")
    inv = await _count_by(db, "room_inventory", in_cycles, "status")
    allots = await _count_by(db, "allotments", {**in_cycles, "is_active": True}, "status")

    hostels = {
        str(h["_id"]): h.get("name", "")
        async for h in db["hostels"].find(
            {"_id": {"$in": [ObjectId(c["hostel_id"]) for c in cycles if ObjectId.is_valid(c["hostel_id"])]}},
            {"name": 1},
        )
    }

    soon = now + timedelta(hours=EXPIRING_SOON_HOURS)
    expiring = await db["allotments"].find({
        **in_cycles, "status": "HELD", "expires_at": {"$gt": now, "$lte": soon},
    }).sort("expires_at", 1).to_list(length=50)
    rooms = {
        str(r["_id"]): r.get("room_no", "")
        async for r in db["rooms"].find(
            {"_id": {"$in": [ObjectId(a["room_id"]) for a in expiring if ObjectId.is_valid(a.get("room_id", ""))]}},
            {"room_no": 1},
        )
    }
    cycle_names = {str(c["_id"]): c.get("name", "") for c in cycles}

    rows = []
    totals = {"applications": 0, "held": 0, "confirmed": 0, "waitlisted": 0, "rooms": 0, "rooms_free": 0}
    for c in cycles:
        cid = str(c["_id"])
        a = apps.get(cid, {})
        i = inv.get(cid, {})
        al = allots.get(cid, {})
        n_apps = sum(v for k, v in a.items() if k not in ("DRAFT", "WITHDRAWN"))
        n_rooms = sum(i.values())
        confirmed = al.get("CONFIRMED", 0)
        row = {
            "cycle_id": cid,
            "name": c.get("name", ""),
            "hostel_id": c.get("hostel_id"),
            "hostel_name": hostels.get(c.get("hostel_id"), ""),
            "status": c.get("status"),
            "apply_close_at": c.get("apply_close_at"),
            "applications": n_apps,
            "applications_by_status": a,
            "inventory_by_status": i,
            "rooms_total": n_rooms,
            "held": al.get("HELD", 0),
            "confirmed": confirmed,
            "waitlisted": a.get("WAITLISTED", 0),
            "fill_rate": round(confirmed / n_rooms, 3) if n_rooms else None,
            "expiring_soon": sum(1 for x in expiring if x["cycle_id"] == cid),
        }
        rows.append(row)
        totals["applications"] += n_apps
        totals["held"] += row["held"]
        totals["confirmed"] += confirmed
        totals["waitlisted"] += row["waitlisted"]
        totals["rooms"] += n_rooms
        totals["rooms_free"] += i.get("AVAILABLE", 0)

    closing_soon = [
        {"cycle_id": r["cycle_id"], "name": r["name"], "apply_close_at": r["apply_close_at"]}
        for r in rows
        if r["status"] == "APPLICATIONS_OPEN" and r["apply_close_at"]
        and now < r["apply_close_at"] <= now + timedelta(hours=CLOSING_SOON_HOURS)
    ]
    expiring_holds = [
        {
            "allotment_id": str(x["_id"]),
            "cycle_id": x["cycle_id"],
            "cycle_name": cycle_names.get(x["cycle_id"], ""),
            "room_no": rooms.get(str(x.get("room_id")), ""),
            "expires_at": x["expires_at"],
            "pending_members": sum(1 for m in x.get("members", []) if m.get("accept_status") == "PENDING"),
            "member_count": len(x.get("members", [])),
        }
        for x in expiring[:10]
    ]
    return {
        "generated_at": now,
        "totals": totals,
        "cycles": rows,
        "attention": {"expiring_holds": expiring_holds, "closing_soon": closing_soon},
    }
