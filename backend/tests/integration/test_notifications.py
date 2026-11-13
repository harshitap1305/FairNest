"""Integration tests for the notification inbox endpoints."""

from __future__ import annotations

import pytest
from bson import ObjectId

from app.repositories import core_repos as repo
from tests.conftest import auth_headers, seed_user


async def _seed_notifications(db, user_id: str, types: list[str]) -> None:
    for t in types:
        await repo.create_notification(db, {
            "user_id": user_id,
            "type": t,
            "title": f"{t} title",
            "body": "body",
            "read": False,
        })


@pytest.mark.asyncio
async def test_mark_all_read_only_touches_own_notifications(live_env):
    client, db, _ = live_env
    me = await seed_user(db, email="me@test.edu", roll_no="R1")
    other = await seed_user(db, email="other@test.edu", roll_no="R2")
    await _seed_notifications(db, str(me["_id"]), ["GROUP_INVITE", "ALLOTMENT_HELD", "ALLOTMENT_HELD"])
    await _seed_notifications(db, str(other["_id"]), ["GROUP_INVITE"])
    hdrs = await auth_headers(client, "me@test.edu")

    summary = await client.get("/api/v1/me/notifications/summary", headers=hdrs)
    assert summary.status_code == 200
    assert summary.json() == {
        "unread_count": 3,
        "unread_by_type": {"GROUP_INVITE": 1, "ALLOTMENT_HELD": 2},
    }

    resp = await client.post("/api/v1/me/notifications/read-all", headers=hdrs)
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3

    count = await client.get("/api/v1/me/notifications/unread-count", headers=hdrs)
    assert count.json()["unread_count"] == 0
    # Another user's inbox is untouched
    assert await repo.count_unread_notifications(db, str(other["_id"])) == 1

    # Idempotent: a second call changes nothing
    again = await client.post("/api/v1/me/notifications/read-all", headers=hdrs)
    assert again.json()["updated"] == 0


@pytest.mark.asyncio
async def test_filter_by_type_and_limit(live_env):
    client, db, _ = live_env
    me = await seed_user(db, email="me@test.edu", roll_no="R1")
    await _seed_notifications(db, str(me["_id"]), ["GROUP_INVITE", "ALLOTMENT_HELD", "WAITLISTED"])
    hdrs = await auth_headers(client, "me@test.edu")

    resp = await client.get("/api/v1/me/notifications", params={"type": "WAITLISTED"}, headers=hdrs)
    assert resp.status_code == 200
    assert [n["type"] for n in resp.json()] == ["WAITLISTED"]

    resp = await client.get("/api/v1/me/notifications", params={"limit": 1}, headers=hdrs)
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_mark_read_rejects_bad_or_foreign_ids(live_env):
    client, db, _ = live_env
    await seed_user(db, email="me@test.edu", roll_no="R1")
    other = await seed_user(db, email="other@test.edu", roll_no="R2")
    await _seed_notifications(db, str(other["_id"]), ["GROUP_INVITE"])
    foreign = await db["notifications"].find_one({"user_id": str(other["_id"])})
    hdrs = await auth_headers(client, "me@test.edu")

    # Malformed id used to crash with a 500; now it is a clean 404
    bad = await client.post("/api/v1/me/notifications/not-an-id/read", headers=hdrs)
    assert bad.status_code == 404

    # Someone else's notification is indistinguishable from a missing one
    resp = await client.post(f"/api/v1/me/notifications/{foreign['_id']}/read", headers=hdrs)
    assert resp.status_code == 404
    missing = await client.post(f"/api/v1/me/notifications/{ObjectId()}/read", headers=hdrs)
    assert missing.status_code == 404
    assert (await db["notifications"].find_one({"_id": foreign["_id"]}))["read"] is False
