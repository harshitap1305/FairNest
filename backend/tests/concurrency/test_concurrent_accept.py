"""Real MongoDB replica-set concurrency tests for allotment acceptance and room holds."""

from __future__ import annotations

import asyncio

import pytest

from tests.conftest import auth_headers, seed_user


async def _prepare_held_two_member_allotment(client, db):
    await seed_user(db, email="admin@conc.edu", role="SUPER_ADMIN")
    h_adm = await auth_headers(client, "admin@conc.edu")

    hid = (
        await client.post(
            "/api/v1/admin/hostels",
            headers=h_adm,
            json={"name": "Conc Hostel", "code": "CH1", "allowed_gender": "M"},
        )
    ).json()["_id"]
    fid = (
        await client.post(
            f"/api/v1/admin/hostels/{hid}/floors",
            headers=h_adm,
            json={"floor_no": 1},
        )
    ).json()["_id"]
    await client.post(
        f"/api/v1/admin/floors/{fid}/rooms/from-list",
        headers=h_adm,
        json={"room_numbers": "101", "capacity": 2},
    )

    await seed_user(db, email="m1@conc.edu", roll_no="C01", hostel_ids=[hid])
    await seed_user(db, email="m2@conc.edu", roll_no="C02", hostel_ids=[hid])
    h_m1 = await auth_headers(client, "m1@conc.edu")
    h_m2 = await auth_headers(client, "m2@conc.edu")

    cid = (
        await client.post(
            "/api/v1/admin/cycles",
            headers=h_adm,
            json={"name": "ConcCycle", "hostel_id": hid},
        )
    ).json()["_id"]
    await client.post(f"/api/v1/admin/cycles/{cid}/open", headers=h_adm)
    rid = (await client.get(f"/api/v1/cycles/{cid}/rooms", headers=h_m1)).json()[0]["room_id"]

    gid = (
        await client.post(
            f"/api/v1/cycles/{cid}/groups",
            headers=h_m1,
            json={"name": "ConcGroup", "solo": False},
        )
    ).json()["_id"]
    await client.post(f"/api/v1/groups/{gid}/invites", headers=h_m1, json={"roll_no": "C02"})
    invs = (await client.get(f"/api/v1/cycles/{cid}/invites/mine", headers=h_m2)).json()
    await client.post(f"/api/v1/invites/{invs[0]['_id']}/accept", headers=h_m2)

    await client.post(
        f"/api/v1/groups/{gid}/application/submit",
        headers=h_m1,
        json={"ranked_choices": [{"kind": "ROOM", "room_id": rid, "rank": 1}], "fallback": "NONE"},
    )
    await client.post(f"/api/v1/admin/cycles/{cid}/close-window", headers=h_adm)
    await client.post(f"/api/v1/admin/cycles/{cid}/allocate", headers=h_adm)

    allotment = (await client.get(f"/api/v1/cycles/{cid}/allotments/mine", headers=h_m1)).json()
    return allotment["_id"], cid, rid, h_m1, h_m2


@pytest.mark.asyncio
async def test_concurrent_two_members_accept_confirms_cleanly(live_env):
    """
    Both members of a HELD allotment send POST /accept concurrently over MongoDB rs0 transactions.
    Neither request should fail with WriteConflict; final state must be CONFIRMED with zero payment fields.
    """
    client, db, _ = live_env
    allotment_id, cid, rid, h_m1, h_m2 = await _prepare_held_two_member_allotment(client, db)

    r1, r2 = await asyncio.gather(
        client.post(f"/api/v1/allotments/{allotment_id}/accept", headers=h_m1),
        client.post(f"/api/v1/allotments/{allotment_id}/accept", headers=h_m2),
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    final = (await client.get(f"/api/v1/cycles/{cid}/allotments/mine", headers=h_m1)).json()
    assert final["status"] == "CONFIRMED"
    assert all(m["accept_status"] == "ACCEPTED" for m in final["members"])
    for m in final["members"]:
        for forbidden in ("payment_status", "paid_at", "payment_ref", "amount_paid"):
            assert forbidden not in m

    inv = await db["room_inventory"].find_one({"cycle_id": cid, "room_id": rid})
    assert inv["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_concurrent_duplicate_accept_same_member_is_idempotent(live_env):
    """Same member firing 10 concurrent /accept calls succeeds idempotently without confirming early."""
    client, db, _ = live_env
    allotment_id, cid, _, h_m1, _ = await _prepare_held_two_member_allotment(client, db)

    responses = await asyncio.gather(
        *[
            client.post(f"/api/v1/allotments/{allotment_id}/accept", headers=h_m1)
            for _ in range(10)
        ]
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses if r.status_code != 200]

    current = (await client.get(f"/api/v1/cycles/{cid}/allotments/mine", headers=h_m1)).json()
    # Second member is still PENDING so allotment remains HELD
    assert current["status"] == "HELD"


@pytest.mark.asyncio
async def test_concurrent_room_hold_only_one_wins(live_env):
    """20 simultaneous hold_room() calls on 1 AVAILABLE room -> strictly 1 succeeds."""
    from bson import ObjectId
    from app.repositories import catalogue as cat_repo

    _, db, _ = live_env
    await db["room_inventory"].insert_one({
        "cycle_id": "race_c1",
        "room_id": "race_r1",
        "hostel_id": "race_h1",
        "floor_no": 1,
        "capacity": 2,
        "status": "AVAILABLE",
        "allotment_id": None,
        "is_live": True,
        "version": 0,
    })

    results = await asyncio.gather(
        *[
            cat_repo.hold_room(db, "race_c1", "race_r1", str(ObjectId()))
            for _ in range(20)
        ]
    )
    assert results.count(True) == 1
    assert results.count(False) == 19
