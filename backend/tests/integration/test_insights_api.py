"""API tests for /cycles/{id}/room-demand and /cycles/{id}/waitlist/me."""

from __future__ import annotations

import pytest

from tests.conftest import auth_headers, seed_user
from tests.integration.test_allotments import _setup_hostel_and_rooms


async def _open_cycle_with_solo_apps(client, db, n_students: int, rooms: str):
    await seed_user(db, email="admin@test.edu", role="SUPER_ADMIN")
    admin = await auth_headers(client, "admin@test.edu")
    hostel_id, _ = await _setup_hostel_and_rooms(client, admin, code="HINS", room_numbers=rooms)
    cycle_id = (await client.post(
        "/api/v1/admin/cycles", headers=admin,
        json={"name": "Insights", "hostel_id": hostel_id, "freeze_hours": 24},
    )).json()["_id"]
    assert (await client.post(f"/api/v1/admin/cycles/{cycle_id}/open", headers=admin)).status_code == 200

    students = []
    for i in range(n_students):
        email = f"s{i}@test.edu"
        await seed_user(db, email=email, roll_no=f"B2300{i}", hostel_ids=[hostel_id])
        students.append(await auth_headers(client, email))
    room_list = (await client.get(f"/api/v1/cycles/{cycle_id}/rooms", headers=students[0])).json()
    return admin, hostel_id, cycle_id, students, room_list


async def _submit(client, cycle_id, hdrs, room_ids):
    gid = (await client.post(f"/api/v1/cycles/{cycle_id}/groups", headers=hdrs, json={"solo": True})).json()["_id"]
    resp = await client.post(
        f"/api/v1/groups/{gid}/application/submit",
        headers=hdrs,
        json={
            "ranked_choices": [{"kind": "ROOM", "room_id": r, "rank": i + 1} for i, r in enumerate(room_ids)],
            "fallback": "NONE",
        },
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_room_demand_is_hidden_until_enough_applications(live_env):
    client, db, _ = live_env
    _, _, cycle_id, students, rooms = await _open_cycle_with_solo_apps(client, db, 3, "101:1, 102:1, 103:1")
    by_no = {r["room_no"]: r["room_id"] for r in rooms}

    await _submit(client, cycle_id, students[0], [by_no["101"], by_no["102"]])
    early = (await client.get(f"/api/v1/cycles/{cycle_id}/room-demand", headers=students[0])).json()
    assert early["insufficient_data"] is True and early["rooms"] == {}
    assert early["by_size"][0]["groups"] == 1

    await _submit(client, cycle_id, students[1], [by_no["101"]])
    await _submit(client, cycle_id, students[2], [by_no["102"], by_no["101"]])
    resp = await client.get(f"/api/v1/cycles/{cycle_id}/room-demand", headers=students[0])
    assert resp.status_code == 200
    d = resp.json()
    assert d["insufficient_data"] is False and d["applications_counted"] == 3
    assert d["rooms"][by_no["101"]]["first_choice"] == 2
    assert d["rooms"][by_no["101"]]["level"] == "HIGH"
    assert d["rooms"][by_no["103"]]["level"] == "NONE"
    assert d["by_size"] == [{"group_size": 1, "groups": 3, "matching_rooms": 3, "groups_per_room": 1.0}]


@pytest.mark.asyncio
async def test_room_demand_respects_hostel_scope(live_env):
    client, db, _ = live_env
    _, _, cycle_id, _, _ = await _open_cycle_with_solo_apps(client, db, 1, "101:1")
    await seed_user(db, email="outsider@test.edu", roll_no="X1", hostel_ids=[])
    outsider = await auth_headers(client, "outsider@test.edu")
    resp = await client.get(f"/api/v1/cycles/{cycle_id}/room-demand", headers=outsider)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_waitlist_position_after_allocation(live_env):
    client, db, _ = live_env
    admin, _, cycle_id, students, rooms = await _open_cycle_with_solo_apps(client, db, 3, "101:1")
    rid = rooms[0]["room_id"]
    for hdrs in students:
        await _submit(client, cycle_id, hdrs, [rid])

    # No group yet -> clean 404 for a student who never applied
    await seed_user(db, email="late@test.edu", roll_no="L1", hostel_ids=[rooms[0]["hostel_id"]])
    late = await auth_headers(client, "late@test.edu")
    assert (await client.get(f"/api/v1/cycles/{cycle_id}/waitlist/me", headers=late)).status_code == 404

    await client.post(f"/api/v1/admin/cycles/{cycle_id}/close-window", headers=admin)
    assert (await client.post(f"/api/v1/admin/cycles/{cycle_id}/allocate", headers=admin)).status_code == 200

    results = [
        (await client.get(f"/api/v1/cycles/{cycle_id}/waitlist/me", headers=h)).json() for h in students
    ]
    waiting = sorted((r for r in results if r["on_waitlist"]), key=lambda r: r["position"])
    held = [r for r in results if not r["on_waitlist"]]
    assert len(held) == 1 and held[0]["status"] == "ALLOTTED"
    assert [r["position"] for r in waiting] == [1, 2]
    assert all(r["total_waitlisted"] == 2 for r in waiting)
    assert waiting[1]["ahead_same_size"] == 1
    assert all(r["fitting_rooms_available"] == 0 for r in waiting)  # the only room is HELD
