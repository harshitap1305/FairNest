"""Integration tests for the account security endpoints (sessions + activity)."""

from __future__ import annotations

import pytest

from tests.conftest import seed_user


async def _login(client, identifier: str, password: str = "StrongPass123!", ua: str = "pytest"):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
        headers={"User-Agent": ua},
    )
    return resp


@pytest.mark.asyncio
async def test_sessions_flag_the_current_device(live_env):
    client, db, _ = live_env
    await seed_user(db, email="me@test.edu", roll_no="R1")

    # First device logs in, then a second device logs in through the same client
    first = await _login(client, "me@test.edu", ua="Laptop Firefox")
    first_cookie = first.cookies.get("refresh_token")
    second = await _login(client, "me@test.edu", ua="Phone Chrome")
    token = second.json()["access_token"]
    hdrs = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/auth/sessions", headers=hdrs)
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 2
    assert sessions[0]["current"] is True and sessions[0]["user_agent"] == "Phone Chrome"
    assert sessions[1]["current"] is False and sessions[1]["user_agent"] == "Laptop Firefox"

    # Without any refresh cookie nothing is marked current
    client.cookies.clear()
    resp = await client.get("/api/v1/auth/sessions", headers=hdrs)
    assert not any(s["current"] for s in resp.json())

    # Revoking the other device leaves exactly one session
    other = sessions[1]["family_id"]
    assert (await client.delete(f"/api/v1/auth/sessions/{other}", headers=hdrs)).status_code == 200
    client.cookies.set("refresh_token", first_cookie)
    remaining = (await client.get("/api/v1/auth/sessions", headers=hdrs)).json()
    assert [s["family_id"] for s in remaining] == [sessions[0]["family_id"]]


@pytest.mark.asyncio
async def test_security_activity_lists_own_events_only(live_env):
    client, db, _ = live_env
    await seed_user(db, email="me@test.edu", roll_no="R1")
    await seed_user(db, email="other@test.edu", roll_no="R2")

    assert (await _login(client, "me@test.edu", password="wrong-password")).status_code == 401
    ok = await _login(client, "me@test.edu")
    hdrs = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    await _login(client, "other@test.edu")

    resp = await client.get("/api/v1/me/security-activity", headers=hdrs)
    assert resp.status_code == 200
    actions = [e["action"] for e in resp.json()]
    assert actions[:2] == ["LOGIN_SUCCESS", "LOGIN_FAILED"]
    assert len(actions) == 2  # the other user's login is not visible

    limited = await client.get("/api/v1/me/security-activity", params={"limit": 1}, headers=hdrs)
    assert len(limited.json()) == 1
