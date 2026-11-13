"""API tests for GET /reports/overview."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core import clock as _clock
from tests.conftest import auth_headers, seed_user
from tests.integration.test_insights_api import _open_cycle_with_solo_apps, _submit


@pytest.mark.asyncio
async def test_overview_counts_and_expiring_holds(live_env):
    client, db, _ = live_env
    admin, hostel_id, cycle_id, students, rooms = await _open_cycle_with_solo_apps(
        client, db, 3, "101:1, 102:1"
    )
    by_no = {r["room_no"]: r["room_id"] for r in rooms}
    for hdrs in students:
        await _submit(client, cycle_id, hdrs, [by_no["101"], by_no["102"]])

    before = (await client.get("/api/v1/reports/overview", headers=admin)).json()
    row = next(c for c in before["cycles"] if c["cycle_id"] == cycle_id)
    assert row["status"] == "APPLICATIONS_OPEN"
    assert row["applications"] == 3 and row["rooms_total"] == 2
    assert row["hostel_name"] == "Hostel HINS"

    await client.post(f"/api/v1/admin/cycles/{cycle_id}/close-window", headers=admin)
    await client.post(f"/api/v1/admin/cycles/{cycle_id}/allocate", headers=admin)

    # Freeze window is 24h: nothing is "expiring soon" yet
    after = (await client.get("/api/v1/reports/overview", headers=admin)).json()
    row = next(c for c in after["cycles"] if c["cycle_id"] == cycle_id)
    assert (row["held"], row["waitlisted"], row["confirmed"]) == (2, 1, 0)
    assert after["totals"]["held"] == 2 and after["attention"]["expiring_holds"] == []

    # 20h later both holds are inside the 6h attention window
    _clock.set_now(_clock.now() + timedelta(hours=20))
    late = (await client.get("/api/v1/reports/overview", headers=admin)).json()
    holds = late["attention"]["expiring_holds"]
    assert len(holds) == 2
    assert {h["room_no"] for h in holds} == {"101", "102"}
    assert all(h["pending_members"] == 1 for h in holds)


@pytest.mark.asyncio
async def test_overview_is_scoped_to_managed_hostels(live_env):
    client, db, _ = live_env
    await _open_cycle_with_solo_apps(client, db, 1, "101:1")
    await seed_user(db, email="warden@test.edu", role="WARDEN", managed_hostel_ids=[])
    warden = await auth_headers(client, "warden@test.edu")
    resp = await client.get("/api/v1/reports/overview", headers=warden)
    assert resp.status_code == 200
    assert resp.json()["cycles"] == [] and resp.json()["totals"]["applications"] == 0

    student = await auth_headers(client, "s0@test.edu")
    assert (await client.get("/api/v1/reports/overview", headers=student)).status_code == 403
