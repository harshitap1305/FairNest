"""Catalogue routes: hostels, floors, rooms, availability."""

from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Depends, Query
from pymongo.errors import DuplicateKeyError

from app.allocator.core import _room_sort_key
from app.api.deps import get_client, get_current_user, get_db, current_warden
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.scope import (
    assert_staff_scope,
    assert_user_hostel_scope,
    filter_hostel_ids_for_user,
)
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.services.catalogue_service import parse_room_entries

router = APIRouter(tags=["catalogue"])


@router.get("/hostels")
async def list_hostels(user=Depends(get_current_user), db=Depends(get_db)):
    hostels = await cat_repo.list_hostels(db)
    allowed = filter_hostel_ids_for_user(user)
    if allowed is not None:
        hostels = [h for h in hostels if str(h["_id"]) in allowed]
    return [{**h, "_id": str(h["_id"])} for h in hostels]


@router.get("/hostels/{hostel_id}")
async def get_hostel(hostel_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    assert_user_hostel_scope(user, hostel_id)
    h = await cat_repo.get_hostel(db, hostel_id)
    if not h:
        raise NotFoundError("Hostel not found")
    return {**h, "_id": str(h["_id"])}


@router.get("/hostels/{hostel_id}/floors")
async def list_floors(hostel_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    assert_user_hostel_scope(user, hostel_id)
    floors = await cat_repo.list_floors_by_hostel(db, hostel_id)
    return [{**f, "_id": str(f["_id"])} for f in floors]


@router.get("/hostels/{hostel_id}/rooms")
async def list_hostel_rooms(
    hostel_id: str,
    floor_id: str | None = None,
    floor_no: int | None = None,
    status: str | None = None,
    user=Depends(current_warden),
    db=Depends(get_db),
):
    assert_staff_scope(user, hostel_id)
    rooms = await cat_repo.list_rooms_by_hostel(db, hostel_id, status=status)
    if floor_id:
        rooms = [r for r in rooms if r.get("floor_id") == floor_id]
    if floor_no is not None:
        rooms = [r for r in rooms if r.get("floor_no") == floor_no]
    rooms.sort(key=lambda r: (r.get("floor_no", 0), _room_sort_key(r.get("room_no", ""))))
    return [{**r, "_id": str(r["_id"])} for r in rooms]


@router.get("/cycles/{cycle_id}/floors")
@router.get("/cycles/{cycle_id}/hostels/{hostel_id}/floors")
async def list_cycle_floors(
    cycle_id: str,
    hostel_id: str | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    hid = hostel_id or cycle["hostel_id"]
    if hid != cycle["hostel_id"]:
        raise NotFoundError("Hostel not in this cycle")
    assert_user_hostel_scope(user, hid)

    floors = await cat_repo.list_floors_by_hostel(db, hid)
    inventory = await cat_repo.list_inventory(db, cycle_id, hostel_id=hid)
    by_floor: dict[int, list[dict]] = {}
    for inv in inventory:
        by_floor.setdefault(inv["floor_no"], []).append(inv)

    result = []
    for f in floors:
        fno = f["floor_no"]
        invs = by_floor.get(fno, [])
        capacities = sorted({i["capacity"] for i in invs if i.get("status") != "BLOCKED"})
        available_count = sum(1 for i in invs if i.get("status") == "AVAILABLE")
        result.append({
            **f,
            "_id": str(f["_id"]),
            "total_rooms": len(invs),
            "available_rooms": available_count,
            "capacities": capacities,
        })
    return result


@router.get("/cycles/{cycle_id}/rooms")
async def list_cycle_rooms(
    cycle_id: str,
    hostel_id: str | None = None,
    floor_no: int | None = None,
    capacity: int | None = None,
    status: str | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    assert_user_hostel_scope(user, cycle["hostel_id"])

    filters: dict = {}
    if hostel_id:
        filters["hostel_id"] = hostel_id
    if floor_no is not None:
        filters["floor_no"] = floor_no
    if capacity is not None:
        filters["capacity"] = capacity
    if status:
        filters["status"] = status

    inventory = await cat_repo.list_inventory(db, cycle_id, **filters)
    room_obj_ids = [ObjectId(inv["room_id"]) for inv in inventory if ObjectId.is_valid(inv["room_id"])]
    room_docs = {}
    if room_obj_ids:
        cursor = db["rooms"].find({"_id": {"$in": room_obj_ids}})
        async for rm in cursor:
            room_docs[str(rm["_id"])] = rm

    result = []
    for inv in inventory:
        room = room_docs.get(inv["room_id"])
        result.append({
            "room_id": inv["room_id"],
            "room_no": room.get("room_no", "") if room else "",
            "floor_no": inv["floor_no"],
            "hostel_id": inv["hostel_id"],
            "capacity": inv["capacity"],
            "status": inv["status"],
            "features": room.get("features", []) if room else [],
        })
    result.sort(key=lambda r: (r.get("floor_no", 0), _room_sort_key(r.get("room_no", ""))))
    return result


@router.get("/cycles/{cycle_id}/availability-summary")
async def availability_summary(cycle_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    assert_user_hostel_scope(user, cycle["hostel_id"])
    return await cat_repo.count_inventory_by_status(db, cycle_id)


# ── Admin / Warden room management ────────────────────────────────────────────

@router.post("/admin/hostels")
async def create_hostel(body: dict, user=Depends(current_warden), db=Depends(get_db)):
    if user.get("role") not in ("ADMIN", "SUPER_ADMIN"):
        from app.core.errors import ForbiddenError
        raise ForbiddenError("Only ADMIN or SUPER_ADMIN can create hostels")
    try:
        hostel_id = await cat_repo.create_hostel(db, {
            "name": body["name"],
            "code": body["code"].upper(),
            "allowed_gender": body.get("allowed_gender", "ANY"),
            "allowed_years": body.get("allowed_years", []),
            "active": True,
        })
    except DuplicateKeyError:
        raise ConflictError("Hostel code already exists", code="HOSTEL_CODE_EXISTS")
    return {"id": hostel_id, "_id": hostel_id}


@router.post("/admin/hostels/{hostel_id}/floors")
async def create_floor(hostel_id: str, body: dict, user=Depends(current_warden), db=Depends(get_db)):
    assert_staff_scope(user, hostel_id)
    hostel = await cat_repo.get_hostel(db, hostel_id)
    if not hostel:
        raise NotFoundError("Hostel not found")
    try:
        floor_no = int(body["floor_no"])
        floor_id = await cat_repo.create_floor(db, {
            "hostel_id": hostel_id,
            "floor_no": floor_no,
            "label": body.get("label") or f"Floor {floor_no}",
            "active": True,
        })
    except DuplicateKeyError:
        raise ConflictError("Floor already exists in this hostel", code="FLOOR_ALREADY_EXISTS")
    return {"id": floor_id, "_id": floor_id}


@router.post("/admin/floors/{floor_id}/rooms/from-list")
async def create_rooms_from_list(
    floor_id: str,
    body: dict,
    dry_run: bool = Query(False),
    user=Depends(current_warden),
    db=Depends(get_db),
    client=Depends(get_client),
):
    """
    Comma-separated room entry with dry_run preview (`?dry_run=true` or body.dry_run=true).
    Max 200 rooms per batch. Inserts atomically inside a transaction.
    """
    room_numbers_str = body.get("room_numbers", "")
    default_capacity = int(body.get("capacity", 2))
    if default_capacity < 1 or default_capacity > 8:
        raise ValidationError("Default capacity must be between 1 and 8")
    features = body.get("features", [])
    is_dry_run = bool(dry_run or body.get("dry_run", False))
    skip_existing = bool(body.get("skip_existing", False))

    floor = await cat_repo.get_floor(db, floor_id)
    if not floor:
        raise NotFoundError("Floor not found")
    assert_staff_scope(user, floor["hostel_id"])

    parsed, dups_in_input, invalid = parse_room_entries(
        room_numbers_str, default_capacity, max_tokens=200
    )

    already_exist: list[str] = []
    to_create: list[dict] = []
    for room in parsed:
        existing = await cat_repo.get_room_by_hostel_no(db, floor["hostel_id"], room["room_no"])
        if existing:
            already_exist.append(room["room_no"])
        else:
            to_create.append(room)

    if is_dry_run:
        return {
            "to_create": [r["room_no"] for r in to_create],
            "duplicates_in_input": dups_in_input,
            "already_exist": already_exist,
            "invalid": invalid,
        }

    if invalid and not skip_existing:
        raise ValidationError(f"Invalid room tokens: {invalid}")
    if already_exist and not skip_existing:
        raise ConflictError(f"Rooms already exist: {already_exist}", code="ROOMS_ALREADY_EXIST")

    created_ids: list[str] = []
    if to_create:
        async def _tx(session):
            ids: list[str] = []
            try:
                for room in to_create:
                    rid = await cat_repo.create_room(db, {
                        "hostel_id": floor["hostel_id"],
                        "floor_id": floor_id,
                        "floor_no": floor["floor_no"],
                        "room_no": room["room_no"],
                        "capacity": room["capacity"],
                        "features": features,
                        "status": "ACTIVE",
                    }, session=session)
                    ids.append(rid)
            except DuplicateKeyError:
                raise ConflictError("Duplicate room number in hostel", code="ROOMS_ALREADY_EXIST")
            await repo.create_audit_log(db, {
                "actor_id": str(user["_id"]),
                "role": user["role"],
                "action": "CREATE_ROOMS_FROM_LIST",
                "target_type": "floor",
                "target_id": floor_id,
                "before": None,
                "after": {"count": len(ids), "rooms": [r["room_no"] for r in to_create]},
                "request_id": "",
                "ip": "",
            }, session=session)
            return ids

        async with client.start_session() as session:
            created_ids = await session.with_transaction(_tx)

    return {
        "created": len(created_ids),
        "to_create": [r["room_no"] for r in to_create],
        "duplicates_in_input": dups_in_input,
        "already_exist": already_exist,
        "invalid": invalid,
    }


@router.post("/admin/floors/{floor_id}/rooms/bulk")
async def bulk_create_rooms(floor_id: str, body: dict, user=Depends(current_warden), db=Depends(get_db)):
    floor = await cat_repo.get_floor(db, floor_id)
    if not floor:
        raise NotFoundError("Floor not found")
    assert_staff_scope(user, floor["hostel_id"])

    from_no = int(body.get("from_no", 1))
    to_no = int(body.get("to_no", 1))
    if to_no < from_no or (to_no - from_no + 1) > 200:
        raise ValidationError("Range must be valid and at most 200 rooms")
    capacity = int(body.get("capacity", 2))
    features = body.get("features", [])
    created = []
    for n in range(from_no, to_no + 1):
        room_no = str(n)
        existing = await cat_repo.get_room_by_hostel_no(db, floor["hostel_id"], room_no)
        if not existing:
            rid = await cat_repo.create_room(db, {
                "hostel_id": floor["hostel_id"],
                "floor_id": floor_id,
                "floor_no": floor["floor_no"],
                "room_no": room_no,
                "capacity": capacity,
                "features": features,
                "status": "ACTIVE",
            })
            created.append(rid)
    return {"created": len(created)}


@router.patch("/admin/rooms/{room_id}")
async def update_room(room_id: str, body: dict, user=Depends(current_warden), db=Depends(get_db)):
    room = await cat_repo.get_room(db, room_id)
    if not room:
        raise NotFoundError("Room not found")
    assert_staff_scope(user, room["hostel_id"])

    allowed_fields = {"status", "capacity", "features", "room_no"}
    update = {k: v for k, v in body.items() if k in allowed_fields}
    if not update:
        return {"message": "No changes"}

    if "status" in update and update["status"] not in ("ACTIVE", "MAINTENANCE"):
        raise ValidationError("Status must be ACTIVE or MAINTENANCE")
    if "capacity" in update:
        cap = int(update["capacity"])
        if cap < 1 or cap > 8:
            raise ValidationError("Capacity must be 1-8")
        update["capacity"] = cap

    # Guard against altering rooms with active HELD/CONFIRMED allotments
    if update.get("status") == "MAINTENANCE":
        live_busy = await db["room_inventory"].find_one({
            "room_id": room_id,
            "is_live": True,
            "status": {"$in": ["HELD", "CONFIRMED"]},
        })
        if live_busy:
            raise ConflictError(
                "Room has an active HELD or CONFIRMED allotment; revoke allotment before setting maintenance",
                code="ROOM_BUSY",
            )
        await db["room_inventory"].update_many(
            {"room_id": room_id, "is_live": True, "status": "AVAILABLE"},
            {"$set": {"status": "BLOCKED"}},
        )
    elif update.get("status") == "ACTIVE":
        await db["room_inventory"].update_many(
            {"room_id": room_id, "is_live": True, "status": "BLOCKED"},
            {"$set": {"status": "AVAILABLE"}},
        )

    await cat_repo.update_room(db, room_id, update)
    await repo.create_audit_log(db, {
        "actor_id": str(user["_id"]),
        "role": user["role"],
        "action": "UPDATE_ROOM",
        "target_type": "room",
        "target_id": room_id,
        "before": {"status": room.get("status"), "capacity": room.get("capacity")},
        "after": update,
        "request_id": "",
        "ip": "",
    })
    return {"message": "Room updated"}
