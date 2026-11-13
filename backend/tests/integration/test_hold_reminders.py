"""Tests for the worker job that reminds members about holds that are about to expire."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app import worker

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


async def _insert_hold(db, *, expires_in: timedelta, members: list[tuple[str, str]], status="HELD"):
    room_id = ObjectId()
    await db["rooms"].insert_one(
        {"_id": room_id, "hostel_id": str(ObjectId()), "room_no": "204", "capacity": len(members)}
    )
    doc = {
        "_id": ObjectId(),
        "cycle_id": str(ObjectId()),
        "application_id": str(ObjectId()),
        "room_id": str(room_id),
        "status": status,
        "is_active": status == "HELD",
        "expires_at": NOW + expires_in,
        "members": [{"user_id": uid, "accept_status": st} for uid, st in members],
    }
    await db["allotments"].insert_one(doc)
    return doc


@pytest.mark.asyncio
async def test_reminds_only_pending_members_once(live_env):
    _, db, _ = live_env
    hold = await _insert_hold(
        db, expires_in=timedelta(hours=3), members=[("u1", "ACCEPTED"), ("u2", "PENDING"), ("u3", "PENDING")]
    )

    sent = await worker.run_hold_reminders(db, now=NOW, reminder_hours=6)
    assert sent == 2
    notes = await db["notifications"].find({"type": "HOLD_EXPIRING_SOON"}).to_list(10)
    assert sorted(n["user_id"] for n in notes) == ["u2", "u3"]
    assert "room 204" in notes[0]["body"] and "3h 0m" in notes[0]["body"]
    assert notes[0]["allotment_id"] == str(hold["_id"])

    # A second pass (or a second worker) must not send duplicates
    assert await worker.run_hold_reminders(db, now=NOW + timedelta(minutes=30), reminder_hours=6) == 0
    stored = await db["allotments"].find_one({"_id": hold["_id"]})
    assert stored["reminder_sent_at"] is not None


@pytest.mark.asyncio
async def test_skips_holds_outside_window_or_not_held(live_env):
    _, db, _ = live_env
    await _insert_hold(db, expires_in=timedelta(hours=20), members=[("far", "PENDING")])
    await _insert_hold(db, expires_in=timedelta(minutes=-5), members=[("past", "PENDING")])
    await _insert_hold(db, expires_in=timedelta(hours=1), members=[("done", "PENDING")], status="CONFIRMED")

    assert await worker.run_hold_reminders(db, now=NOW, reminder_hours=6) == 0
    assert await db["notifications"].count_documents({}) == 0


@pytest.mark.asyncio
async def test_disabled_when_reminder_hours_is_zero(live_env):
    _, db, _ = live_env
    await _insert_hold(db, expires_in=timedelta(hours=1), members=[("u1", "PENDING")])
    assert await worker.run_hold_reminders(db, now=NOW, reminder_hours=0) == 0
