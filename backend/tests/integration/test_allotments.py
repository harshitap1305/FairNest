"""Full end-to-end integration tests for FairNest allotment flows (NO payment)."""

from __future__ import annotations

import pytest
from bson import ObjectId

from tests.conftest import auth_headers, seed_user


async def _setup_hostel_and_rooms(client, admin_hdrs, *, code: str, room_numbers: str, default_cap: int = 2):
    r_h = await client.post(
        "/api/v1/admin/hostels",
        headers=admin_hdrs,
        json={"name": f"Hostel {code}", "code": code, "allowed_gender": "M", "allowed_years": [1, 2]},
    )
    assert r_h.status_code == 200, r_h.text
    hostel_id = r_h.json()["_id"]

    r_f = await client.post(
        f"/api/v1/admin/hostels/{hostel_id}/floors",
        headers=admin_hdrs,
        json={"floor_no": 1, "label": "Floor 1"},
    )
    assert r_f.status_code == 200, r_f.text
    floor_id = r_f.json()["_id"]

    # Dry-run preview first
    dry = await client.post(
        f"/api/v1/admin/floors/{floor_id}/rooms/from-list?dry_run=true",
        headers=admin_hdrs,
        json={"room_numbers": f"{room_numbers}, {room_numbers.split(',')[0].strip()}", "capacity": default_cap},
    )
    assert dry.status_code == 200, dry.text
    assert len(dry.json()["duplicates_in_input"]) >= 1

    # Commit creation (using skip_existing or clean list)
    r_rooms = await client.post(
        f"/api/v1/admin/floors/{floor_id}/rooms/from-list",
        headers=admin_hdrs,
        json={"room_numbers": room_numbers, "capacity": default_cap},
    )
    assert r_rooms.status_code == 200, r_rooms.text
    return hostel_id, floor_id


@pytest.mark.asyncio
async def test_full_lifecycle_accept_all_confirms_without_payment(live_env):
    """T1 & T2: Full flow -> group invite -> allocate -> both accept -> CONFIRMED (NO /pay) -> settle -> audit verifies."""
    client, db, _ = live_env
    await seed_user(db, email="admin@test.edu", role="SUPER_ADMIN", name="Super Admin")
    admin_hdrs = await auth_headers(client, "admin@test.edu")

    hostel_id, _ = await _setup_hostel_and_rooms(client, admin_hdrs, code="H1", room_numbers="101:2, 102:1")

    await seed_user(db, email="s1@test.edu", roll_no="B22001", role="STUDENT", hostel_ids=[hostel_id], credits=4)
    await seed_user(db, email="s2@test.edu", roll_no="B22002", role="STUDENT", hostel_ids=[hostel_id], credits=4)
    await seed_user(db, email="auditor@test.edu", role="AUDITOR")
    h_s1 = await auth_headers(client, "s1@test.edu")
    h_s2 = await auth_headers(client, "s2@test.edu")
    h_aud = await auth_headers(client, "auditor@test.edu")

    # Create & open cycle
    c_resp = await client.post(
        "/api/v1/admin/cycles",
        headers=admin_hdrs,
        json={"name": "Cycle 2026", "hostel_id": hostel_id, "freeze_hours": 48},
    )
    assert c_resp.status_code == 200
    cycle_id = c_resp.json()["_id"]

    # Seed secret hidden before allocation
    pre_c = await client.get(f"/api/v1/cycles/{cycle_id}", headers=admin_hdrs)
    assert "seed_secret" not in pre_c.json()

    open_resp = await client.post(f"/api/v1/admin/cycles/{cycle_id}/open", headers=admin_hdrs)
    assert open_resp.status_code == 200
    assert open_resp.json()["rooms_snapshotted"] == 2
    assert len(open_resp.json()["seed_commitment"]) == 64

    # Seed secret STILL hidden while APPLICATIONS_OPEN
    open_c = await client.get(f"/api/v1/cycles/{cycle_id}", headers=admin_hdrs)
    assert open_c.json()["seed_commitment"]
    assert "seed_secret" not in open_c.json()

    # Fetch rooms for cycle
    rooms_resp = await client.get(f"/api/v1/cycles/{cycle_id}/rooms", headers=h_s1)
    assert rooms_resp.status_code == 200
    cap2_room = next(r for r in rooms_resp.json() if r["capacity"] == 2)

    # Create 2-person group, invite s2, accept invite
    g_resp = await client.post(
        f"/api/v1/cycles/{cycle_id}/groups",
        headers=h_s1,
        json={"name": "Duo", "solo": False},
    )
    assert g_resp.status_code == 200
    group_id = g_resp.json()["_id"]

    inv_resp = await client.post(
        f"/api/v1/groups/{group_id}/invites",
        headers=h_s1,
        json={"roll_no": "B22002"},
    )
    assert inv_resp.status_code == 200

    mine_inv = await client.get(f"/api/v1/cycles/{cycle_id}/invites/mine", headers=h_s2)
    assert mine_inv.status_code == 200 and len(mine_inv.json()) == 1
    acc_inv = await client.post(f"/api/v1/invites/{mine_inv.json()[0]['_id']}/accept", headers=h_s2)
    assert acc_inv.status_code == 200
    assert acc_inv.json()["status"] == "READY"

    # Submit ranked preference for Room 101
    sub = await client.post(
        f"/api/v1/groups/{group_id}/application/submit",
        headers=h_s1,
        json={
            "ranked_choices": [{"kind": "ROOM", "room_id": cap2_room["room_id"], "rank": 1}],
            "fallback": "NONE",
        },
    )
    assert sub.status_code == 200
    assert sub.json()["status"] == "SUBMITTED"

    # Close window -> Preview -> Run Allocation
    cw = await client.post(f"/api/v1/admin/cycles/{cycle_id}/close-window", headers=admin_hdrs)
    assert cw.status_code == 200
    prev = await client.post(f"/api/v1/admin/cycles/{cycle_id}/preview-allocation", headers=admin_hdrs)
    assert prev.status_code == 200 and prev.json()["would_allot"] == 1 and prev.json()["dry_run"] is True

    alloc = await client.post(f"/api/v1/admin/cycles/{cycle_id}/allocate", headers=admin_hdrs)
    assert alloc.status_code == 200
    assert alloc.json()["allotted"] == 1

    # Re-running allocation must return 409 ALLOCATION_ALREADY_RUN
    alloc_dup = await client.post(f"/api/v1/admin/cycles/{cycle_id}/allocate", headers=admin_hdrs)
    assert alloc_dup.status_code == 409
    assert alloc_dup.json()["error"]["code"] == "ALLOCATION_ALREADY_RUN"

    # Member 1 accepts -> stays HELD
    a_mine = await client.get(f"/api/v1/cycles/{cycle_id}/allotments/mine", headers=h_s1)
    assert a_mine.status_code == 200
    allotment_id = a_mine.json()["_id"]
    assert a_mine.json()["status"] == "HELD"

    # Critical constraint: /pay endpoint must NOT exist (404)
    pay_resp = await client.post(f"/api/v1/allotments/{allotment_id}/pay", headers=h_s1)
    assert pay_resp.status_code == 404

    acc1 = await client.post(f"/api/v1/allotments/{allotment_id}/accept", headers=h_s1)
    assert acc1.status_code == 200
    assert acc1.json()["status"] == "HELD"

    # Member 2 accepts -> immediately becomes CONFIRMED (zero payment!)
    acc2 = await client.post(f"/api/v1/allotments/{allotment_id}/accept", headers=h_s2)
    assert acc2.status_code == 200
    assert acc2.json()["status"] == "CONFIRMED"
    assert "payment_status" not in acc2.json()

    # Check room inventory is CONFIRMED
    inv_doc = await db["room_inventory"].find_one({"cycle_id": cycle_id, "room_id": cap2_room["room_id"]})
    assert inv_doc["status"] == "CONFIRMED"

    # Auditor verifies allocation hashes (must succeed even AFTER confirmation)
    aud = await client.get(f"/api/v1/cycles/{cycle_id}/audit", headers=h_aud)
    assert aud.status_code == 200
    assert aud.json()["ok"] is True
    assert aud.json()["checks"] == {"seed_ok": True, "input_ok": True, "output_ok": True}

    # Settle cycle -> credits decrease by 3 for rank 1 (4 -> 1) and is_live released
    settle_res = await client.post(f"/api/v1/admin/cycles/{cycle_id}/settle", headers=admin_hdrs)
    assert settle_res.status_code == 200
    assert settle_res.json()["settled_users"] == 2

    # Idempotent second settle settles 0 additional rows
    settle_dup = await client.post(f"/api/v1/admin/cycles/{cycle_id}/settle", headers=admin_hdrs)
    assert settle_dup.status_code == 200
    assert settle_dup.json()["settled_users"] == 0

    cred1 = await client.get("/api/v1/me/credits", headers=h_s1)
    assert cred1.json()["credits"] == 1
    fair1 = await client.get(f"/api/v1/me/fairness?cycle_id={cycle_id}", headers=h_s1)
    assert fair1.status_code == 200
    assert fair1.json()["allotment"]["status"] == "CONFIRMED"

    # Room can now be included in a second release because is_live became False
    c2_resp = await client.post(
        "/api/v1/admin/cycles",
        headers=admin_hdrs,
        json={"name": "Cycle 2026-B", "hostel_id": hostel_id, "freeze_hours": 48},
    )
    open2 = await client.post(f"/api/v1/admin/cycles/{c2_resp.json()['_id']}/open", headers=admin_hdrs)
    assert open2.status_code == 200


@pytest.mark.asyncio
async def test_decline_triggers_cascade_and_credit_settlement(live_env):
    """T3: Held allotment declined -> FORFEITED (-2) -> waitlisted group auto-offered in Round-2 cascade."""
    client, db, _ = live_env
    await seed_user(db, email="admin@test.edu", role="SUPER_ADMIN")
    admin_hdrs = await auth_headers(client, "admin@test.edu")
    hostel_id, _ = await _setup_hostel_and_rooms(client, admin_hdrs, code="HCASC", room_numbers="101:1")

    # s_acc has Tier-0 accessibility so guaranteed to win Round 1 over s_wait
    await seed_user(
        db, email="acc@test.edu", roll_no="B22010", hostel_ids=[hostel_id], accessibility_verified=True, credits=3
    )
    await seed_user(
        db, email="wait@test.edu", roll_no="B22011", hostel_ids=[hostel_id], accessibility_verified=False, credits=5
    )
    h_acc = await auth_headers(client, "acc@test.edu")
    h_wait = await auth_headers(client, "wait@test.edu")

    c_id = (await client.post("/api/v1/admin/cycles", headers=admin_hdrs, json={"name": "C1", "hostel_id": hostel_id})).json()["_id"]
    await client.post(f"/api/v1/admin/cycles/{c_id}/open", headers=admin_hdrs)
    room_id = (await client.get(f"/api/v1/cycles/{c_id}/rooms", headers=h_acc)).json()[0]["room_id"]

    # Second cycle open attempt on same room fails with ROOM_IN_LIVE_RELEASE
    c_dup = (await client.post("/api/v1/admin/cycles", headers=admin_hdrs, json={"name": "Dup", "hostel_id": hostel_id})).json()["_id"]
    open_dup = await client.post(f"/api/v1/admin/cycles/{c_dup}/open", headers=admin_hdrs)
    assert open_dup.status_code == 409
    assert open_dup.json()["error"]["code"] == "ROOM_IN_LIVE_RELEASE"

    # Both create solo groups & submit Room 101
    for hdrs in (h_acc, h_wait):
        g = await client.post(f"/api/v1/cycles/{c_id}/groups", headers=hdrs, json={"solo": True})
        gid = g.json()["_id"]
        sub = await client.post(
            f"/api/v1/groups/{gid}/application/submit",
            headers=hdrs,
            json={"ranked_choices": [{"kind": "ROOM", "room_id": room_id, "rank": 1}], "fallback": "NONE"},
        )
        assert sub.status_code == 200

    await client.post(f"/api/v1/admin/cycles/{c_id}/close-window", headers=admin_hdrs)
    await client.post(f"/api/v1/admin/cycles/{c_id}/allocate", headers=admin_hdrs)

    # Tier-0 student got HELD, s_wait is WAITLISTED
    a_acc = await client.get(f"/api/v1/cycles/{c_id}/allotments/mine", headers=h_acc)
    assert a_acc.json()["status"] == "HELD"
    a_wait_before = await client.get(f"/api/v1/cycles/{c_id}/allotments/mine", headers=h_wait)
    assert a_wait_before.json() is None

    # Tier-0 student declines -> triggers automatic cascade offering Room 101 to s_wait in Round 2!
    dec = await client.post(f"/api/v1/allotments/{a_acc.json()['_id']}/decline", headers=h_acc)
    assert dec.status_code == 200
    assert dec.json()["status"] == "DECLINED"

    a_wait_after = await client.get(f"/api/v1/cycles/{c_id}/allotments/mine", headers=h_wait)
    assert a_wait_after.json() is not None
    assert a_wait_after.json()["status"] == "HELD"
    assert a_wait_after.json()["round_no"] == 2

    # Waitlisted winner accepts -> CONFIRMED
    acc_wait = await client.post(f"/api/v1/allotments/{a_wait_after.json()['_id']}/accept", headers=h_wait)
    assert acc_wait.json()["status"] == "CONFIRMED"

    # Settle -> decliner loses 2 credits (3 -> 1), cascade winner rank 1 loses 3 (5 -> 2)
    settle_res = await client.post(f"/api/v1/admin/cycles/{c_id}/settle", headers=admin_hdrs)
    assert settle_res.status_code == 200
    assert (await client.get("/api/v1/me/credits", headers=h_acc)).json()["credits"] == 1
    assert (await client.get("/api/v1/me/credits", headers=h_wait)).json()["credits"] == 2


@pytest.mark.asyncio
async def test_cancel_and_admin_revoke_outcomes(live_env):
    """Cancel -> LATE_CANCELLED (-1); Admin revoke -> REVOKED (0 penalty + reinsert priority)."""
    client, db, _ = live_env
    await seed_user(db, email="admin@test.edu", role="SUPER_ADMIN")
    admin_hdrs = await auth_headers(client, "admin@test.edu")
    hostel_id, _ = await _setup_hostel_and_rooms(client, admin_hdrs, code="HREV", room_numbers="101:1, 102:1")

    await seed_user(db, email="sc@test.edu", roll_no="B22021", hostel_ids=[hostel_id], credits=4)
    await seed_user(db, email="sr@test.edu", roll_no="B22022", hostel_ids=[hostel_id], credits=4)
    h_c = await auth_headers(client, "sc@test.edu")
    h_r = await auth_headers(client, "sr@test.edu")

    c_id = (await client.post("/api/v1/admin/cycles", headers=admin_hdrs, json={"name": "RevokeTest", "hostel_id": hostel_id})).json()["_id"]
    await client.post(f"/api/v1/admin/cycles/{c_id}/open", headers=admin_hdrs)
    rooms = (await client.get(f"/api/v1/cycles/{c_id}/rooms", headers=h_c)).json()

    for idx, hdrs in enumerate((h_c, h_r)):
        gid = (await client.post(f"/api/v1/cycles/{c_id}/groups", headers=hdrs, json={"solo": True})).json()["_id"]
        await client.post(
            f"/api/v1/groups/{gid}/application/submit",
            headers=hdrs,
            json={"ranked_choices": [{"kind": "ROOM", "room_id": rooms[idx]["room_id"], "rank": 1}], "fallback": "NONE"},
        )

    await client.post(f"/api/v1/admin/cycles/{c_id}/close-window", headers=admin_hdrs)
    await client.post(f"/api/v1/admin/cycles/{c_id}/allocate", headers=admin_hdrs)

    a_c = (await client.get(f"/api/v1/cycles/{c_id}/allotments/mine", headers=h_c)).json()
    a_r = (await client.get(f"/api/v1/cycles/{c_id}/allotments/mine", headers=h_r)).json()

    # s_cancel accepts -> CONFIRMED -> then cancels -> status CANCELLED (late cancel penalty -1)
    await client.post(f"/api/v1/allotments/{a_c['_id']}/accept", headers=h_c)
    c_resp = await client.post(f"/api/v1/allotments/{a_c['_id']}/cancel", headers=h_c)
    assert c_resp.status_code == 200
    assert c_resp.json()["status"] == "CANCELLED"

    # Admin revokes s_revoke's hold with audit reason -> reinserted top of waitlist -> cascade gives them room 101 or 102!
    rev_resp = await client.post(
        f"/api/v1/admin/allotments/{a_r['_id']}/revoke",
        headers=admin_hdrs,
        json={"reason": "Maintenance emergency discovered on pipeline"},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["status"] == "REVOKED"

    # s_revoke got offered another room via cascade because of reinsert=True!
    a_r2 = (await client.get(f"/api/v1/cycles/{c_id}/allotments/mine", headers=h_r)).json()
    assert a_r2 is not None and a_r2["status"] == "HELD"
    # Even if revoked twice / left revoked without accepting another offer? Wait: if s_revoke declines doesn't happen, let's verify revoke without free rooms leaves 0 penalty!
    # Here let's settle after declining? Actually accept room and check s_cancel lost 1 credit (4 -> 3)!
    await client.post(f"/api/v1/allotments/{a_r2['_id']}/accept", headers=h_r)
    await client.post(f"/api/v1/admin/cycles/{c_id}/settle", headers=admin_hdrs)
    assert (await client.get("/api/v1/me/credits", headers=h_c)).json()["credits"] == 3  # 4 - 1 = 3


@pytest.mark.asyncio
async def test_health_and_unauthenticated_endpoints(live_env):
    client, _, _ = live_env
    live = await client.get("/api/v1/health/live")
    assert live.status_code == 200 and live.json()["status"] == "ok"

    ready = await client.get("/api/v1/health/ready")
    assert ready.status_code == 200 and ready.json()["db"] == "connected"

    pay = await client.post(f"/api/v1/allotments/{ObjectId()}/pay")
    assert pay.status_code == 404

    allot_me = await client.get("/api/v1/allotments/me")
    assert allot_me.status_code == 401

    login_err = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "nobody@nowhere.invalid", "password": "wrong_password_123"},
    )
    assert login_err.status_code == 401
    msg = login_err.json()["error"]["message"].lower()
    assert "not found" not in msg and "does not exist" not in msg


@pytest.mark.asyncio
async def test_worker_grace_expiry_cascade_and_cycle_closure(live_env):
    """Worker auto-grace extend -> expiry FORFEITED + cascade -> accept -> auto close & release is_live."""
    from datetime import timedelta

    from app import worker
    from app.core import clock as _clock

    client, db, raw_client = live_env
    await seed_user(db, email="admin@test.edu", role="SUPER_ADMIN")
    admin_hdrs = await auth_headers(client, "admin@test.edu")
    hostel_id, _ = await _setup_hostel_and_rooms(client, admin_hdrs, code="HWRK", room_numbers="101:1")

    await seed_user(db, email="w_acc@test.edu", roll_no="B22031", hostel_ids=[hostel_id], accessibility_verified=True)
    await seed_user(db, email="w_wait@test.edu", roll_no="B22032", hostel_ids=[hostel_id], accessibility_verified=False)
    h_acc = await auth_headers(client, "w_acc@test.edu")
    h_wait = await auth_headers(client, "w_wait@test.edu")

    c_id = (await client.post("/api/v1/admin/cycles", headers=admin_hdrs, json={"name": "WorkerCycle", "hostel_id": hostel_id, "freeze_hours": 1})).json()["_id"]
    await client.post(f"/api/v1/admin/cycles/{c_id}/open", headers=admin_hdrs)
    rooms = (await client.get(f"/api/v1/cycles/{c_id}/rooms", headers=h_acc)).json()
    rid = rooms[0]["room_id"]

    for hdrs in (h_acc, h_wait):
        gid = (await client.post(f"/api/v1/cycles/{c_id}/groups", headers=hdrs, json={"solo": True})).json()["_id"]
        await client.post(
            f"/api/v1/groups/{gid}/application/submit",
            headers=hdrs,
            json={"ranked_choices": [{"kind": "ROOM", "room_id": rid, "rank": 1}], "fallback": "NONE"},
        )

    await client.post(f"/api/v1/admin/cycles/{c_id}/close-window", headers=admin_hdrs)
    await client.post(f"/api/v1/admin/cycles/{c_id}/allocate", headers=admin_hdrs)

    hold1 = (await client.get(f"/api/v1/cycles/{c_id}/allotments/mine", headers=h_acc)).json()
    assert hold1["status"] == "HELD"

    # Advance fake clock past initial freeze deadline -> 1st worker pass applies 10-minute grace extension
    base_now = _clock.now()
    _clock.set_now(base_now + timedelta(hours=2))
    await worker.run_expire_holds(db, raw_client)
    hold1_after_grace = await db["allotments"].find_one({"_id": ObjectId(hold1["_id"])})
    assert hold1_after_grace["status"] == "HELD"
    assert hold1_after_grace["grace_used"] is True

    # Advance fake clock past grace -> 2nd worker pass expires hold, forfeits app, triggers cascade to w_wait
    _clock.set_now(base_now + timedelta(hours=3))
    await worker.run_expire_holds(db, raw_client)
    hold1_expired = await db["allotments"].find_one({"_id": ObjectId(hold1["_id"])})
    assert hold1_expired["status"] == "EXPIRED"
    assert hold1_expired["is_active"] is False

    hold2 = (await client.get(f"/api/v1/cycles/{c_id}/allotments/mine", headers=h_wait)).json()
    assert hold2 is not None and hold2["status"] == "HELD" and hold2["round_no"] == 2

    # Waitlist winner accepts -> all rooms consumed -> worker auto-closes cycle and clears is_live
    acc = await client.post(f"/api/v1/allotments/{hold2['_id']}/accept", headers=h_wait)
    assert acc.status_code == 200 and acc.json()["status"] == "CONFIRMED"

    await worker.run_close_cycle_check(db, raw_client)
    cycle_doc = await db["cycles"].find_one({"_id": ObjectId(c_id)})
    assert cycle_doc["status"] == "CLOSED"
    live_count = await db["room_inventory"].count_documents({"cycle_id": c_id, "is_live": True})
    assert live_count == 0
    assert await worker.run_invariant_check(db) == []
