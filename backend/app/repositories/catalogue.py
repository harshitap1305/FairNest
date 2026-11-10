"""Repositories for hostels, floors, rooms, cycles, and room inventory."""

from __future__ import annotations

from bson import ObjectId

from app.core import clock as _clock


# ─────────────────────────── hostels ─────────────────────────────────────────

async def create_hostel(db, doc: dict) -> str:
    doc = {
        **doc,
        "_id": ObjectId(),
        "active": doc.get("active", True),
        "created_at": _clock.now(),
        "updated_at": _clock.now(),
    }
    r = await db["hostels"].insert_one(doc)
    return str(r.inserted_id)


async def get_hostel(db, hostel_id: str) -> dict | None:
    return await db["hostels"].find_one({"_id": ObjectId(hostel_id)})


async def get_hostel_by_code(db, code: str) -> dict | None:
    return await db["hostels"].find_one({"code": code.upper()})


async def list_hostels(db, active_only: bool = True) -> list[dict]:
    q = {"active": {"$ne": False}} if active_only else {}
    return await db["hostels"].find(q).to_list(length=200)


async def update_hostel(db, hostel_id: str, update: dict) -> bool:
    update["updated_at"] = _clock.now()
    r = await db["hostels"].update_one({"_id": ObjectId(hostel_id)}, {"$set": update})
    return r.modified_count > 0


# ─────────────────────────── floors ──────────────────────────────────────────

async def create_floor(db, doc: dict) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now(), "updated_at": _clock.now()}
    r = await db["floors"].insert_one(doc)
    return str(r.inserted_id)


async def get_floor(db, floor_id: str) -> dict | None:
    return await db["floors"].find_one({"_id": ObjectId(floor_id)})


async def list_floors_by_hostel(db, hostel_id: str) -> list[dict]:
    return await db["floors"].find({"hostel_id": hostel_id}).sort("floor_no", 1).to_list(length=50)


# ─────────────────────────── rooms ───────────────────────────────────────────

async def create_room(db, doc: dict, session=None) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now(), "updated_at": _clock.now()}
    r = await db["rooms"].insert_one(doc, session=session)
    return str(r.inserted_id)


async def get_room(db, room_id: str) -> dict | None:
    return await db["rooms"].find_one({"_id": ObjectId(room_id)})


async def get_room_by_hostel_no(db, hostel_id: str, room_no: str) -> dict | None:
    return await db["rooms"].find_one({"hostel_id": hostel_id, "room_no": room_no.upper()})


async def list_rooms_by_floor(db, floor_id: str, status: str | None = None) -> list[dict]:
    q: dict = {"floor_id": floor_id}
    if status:
        q["status"] = status
    return await db["rooms"].find(q).sort("room_no", 1).to_list(length=500)


async def list_rooms_by_hostel(db, hostel_id: str, status: str | None = None) -> list[dict]:
    q: dict = {"hostel_id": hostel_id}
    if status:
        q["status"] = status
    return await db["rooms"].find(q).sort([("floor_no", 1), ("room_no", 1)]).to_list(length=1000)


async def update_room(db, room_id: str, update: dict) -> bool:
    update["updated_at"] = _clock.now()
    r = await db["rooms"].update_one({"_id": ObjectId(room_id)}, {"$set": update})
    return r.modified_count > 0


# ─────────────────────────── cycles ──────────────────────────────────────────

async def create_cycle(db, doc: dict) -> str:
    doc = {**doc, "_id": ObjectId(), "created_at": _clock.now(), "updated_at": _clock.now()}
    r = await db["cycles"].insert_one(doc)
    return str(r.inserted_id)


async def get_cycle(db, cycle_id: str) -> dict | None:
    return await db["cycles"].find_one({"_id": ObjectId(cycle_id)})


async def list_cycles(db, hostel_ids: list[str] | None = None,
                      status: str | None = None) -> list[dict]:
    q: dict = {}
    if hostel_ids is not None:
        q["hostel_id"] = {"$in": hostel_ids}
    if status:
        q["status"] = status
    return await db["cycles"].find(q).sort("created_at", -1).to_list(length=200)


async def update_cycle(db, cycle_id: str, update: dict, session=None) -> bool:
    update["updated_at"] = _clock.now()
    r = await db["cycles"].update_one(
        {"_id": ObjectId(cycle_id)},
        {"$set": update},
        session=session,
    )
    return r.modified_count > 0


async def transition_cycle_status(db, cycle_id: str, from_status: str,
                                  to_status: str, extra: dict | None = None,
                                  session=None) -> bool:
    """Atomic status transition. Returns True if the update matched."""
    set_doc: dict = {"status": to_status, "updated_at": _clock.now()}
    if extra:
        set_doc.update(extra)
    r = await db["cycles"].update_one(
        {"_id": ObjectId(cycle_id), "status": from_status},
        {"$set": set_doc},
        session=session,
    )
    return r.modified_count > 0


async def get_scheduled_to_open(db, now) -> list[dict]:
    return await db["cycles"].find({
        "status": "SCHEDULED",
        "apply_open_at": {"$lte": now},
    }).to_list(length=100)


async def get_open_to_close(db, now) -> list[dict]:
    return await db["cycles"].find({
        "status": "APPLICATIONS_OPEN",
        "apply_close_at": {"$lte": now},
    }).to_list(length=100)


# ─────────────────────────── room inventory ───────────────────────────────────

async def create_inventory_docs(db, docs: list[dict], session=None) -> list[str]:
    for d in docs:
        d.setdefault("_id", ObjectId())
        d.setdefault("created_at", _clock.now())
        d.setdefault("updated_at", _clock.now())
    r = await db["room_inventory"].insert_many(docs, session=session)
    return [str(i) for i in r.inserted_ids]


async def get_inventory(db, cycle_id: str, room_id: str) -> dict | None:
    return await db["room_inventory"].find_one({"cycle_id": cycle_id, "room_id": room_id})


async def list_inventory(db, cycle_id: str, **filters) -> list[dict]:
    q: dict = {"cycle_id": cycle_id}
    q.update(filters)
    return await db["room_inventory"].find(q).to_list(length=1000)


async def hold_room(db, cycle_id: str, room_id: str, allotment_id: str,
                    session=None) -> bool:
    """Atomic AVAILABLE → HELD. Returns False if the room is no longer AVAILABLE."""
    r = await db["room_inventory"].update_one(
        {"cycle_id": cycle_id, "room_id": room_id, "status": "AVAILABLE"},
        {"$set": {"status": "HELD", "allotment_id": allotment_id, "updated_at": _clock.now()},
         "$inc": {"version": 1}},
        session=session,
    )
    return r.modified_count == 1


async def confirm_room(db, cycle_id: str, room_id: str, allotment_id: str,
                       session=None) -> bool:
    """HELD → CONFIRMED."""
    r = await db["room_inventory"].update_one(
        {"cycle_id": cycle_id, "room_id": room_id,
         "status": "HELD", "allotment_id": allotment_id},
        {"$set": {"status": "CONFIRMED", "updated_at": _clock.now()},
         "$inc": {"version": 1}},
        session=session,
    )
    return r.modified_count == 1


async def release_room(db, cycle_id: str, room_id: str, allotment_id: str,
                       from_status: str = "HELD", session=None) -> bool:
    """HELD or CONFIRMED → AVAILABLE."""
    r = await db["room_inventory"].update_one(
        {"cycle_id": cycle_id, "room_id": room_id,
         "status": from_status, "allotment_id": allotment_id},
        {"$set": {"status": "AVAILABLE", "allotment_id": None, "updated_at": _clock.now()},
         "$inc": {"version": 1}},
        session=session,
    )
    return r.modified_count == 1


async def count_inventory_by_status(db, cycle_id: str) -> dict[str, int]:
    pipeline = [
        {"$match": {"cycle_id": cycle_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    cursor = await db["room_inventory"].aggregate(pipeline)
    rows = await cursor.to_list(length=10)
    return {row["_id"]: row["count"] for row in rows}
