"""Background worker: runs periodic allotment & cycle lifecycle jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bson import ObjectId

from app.core import clock as _clock
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.client import connect_db, get_client, get_db
from app.db.indexes import create_indexes
from app.db.validators import create_validators

logger = logging.getLogger(__name__)

FAST_INTERVAL = 30   # seconds


async def run_expire_holds(db, client):
    from app.repositories.catalogue import release_room
    from app.repositories.core_repos import create_notification, list_expired_held, try_extend_grace
    from app.services.allotment_service import run_cascade

    now = _clock.now()
    expired = await list_expired_held(db, now)
    for allotment in expired:
        allotment_id = str(allotment["_id"])
        grace_minutes = 10
        # Atomic one-time grace extension if pending members exist
        extended = await try_extend_grace(
            db,
            allotment_id,
            new_expires_at=allotment["expires_at"] + timedelta(minutes=grace_minutes),
            now=now,
        )
        if extended:
            logger.info("Grace extended for allotment %s", allotment_id)
            continue

        # Atomic expiry claim so multiple workers cannot double-expire
        res = await db["allotments"].update_one(
            {"_id": allotment["_id"], "status": "HELD", "expires_at": {"$lte": now}},
            {"$set": {
                "status": "EXPIRED",
                "is_active": False,
                "release_reason": "TIMEOUT",
                "updated_at": now,
            }},
        )
        if res.modified_count == 0:
            continue

        await release_room(
            db, allotment["cycle_id"], allotment["room_id"], allotment_id, from_status="HELD"
        )
        app_oid = ObjectId(allotment["application_id"]) if ObjectId.is_valid(str(allotment["application_id"])) else allotment["application_id"]
        await db["applications"].update_one(
            {"_id": app_oid},
            {"$set": {
                "status": "FORFEITED",
                "last_allotment_status": "EXPIRED",
                "updated_at": now,
            }},
        )
        for m in allotment.get("members", []):
            await create_notification(db, {
                "user_id": m["user_id"],
                "type": "ALLOTMENT_EXPIRED",
                "title": "Allotment Hold Expired",
                "body": "The hold deadline passed before all group members accepted; the room was released.",
                "read": False,
            })
        logger.info("Allotment %s expired -> FORFEITED + cascade", allotment_id)
        await run_cascade(db, client, allotment["cycle_id"], actor_id="system")


async def run_open_window(db, client):
    from app.repositories.catalogue import get_scheduled_to_open, transition_cycle_status
    from app.services.cycle_service import open_cycle_impl

    now = _clock.now()
    cycles = await get_scheduled_to_open(db, now)
    for cycle in cycles:
        cycle_id = str(cycle["_id"])
        moved = await transition_cycle_status(db, cycle_id, "SCHEDULED", "APPLICATIONS_OPEN_PENDING")
        if moved:
            try:
                await open_cycle_impl(
                    db, client, cycle_id, "system", allowed_from=("APPLICATIONS_OPEN_PENDING",)
                )
                logger.info("Cycle %s opened automatically", cycle_id)
            except Exception as exc:
                logger.error("Failed opening scheduled cycle %s: %s", cycle_id, exc)
                await db["cycles"].update_one(
                    {"_id": cycle["_id"], "status": "APPLICATIONS_OPEN_PENDING"},
                    {"$set": {"status": "SCHEDULED"}},
                )


async def run_close_window(db, client):
    from app.repositories.catalogue import get_open_to_close
    from app.services.cycle_service import close_window_impl

    now = _clock.now()
    cycles = await get_open_to_close(db, now)
    for cycle in cycles:
        cycle_id = str(cycle["_id"])
        try:
            await close_window_impl(db, client, cycle_id, "system")
            logger.info("Cycle %s window closed automatically", cycle_id)
        except Exception as exc:
            logger.debug("Close window skipped for %s: %s", cycle_id, exc)


def _no_waitlisted_can_fit(cycle: dict, waitlisted: list[dict], available_inv: list[dict]) -> bool:
    if not waitlisted:
        return True
    fill_rule = cycle.get("policy", {}).get("fill_rule", "EXACT")
    avail_by_id = {inv["room_id"]: inv for inv in available_inv}
    for app in waitlisted:
        gsize = int(app.get("group_size", 1))
        if app.get("fallback") == "ANY_ELIGIBLE":
            for inv in available_inv:
                cap = int(inv["capacity"])
                if (fill_rule == "EXACT" and cap == gsize) or (fill_rule == "AT_MOST" and gsize <= cap):
                    return False
        for ch in app.get("ranked_choices", []):
            kind = ch.get("kind", "ROOM")
            if kind == "ROOM":
                inv = avail_by_id.get(ch.get("room_id"))
                if inv:
                    cap = int(inv["capacity"])
                    if (fill_rule == "EXACT" and cap == gsize) or (fill_rule == "AT_MOST" and gsize <= cap):
                        return False
            elif kind == "FLOOR":
                fno = ch.get("floor_no")
                for inv in available_inv:
                    if inv.get("floor_no") == fno:
                        cap = int(inv["capacity"])
                        if (fill_rule == "EXACT" and cap == gsize) or (fill_rule == "AT_MOST" and gsize <= cap):
                            return False
    return True


async def run_close_cycle_check(db, client):
    """Close ALLOTMENT_ACTIVE cycles if all rooms consumed, deadline reached, or nothing can fit."""
    from app.repositories.catalogue import count_inventory_by_status, list_cycles, list_inventory
    from app.repositories.core_repos import list_waitlisted_by_cycle, mark_unallotted

    cycles = await list_cycles(db, status="ALLOTMENT_ACTIVE")
    now = _clock.now()
    for cycle in cycles:
        cycle_id = str(cycle["_id"])
        counts = await count_inventory_by_status(db, cycle_id)
        available = counts.get("AVAILABLE", 0)
        held = counts.get("HELD", 0)

        should_close = False
        reason = ""
        final_deadline = cycle.get("final_deadline_at")

        if available == 0 and held == 0:
            should_close = True
            reason = "all rooms consumed"
        elif final_deadline and now > final_deadline:
            should_close = True
            reason = "final deadline reached"
        elif held == 0:
            waitlisted = await list_waitlisted_by_cycle(db, cycle_id)
            avail_inv = await list_inventory(db, cycle_id, status="AVAILABLE")
            if _no_waitlisted_can_fit(cycle, waitlisted, avail_inv):
                should_close = True
                reason = "no remaining waitlist group fits available rooms"

        if should_close:
            await db["cycles"].update_one(
                {"_id": cycle["_id"], "status": "ALLOTMENT_ACTIVE"},
                {"$set": {"status": "CLOSED", "closed_at": now, "updated_at": now}},
            )
            await db["room_inventory"].update_many(
                {"cycle_id": cycle_id, "is_live": True},
                {"$set": {"is_live": False, "updated_at": now}},
            )
            await mark_unallotted(db, cycle_id)
            logger.info("Cycle %s closed (%s)", cycle_id, reason)


async def run_invariant_check(db):
    violations = []
    inventory = await db["room_inventory"].find(
        {"status": {"$in": ["HELD", "CONFIRMED"]}}
    ).to_list(length=5000)
    for inv in inventory:
        active_allotments = await db["allotments"].count_documents(
            {"cycle_id": inv["cycle_id"], "room_id": inv["room_id"], "is_active": True}
        )
        if active_allotments != 1:
            violations.append(
                f"Room {inv['room_id']} in cycle {inv['cycle_id']} "
                f"has status {inv['status']} but {active_allotments} active allotments"
            )
    available = await db["room_inventory"].find({"status": "AVAILABLE"}).to_list(length=5000)
    for inv in available:
        active_allotments = await db["allotments"].count_documents(
            {"cycle_id": inv["cycle_id"], "room_id": inv["room_id"], "is_active": True}
        )
        if active_allotments > 0:
            violations.append(
                f"AVAILABLE room {inv['room_id']} has {active_allotments} active allotments"
            )
    if violations:
        logger.critical("INVARIANT VIOLATIONS DETECTED: %s", violations)
    else:
        logger.debug("Invariant check passed")
    return violations


async def main():
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger.info("Worker starting...")
    await connect_db(settings.MONGO_URI)
    db = get_db(settings.MONGO_DB)
    client = get_client()
    await create_indexes(db)
    await create_validators(db)
    logger.info("Worker ready, starting job loop")
    tick = 0
    while True:
        try:
            await run_expire_holds(db, client)
            await run_open_window(db, client)
            await run_close_window(db, client)
            await run_close_cycle_check(db, client)
            tick += 1
            if tick % 20 == 0:
                await run_invariant_check(db)
        except Exception as exc:
            logger.error("Worker job error: %s", exc, exc_info=True)
        await asyncio.sleep(FAST_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
