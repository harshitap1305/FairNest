"""API tests for CSV exports (allotment roster + audit log)."""

from __future__ import annotations

import csv
import io

import pytest

from tests.conftest import auth_headers, seed_user
from tests.integration.test_insights_api import _open_cycle_with_solo_apps, _submit


def _parse(resp) -> list[dict]:
    text = resp.text.lstrip("﻿")
    return list(csv.DictReader(io.StringIO(text)))


@pytest.mark.asyncio
async def test_allotment_roster_csv(live_env):
    client, db, _ = live_env
    admin, hostel_id, cycle_id, students, rooms = await _open_cycle_with_solo_apps(
        client, db, 2, "101:1, 102:1"
    )
    # A name that looks like a spreadsheet formula must be neutralised in the export
    await db["users"].update_one({"email": "s0@test.edu"}, {"$set": {"name": "=EVIL()"}})
    by_no = {r["room_no"]: r["room_id"] for r in rooms}
    await _submit(client, cycle_id, students[0], [by_no["101"]])
    await _submit(client, cycle_id, students[1], [by_no["102"]])
    await client.post(f"/api/v1/admin/cycles/{cycle_id}/close-window", headers=admin)
    assert (await client.post(f"/api/v1/admin/cycles/{cycle_id}/allocate", headers=admin)).status_code == 200

    resp = await client.get(f"/api/v1/admin/cycles/{cycle_id}/allotments.csv", headers=admin)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    rows = _parse(resp)
    assert [r["room_no"] for r in rows] == ["101", "102"]
    assert {r["allotment_status"] for r in rows} == {"HELD"}
    assert rows[0]["member_name"] == "'=EVIL()"
    assert rows[1]["roll_no"] == "B23001"

    only_confirmed = await client.get(
        f"/api/v1/admin/cycles/{cycle_id}/allotments.csv", params={"status": "confirmed"}, headers=admin
    )
    assert _parse(only_confirmed) == []


@pytest.mark.asyncio
async def test_allotment_csv_requires_staff_in_scope(live_env):
    client, db, _ = live_env
    _, _, cycle_id, students, _ = await _open_cycle_with_solo_apps(client, db, 1, "101:1")
    assert (await client.get(f"/api/v1/admin/cycles/{cycle_id}/allotments.csv", headers=students[0])).status_code == 403

    await seed_user(db, email="warden@test.edu", role="WARDEN", managed_hostel_ids=[])
    warden = await auth_headers(client, "warden@test.edu")
    resp = await client.get(f"/api/v1/admin/cycles/{cycle_id}/allotments.csv", headers=warden)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "HOSTEL_SCOPE_DENIED"
    assert (await client.get("/api/v1/admin/cycles/bad-id/allotments.csv", headers=warden)).status_code == 404


@pytest.mark.asyncio
async def test_audit_log_csv(live_env):
    client, db, _ = live_env
    await seed_user(db, email="auditor@test.edu", role="AUDITOR")
    hdrs = await auth_headers(client, "auditor@test.edu")
    resp = await client.get("/api/v1/admin/audit-logs.csv", params={"action": "LOGIN_SUCCESS"}, headers=hdrs)
    assert resp.status_code == 200
    rows = _parse(resp)
    assert len(rows) == 1
    assert rows[0]["action"] == "LOGIN_SUCCESS" and rows[0]["actor"] == "auditor@test.edu"
