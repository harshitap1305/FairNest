"""Create all MongoDB indexes for FairNest."""

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, IndexModel


async def create_indexes(db) -> None:
    """Create all required indexes. Safe to call multiple times (idempotent)."""

    # ── users ─────────────────────────────────────────────────────────────────
    await db["users"].create_indexes([
        IndexModel([("email", ASCENDING)], unique=True, name="users_email_unique"),
        IndexModel(
            [("roll_no", ASCENDING)],
            unique=True,
            partialFilterExpression={"roll_no": {"$type": "string"}},
            name="users_roll_no_unique",
        ),
        IndexModel([("role", ASCENDING)], name="users_role"),
        IndexModel([("hostel_ids", ASCENDING)], name="users_hostel_ids"),
        IndexModel([("status", ASCENDING)], name="users_status"),
        IndexModel(
            [("activation_token_hash", ASCENDING)],
            sparse=True,
            name="users_activation_token_hash",
        ),
    ])

    # ── refresh_tokens ────────────────────────────────────────────────────────
    await db["refresh_tokens"].create_indexes([
        IndexModel([("token_hash", ASCENDING)], unique=True, name="rt_token_hash_unique"),
        IndexModel([("family_id", ASCENDING)], name="rt_family_id"),
        IndexModel([("user_id", ASCENDING)], name="rt_user_id"),
        IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="rt_ttl"),
    ])

    # ── role_grants ───────────────────────────────────────────────────────────
    await db["role_grants"].create_indexes([
        IndexModel(
            [("email", ASCENDING), ("role", ASCENDING)],
            unique=True,
            partialFilterExpression={"status": {"$in": ["PENDING", "ACTIVE"]}},
            name="role_grants_active_unique",
        ),
        IndexModel([("email", ASCENDING)], name="role_grants_email"),
        IndexModel([("status", ASCENDING)], name="role_grants_status"),
    ])

    # ── credit_accounts ───────────────────────────────────────────────────────
    await db["credit_accounts"].create_indexes([
        IndexModel([("user_id", ASCENDING)], unique=True, name="credit_accounts_user_id"),
    ])

    # ── credit_ledger ─────────────────────────────────────────────────────────
    await db["credit_ledger"].create_indexes([
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="cl_user_created"),
        IndexModel(
            [("cycle_id", ASCENDING), ("user_id", ASCENDING), ("event_type", ASCENDING)],
            unique=True,
            partialFilterExpression={
                "event_type": {"$in": [
                    "SETTLEMENT_CONFIRMED", "SETTLEMENT_UNALLOTTED",
                    "SETTLEMENT_FORFEITED", "SETTLEMENT_LATE_CANCELLED",
                    "SETTLEMENT_REVOKED",
                ]}
            },
            name="cl_settlement_unique",
        ),
    ])

    # ── hostels ───────────────────────────────────────────────────────────────
    await db["hostels"].create_indexes([
        IndexModel([("code", ASCENDING)], unique=True, name="hostels_code_unique"),
        IndexModel([("active", ASCENDING)], name="hostels_active"),
    ])

    # ── floors ────────────────────────────────────────────────────────────────
    await db["floors"].create_indexes([
        IndexModel(
            [("hostel_id", ASCENDING), ("floor_no", ASCENDING)],
            unique=True,
            name="floors_hostel_floor_unique",
        ),
    ])

    # ── rooms ─────────────────────────────────────────────────────────────────
    await db["rooms"].create_indexes([
        IndexModel(
            [("hostel_id", ASCENDING), ("room_no", ASCENDING)],
            unique=True,
            name="rooms_hostel_room_no_unique",
        ),
        IndexModel(
            [("hostel_id", ASCENDING), ("floor_no", ASCENDING)],
            name="rooms_hostel_floor",
        ),
        IndexModel([("status", ASCENDING)], name="rooms_status"),
    ])

    # ── cycles ────────────────────────────────────────────────────────────────
    await db["cycles"].create_indexes([
        IndexModel([("status", ASCENDING)], name="cycles_status"),
        IndexModel([("hostel_id", ASCENDING), ("status", ASCENDING)], name="cycles_hostel_status"),
        IndexModel(
            [("status", ASCENDING), ("apply_open_at", ASCENDING)],
            name="cycles_status_open_at",
        ),
        IndexModel(
            [("status", ASCENDING), ("apply_close_at", ASCENDING)],
            name="cycles_status_close_at",
        ),
    ])

    # ── room_inventory ────────────────────────────────────────────────────────
    await db["room_inventory"].create_indexes([
        IndexModel(
            [("cycle_id", ASCENDING), ("room_id", ASCENDING)],
            unique=True,
            name="inv_cycle_room_unique",
        ),
        IndexModel(
            [("room_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"is_live": True},
            name="inv_live_room_unique",
        ),
        IndexModel(
            [("cycle_id", ASCENDING), ("hostel_id", ASCENDING),
             ("floor_no", ASCENDING), ("status", ASCENDING)],
            name="inv_cycle_hostel_floor_status",
        ),
        IndexModel([("allotment_id", ASCENDING)], sparse=True, name="inv_allotment_id"),
    ])

    # ── groups ────────────────────────────────────────────────────────────────
    await db["groups"].create_indexes([
        IndexModel(
            [("cycle_id", ASCENDING), ("leader_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"status": {"$in": ["FORMING", "READY", "SUBMITTED", "LOCKED"]}},
            name="groups_cycle_leader_unique",
        ),
        IndexModel([("cycle_id", ASCENDING), ("status", ASCENDING)], name="groups_cycle_status"),
    ])

    # ── memberships ───────────────────────────────────────────────────────────
    await db["memberships"].create_indexes([
        IndexModel(
            [("cycle_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"status": "ACCEPTED"},
            name="memberships_active_unique",
        ),
        IndexModel([("group_id", ASCENDING)], name="memberships_group_id"),
        IndexModel([("cycle_id", ASCENDING), ("user_id", ASCENDING)], name="memberships_cycle_user"),
        IndexModel([("status", ASCENDING)], name="memberships_status"),
    ])

    # ── applications ──────────────────────────────────────────────────────────
    await db["applications"].create_indexes([
        IndexModel(
            [("cycle_id", ASCENDING), ("group_id", ASCENDING)],
            unique=True,
            name="applications_cycle_group_unique",
        ),
        IndexModel(
            [("cycle_id", ASCENDING), ("status", ASCENDING), ("order_index", ASCENDING)],
            name="applications_cycle_status_order",
        ),
        IndexModel([("status", ASCENDING)], name="applications_status"),
    ])

    # ── allotments ────────────────────────────────────────────────────────────
    await db["allotments"].create_indexes([
        IndexModel(
            [("cycle_id", ASCENDING), ("application_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"is_active": True},
            name="allotments_active_app_unique",
        ),
        IndexModel(
            [("cycle_id", ASCENDING), ("room_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"is_active": True},
            name="allotments_active_room_unique",
        ),
        IndexModel(
            [("status", ASCENDING), ("expires_at", ASCENDING)],
            name="allotments_status_expires",
        ),
        IndexModel([("cycle_id", ASCENDING), ("status", ASCENDING)], name="allotments_cycle_status"),
    ])

    # ── notifications ─────────────────────────────────────────────────────────
    await db["notifications"].create_indexes([
        IndexModel(
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="notifications_user_created",
        ),
        IndexModel(
            [("created_at", ASCENDING)],
            expireAfterSeconds=90 * 24 * 3600,
            name="notifications_ttl",
        ),
        IndexModel([("user_id", ASCENDING), ("read", ASCENDING)], name="notifications_user_read"),
    ])

    # ── outbox ────────────────────────────────────────────────────────────────
    await db["outbox"].create_indexes([
        IndexModel(
            [("status", ASCENDING), ("next_attempt_at", ASCENDING)],
            name="outbox_status_next_attempt",
        ),
    ])

    # ── audit_logs ────────────────────────────────────────────────────────────
    await db["audit_logs"].create_indexes([
        IndexModel([("ts", DESCENDING)], name="audit_ts"),
        IndexModel([("actor_id", ASCENDING), ("ts", DESCENDING)], name="audit_actor_ts"),
        IndexModel(
            [("target_type", ASCENDING), ("target_id", ASCENDING)],
            name="audit_target",
        ),
    ])

    # ── idempotency_keys ──────────────────────────────────────────────────────
    await db["idempotency_keys"].create_indexes([
        IndexModel(
            [("user_id", ASCENDING), ("key", ASCENDING)],
            unique=True,
            name="idempotency_user_key_unique",
        ),
        IndexModel(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="idempotency_ttl",
        ),
    ])

    # ── job_locks ─────────────────────────────────────────────────────────────
    await db["job_locks"].create_indexes([
        IndexModel([("job_name", ASCENDING)], unique=True, name="job_locks_name_unique"),
        IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="job_locks_ttl"),
    ])
