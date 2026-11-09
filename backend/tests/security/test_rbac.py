"""Security tests: RBAC hierarchy, hostel scope isolation, IDOR, refresh token reuse, no payment."""

from __future__ import annotations

import pytest
from bson import ObjectId

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from tests.conftest import auth_headers, seed_user


@pytest.mark.asyncio
async def test_unauthenticated_guards_and_no_pay_endpoint(live_env):
    client, _, _ = live_env
    fake = str(ObjectId())

    assert (await client.get("/api/v1/allotments/mine")).status_code == 401
    assert (await client.post(f"/api/v1/allotments/{fake}/accept")).status_code == 401
    assert (await client.post(f"/api/v1/admin/cycles/{fake}/open")).status_code == 401
    assert (await client.post(f"/api/v1/admin/cycles/{fake}/allocate")).status_code == 401
    assert (await client.post(f"/api/v1/admin/cycles/{fake}/settle")).status_code == 401
    assert (await client.post("/api/v1/admin/role-grants", json={"email": "x@y.edu", "role": "ADMIN"})).status_code == 401
    assert (await client.post(f"/api/v1/allotments/{fake}/pay")).status_code == 404


@pytest.mark.asyncio
async def test_student_idor_blocked(live_env):
    """T13: Student B cannot access/accept/decline Student A's application, allotment, or hidden hostel."""
    client, db, _ = live_env
    await seed_user(db, email="sa@sec.edu", role="SUPER_ADMIN")
    h_sa = await auth_headers(client, "sa@sec.edu")

    hid_a = (await client.post("/api/v1/admin/hostels", headers=h_sa, json={"name": "Hostel A", "code": "HA"})).json()["_id"]
    hid_b = (await client.post("/api/v1/admin/hostels", headers=h_sa, json={"name": "Hostel B", "code": "HB"})).json()["_id"]
    fid_a = (await client.post(f"/api/v1/admin/hostels/{hid_a}/floors", headers=h_sa, json={"floor_no": 1})).json()["_id"]
    await client.post(f"/api/v1/admin/floors/{fid_a}/rooms/from-list", headers=h_sa, json={"room_numbers": "101", "capacity": 1})

    await seed_user(db, email="stu_a@sec.edu", roll_no="S01", hostel_ids=[hid_a])
    await seed_user(db, email="stu_a2@sec.edu", roll_no="S02", hostel_ids=[hid_a])
    await seed_user(db, email="stu_b@sec.edu", roll_no="S03", hostel_ids=[hid_b])
    h_a = await auth_headers(client, "stu_a@sec.edu")
    h_a2 = await auth_headers(client, "stu_a2@sec.edu")
    h_b = await auth_headers(client, "stu_b@sec.edu")

    cid = (await client.post("/api/v1/admin/cycles", headers=h_sa, json={"name": "CycleA", "hostel_id": hid_a})).json()["_id"]
    await client.post(f"/api/v1/admin/cycles/{cid}/open", headers=h_sa)
    rid = (await client.get(f"/api/v1/cycles/{cid}/rooms", headers=h_a)).json()[0]["room_id"]

    # Student B (hostel B) cannot view hostel A cycle (404 avoids leaking existence)
    assert (await client.get(f"/api/v1/cycles/{cid}", headers=h_b)).status_code == 404

    gid_a = (await client.post(f"/api/v1/cycles/{cid}/groups", headers=h_a, json={"solo": True})).json()["_id"]
    await client.post(
        f"/api/v1/groups/{gid_a}/application/submit",
        headers=h_a,
        json={"ranked_choices": [{"kind": "ROOM", "room_id": rid, "rank": 1}], "fallback": "NONE"},
    )

    # Another student in same hostel cannot read/edit Student A's application
    assert (await client.get(f"/api/v1/groups/{gid_a}/application", headers=h_a2)).status_code == 404
    assert (
        await client.put(
            f"/api/v1/groups/{gid_a}/application",
            headers=h_a2,
            json={"ranked_choices": [], "fallback": "NONE"},
        )
    ).status_code == 403

    await client.post(f"/api/v1/admin/cycles/{cid}/close-window", headers=h_sa)
    await client.post(f"/api/v1/admin/cycles/{cid}/allocate", headers=h_sa)
    allotment_id = (await client.get(f"/api/v1/cycles/{cid}/allotments/mine", headers=h_a)).json()["_id"]

    # Student A2 cannot accept or decline Student A's allotment
    assert (await client.post(f"/api/v1/allotments/{allotment_id}/accept", headers=h_a2)).status_code == 404
    assert (await client.post(f"/api/v1/allotments/{allotment_id}/decline", headers=h_a2)).status_code == 404


@pytest.mark.asyncio
async def test_refresh_token_reuse_revokes_entire_family(live_env):
    """T15: Rotating a refresh token and replaying the old token revokes the entire token family."""
    client, db, _ = live_env
    await seed_user(db, email="rt@sec.edu", role="STUDENT")

    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "rt@sec.edu", "password": "StrongPass123!"},
    )
    assert login.status_code == 200
    t1 = login.cookies.get("refresh_token")
    assert t1

    # Legitimate rotation T1 -> T2
    client.cookies.clear()
    ref1 = await client.post("/api/v1/auth/refresh", cookies={"refresh_token": t1})
    assert ref1.status_code == 200
    t2 = ref1.cookies.get("refresh_token")
    assert t2 and t2 != t1

    # Replay stale token T1 -> triggers TOKEN_REUSE and revokes T2's family
    client.cookies.clear()
    replay = await client.post("/api/v1/auth/refresh", cookies={"refresh_token": t1})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "TOKEN_REUSE"

    # Subsequent use of T2 must now fail too because entire family was revoked
    client.cookies.clear()
    ref2 = await client.post("/api/v1/auth/refresh", cookies={"refresh_token": t2})
    assert ref2.status_code == 401


@pytest.mark.asyncio
async def test_hostel_scope_rbac_role_hierarchy_and_last_super_admin(live_env):
    """T21, T22, T23: Hostel scoping, Auditor read-only isolation, Admin->Warden limit, last SUPER_ADMIN guard."""
    client, db, _ = live_env
    sa = await seed_user(db, email="sa@sec.edu", role="SUPER_ADMIN")
    h_sa = await auth_headers(client, "sa@sec.edu")

    hid_a = (await client.post("/api/v1/admin/hostels", headers=h_sa, json={"name": "North", "code": "N1"})).json()["_id"]
    hid_b = (await client.post("/api/v1/admin/hostels", headers=h_sa, json={"name": "South", "code": "S1"})).json()["_id"]

    await seed_user(db, email="adm_a@sec.edu", role="ADMIN", managed_hostel_ids=[hid_a])
    await seed_user(db, email="aud@sec.edu", role="AUDITOR")
    stu_b = await seed_user(db, email="st_b@sec.edu", roll_no="SB01", hostel_ids=[hid_b])
    await seed_user(db, email="target@sec.edu", role="STUDENT")

    h_adm_a = await auth_headers(client, "adm_a@sec.edu")
    h_aud = await auth_headers(client, "aud@sec.edu")

    # Hostel-scoped ADMIN for hid_a cannot create a cycle for hid_b
    bad_cyc = await client.post(
        "/api/v1/admin/cycles",
        headers=h_adm_a,
        json={"name": "OutOfScope", "hostel_id": hid_b},
    )
    assert bad_cyc.status_code == 403
    assert bad_cyc.json()["error"]["code"] == "HOSTEL_SCOPE_DENIED"

    # Hostel-scoped ADMIN cannot verify accessibility for student in hid_b
    bad_acc = await client.put(
        f"/api/v1/warden/users/{stu_b['_id']}/accessibility",
        headers=h_adm_a,
        json={"verified": True},
    )
    assert bad_acc.status_code == 403

    # ADMIN can only grant WARDEN for own hostels (not ADMIN, not hid_b)
    bad_grant_role = await client.post(
        "/api/v1/admin/role-grants",
        headers=h_adm_a,
        json={"email": "target@sec.edu", "role": "ADMIN", "hostel_ids": [hid_a]},
    )
    assert bad_grant_role.status_code == 403

    bad_grant_hostel = await client.post(
        "/api/v1/admin/role-grants",
        headers=h_adm_a,
        json={"email": "target@sec.edu", "role": "WARDEN", "hostel_ids": [hid_b]},
    )
    assert bad_grant_hostel.status_code == 403

    ok_grant = await client.post(
        "/api/v1/admin/role-grants",
        headers=h_adm_a,
        json={"email": "target@sec.edu", "role": "WARDEN", "hostel_ids": [hid_a]},
    )
    assert ok_grant.status_code == 200 and ok_grant.json()["status"] == "ACTIVE"

    # AUDITOR can access fairness/audit reports but cannot mutate hostels/cycles
    assert (await client.get("/api/v1/reports/fairness", headers=h_aud)).status_code == 200
    assert (await client.post("/api/v1/admin/hostels", headers=h_aud, json={"name": "X", "code": "X"})).status_code == 403
    assert (await client.post("/api/v1/admin/cycles", headers=h_aud, json={"name": "X", "hostel_id": hid_a})).status_code == 403

    # Cannot disable the last active SUPER_ADMIN
    dis = await client.put(f"/api/v1/admin/users/{sa['_id']}/disable", headers=h_sa)
    assert dis.status_code == 409
    assert dis.json()["error"]["code"] == "LAST_SUPER_ADMIN"


def test_argon2_hashing_and_jwt_secret_strength():
    pw = "test_password_secure_123"
    hashed = hash_password(pw)
    assert hashed.startswith("$argon2")
    assert verify_password(pw, hashed) is True
    assert verify_password("wrong", hashed) is False
    assert len(get_settings().JWT_SECRET) >= 32
