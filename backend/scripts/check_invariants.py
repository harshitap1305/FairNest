#!/usr/bin/env python3
"""Check database invariants once; exits 0 (ok) or 1 (violations found)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bson import ObjectId

from app.core.config import get_settings
from app.db.client import close_db, connect_db, get_db


async def main() -> None:
    settings = get_settings()
    await connect_db(settings.MONGO_URI)
    violations: list[str] = []
    try:
        db = get_db(settings.MONGO_DB)

        # 1. No room can have > 1 active allotment per cycle or total members > capacity
        pipeline = [
            {"$match": {"is_active": True, "status": {"$in": ["HELD", "CONFIRMED"]}}},
            {
                "$group": {
                    "_id": {"cycle_id": "$cycle_id", "room_id": "$room_id"},
                    "total_members": {"$sum": {"$size": "$members"}},
                    "allotment_count": {"$sum": 1},
                }
            },
        ]
        async for doc in await db.allotments.aggregate(pipeline):
            rid = doc["_id"]["room_id"]
            cid = doc["_id"]["cycle_id"]
            if doc["allotment_count"] > 1:
                violations.append(
                    f"Room {rid} in cycle {cid} has {doc['allotment_count']} active allotments"
                )
            lookup_rid = ObjectId(rid) if ObjectId.is_valid(str(rid)) else rid
            room = await db.rooms.find_one({"_id": lookup_rid})
            if not room:
                violations.append(f"Active allotment references missing room {rid}")
            elif doc["total_members"] > int(room["capacity"]):
                violations.append(
                    f"Room {rid} overallocated: {doc['total_members']} > {room['capacity']}"
                )

        # 2. At most one live room_inventory entry per physical room
        live_pipeline = [
            {"$match": {"is_live": True}},
            {"$group": {"_id": "$room_id", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        async for doc in await db.room_inventory.aggregate(live_pipeline):
            violations.append(f"Room {doc['_id']} is live in {doc['count']} cycles simultaneously")

        # 3. Every cycle has at most one MAIN allocation run
        main_run_pipeline = [
            {"$match": {"type": "MAIN"}},
            {"$group": {"_id": "$cycle_id", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        async for doc in await db.allocation_runs.aggregate(main_run_pipeline):
            violations.append(f"Cycle {doc['_id']} has {doc['count']} MAIN allocation runs")

        # 4. Credit accounts must stay within [C_MIN, C_MAX]
        async for acct in db.credit_accounts.find({
            "$or": [
                {"credits": {"$lt": settings.C_MIN}},
                {"credits": {"$gt": settings.C_MAX}},
            ]
        }):
            violations.append(
                f"User {acct.get('user_id')} has out-of-bounds credits: {acct.get('credits')}"
            )

        # 5. All members of CONFIRMED allotments must have accept_status = ACCEPTED
        async for allotment in db.allotments.find({"status": "CONFIRMED"}):
            for m in allotment.get("members", []):
                if m.get("accept_status") != "ACCEPTED":
                    violations.append(
                        f"Allotment {allotment['_id']}: CONFIRMED but member {m.get('user_id')} has status {m.get('accept_status')}"
                    )

        # 6. No user has > 1 ACCEPTED membership in the same cycle
        mem_pipeline = [
            {"$match": {"status": "ACCEPTED"}},
            {"$group": {"_id": {"cycle_id": "$cycle_id", "user_id": "$user_id"}, "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        async for doc in await db.memberships.aggregate(mem_pipeline):
            violations.append(
                f"User {doc['_id']['user_id']} has {doc['count']} ACCEPTED memberships in cycle {doc['_id']['cycle_id']}"
            )
    finally:
        await close_db()

    if violations:
        print(f"INVARIANT VIOLATIONS FOUND ({len(violations)}):")
        for v in violations:
            print(f"  ✗ {v}")
        sys.exit(1)
    else:
        print("All invariants OK ✓")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
