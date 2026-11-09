"""Pytest fixtures for FairNest unit, integration, concurrency, and security tests."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from bson import ObjectId

# Ensure `app` package is importable when running from repo root or `backend/`
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ── Pure / Unit Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def fake_now():
    return datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_student_id():
    return ObjectId()


@pytest.fixture
def sample_cycle_id():
    return ObjectId()


@pytest.fixture
def sample_room_id():
    return ObjectId()


@pytest.fixture
def sample_group_id():
    return ObjectId()


@pytest.fixture
def mock_db():
    """Lightweight mock database for pure unit helpers."""
    db = MagicMock()
    for coll in [
        "users", "cycles", "rooms", "groups", "allotments", "applications",
        "credit_accounts", "credit_ledger", "notifications", "audit_logs",
        "idempotency_keys", "allocation_runs", "memberships", "refresh_tokens",
        "hostels", "floors", "room_inventory", "role_grants", "outbox",
    ]:
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=None)
        col.insert_one = AsyncMock()
        col.update_one = AsyncMock()
        col.delete_one = AsyncMock()
        setattr(db, coll, col)
    return db


@pytest.fixture
def sample_allotment(sample_group_id, sample_room_id, sample_cycle_id, sample_student_id):
    return {
        "_id": ObjectId(),
        "cycle_id": str(sample_cycle_id),
        "group_id": str(sample_group_id),
        "room_id": str(sample_room_id),
        "status": "HELD",
        "is_active": True,
        "order_index": 0,
        "members": [
            {
                "user_id": str(sample_student_id),
                "accept_status": "PENDING",
                "accepted_at": None,
            }
        ],
        "expires_at": datetime(2025, 6, 2, 12, 0, 0, tzinfo=timezone.utc),
        "grace_used": False,
        "created_at": datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    }


# ── Real MongoDB rs0 + FastAPI AsyncClient Fixtures ──────────────────────────

@pytest_asyncio.fixture
async def live_env():
    """
    Spin up an isolated temporary MongoDB database on the replica set + an HTTPX ASGITransport
    client wired directly to `create_app()`. Drops the temp database cleanly on teardown.
    """
    from httpx import ASGITransport, AsyncClient

    from app.core import clock as _clock
    from app.core.config import get_settings
    from app.core.rate_limit import identifier_limiter, login_limiter, sensitive_limiter
    from app.db.client import close_db, connect_db, get_client, get_db
    from app.db.indexes import create_indexes
    from app.db.validators import create_validators
    from app.main import create_app

    settings = get_settings()
    orig_db = settings.MONGO_DB
    test_db_name = f"fairnest_t_{uuid.uuid4().hex[:10]}"
    settings.MONGO_DB = test_db_name

    # Reset rate limiters & clock before each test
    login_limiter._buckets.clear()
    identifier_limiter._buckets.clear()
    sensitive_limiter._buckets.clear()
    _clock.set_now(None)

    await connect_db(settings.MONGO_URI)
    raw_client = get_client()
    db = get_db(test_db_name)
    await create_indexes(db)
    await create_validators(db)

    application = create_app()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield client, db, raw_client
        finally:
            _clock.set_now(None)
            try:
                await raw_client.drop_database(test_db_name)
            finally:
                settings.MONGO_DB = orig_db
                await close_db()


async def seed_user(
    db,
    *,
    email: str,
    password: str = "StrongPass123!",
    role: str = "STUDENT",
    name: str = "Test User",
    roll_no: str | None = None,
    gender: str = "M",
    year: int = 1,
    hostel_ids: list[str] | None = None,
    managed_hostel_ids: list[str] | None = None,
    accessibility_verified: bool = False,
    credits: int = 3,
) -> dict:
    """Insert an ACTIVE user + credit_account directly into the test DB."""
    from app.core.security import hash_password
    from app.repositories import core_repos as repo
    from app.repositories import users as user_repo

    doc = {
        "email": email.lower(),
        "name": name,
        "password_hash": hash_password(password),
        "role": role,
        "status": "ACTIVE",
        "gender": gender,
        "year": year,
        "program": "BTech",
        "hostel_ids": hostel_ids or [],
        "managed_hostel_ids": managed_hostel_ids or [],
        "accessibility_verified": accessibility_verified,
        "failed_logins": 0,
        "locked_until": None,
        "token_version": 0,
    }
    if roll_no is not None:
        doc["roll_no"] = roll_no
    uid = await user_repo.create_user(db, doc)
    if role == "STUDENT":
        await repo.create_credit_account(db, uid, credits)
    user = await user_repo.find_user_by_id(db, uid)
    return user


async def auth_headers(client, identifier: str, password: str = "StrongPass123!") -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {identifier}: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
