"""User, floor, room, credit, group, application, allotment, audit, notification models."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from app.models.base import BaseDocument
from app.core.constants import (
    Role, UserStatus, RoomStatus, CycleStatus, InventoryStatus,
    AllotmentStatus, ApplicationStatus, GroupStatus, MembershipStatus,
    ChoiceKind, Fallback, RoleGrantStatus,
)
from pydantic import Field


# ── User ──────────────────────────────────────────────────────────────────────

class UserDoc(BaseDocument):
    roll_no: Optional[str] = None
    email: str
    name: str
    password_hash: str
    role: Role = Role.STUDENT
    hostel_ids: list[str] = Field(default_factory=list)
    managed_hostel_ids: list[str] = Field(default_factory=list)
    status: UserStatus = UserStatus.INVITED
    gender: str = ""
    year: Optional[int] = None
    program: Optional[str] = None
    accessibility_verified: bool = False
    failed_logins: int = 0
    locked_until: Optional[datetime] = None
    token_version: int = 0
    activation_token_hash: Optional[str] = None
    activation_expires_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


# ── Hostel / Floor / Room ──────────────────────────────────────────────────────

class HostelDoc(BaseDocument):
    name: str
    code: str
    allowed_gender: str = "ANY"   # "M" | "F" | "ANY"
    allowed_years: list[int] = Field(default_factory=list)
    active: bool = True


class FloorDoc(BaseDocument):
    hostel_id: str
    floor_no: int
    label: str = ""
    active: bool = True


class RoomDoc(BaseDocument):
    hostel_id: str
    floor_id: str
    floor_no: int
    room_no: str
    capacity: int
    features: list[str] = Field(default_factory=list)
    status: RoomStatus = RoomStatus.ACTIVE


# ── Cycle ─────────────────────────────────────────────────────────────────────

DEFAULT_POLICY: dict = {
    "c_init": 3, "c_min": 0, "c_max": 10,
    "weight_formula": "1 + credits",
    "group_weight_policy": "MEAN",
    "fill_rule": "EXACT",
    "rank_deltas": {"1": -3, "2": -2, "3": -1, "4": 0, "5": 0, "default": 1},
    "unallotted_delta": 2,
    "forfeit_delta": -2,
    "late_cancel_delta": -1,
    "carry_over_factor": 0.5,
}


class CycleDoc(BaseDocument):
    name: str
    academic_year: str
    hostel_id: str
    status: CycleStatus = CycleStatus.DRAFT
    apply_open_at: Optional[datetime] = None
    apply_close_at: Optional[datetime] = None
    schedule_history: list[dict] = Field(default_factory=list)
    final_deadline_at: Optional[datetime] = None
    freeze_hours: int = 48
    policy: dict = Field(default_factory=lambda: dict(DEFAULT_POLICY))
    seed_commitment: Optional[str] = None
    seed_secret: Optional[str] = None
    seed_revealed_at: Optional[datetime] = None
    created_by: str = ""


# ── Room Inventory ─────────────────────────────────────────────────────────────

class RoomInventoryDoc(BaseDocument):
    cycle_id: str
    room_id: str
    hostel_id: str
    floor_no: int
    capacity: int
    status: InventoryStatus = InventoryStatus.AVAILABLE
    allotment_id: Optional[str] = None
    is_live: bool = True
    version: int = 0


# ── Group / Membership ────────────────────────────────────────────────────────

class GroupDoc(BaseDocument):
    cycle_id: str
    leader_id: str
    name: str
    status: GroupStatus = GroupStatus.FORMING
    size: int = 1
    gender: str = ""


class MembershipDoc(BaseDocument):
    cycle_id: str
    group_id: str
    user_id: str
    role: str = "MEMBER"   # "LEADER" | "MEMBER"
    status: MembershipStatus = MembershipStatus.INVITED
    invited_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None


# ── Application ───────────────────────────────────────────────────────────────

class RankedChoice(BaseDocument):
    kind: ChoiceKind
    room_id: Optional[str] = None
    hostel_id: Optional[str] = None
    floor_no: Optional[int] = None
    rank: int

    class Config:
        populate_by_name = True


class CreditSnapshot(BaseDocument):
    members: list[dict] = Field(default_factory=list)
    group_policy: str = "MEAN"
    weight: float = 1.0

    class Config:
        populate_by_name = True


class ApplicationDoc(BaseDocument):
    cycle_id: str
    group_id: str
    member_ids: list[str] = Field(default_factory=list)
    group_size: int = 1
    ranked_choices: list[dict] = Field(default_factory=list)
    fallback: Fallback = Fallback.NONE
    tier: int = 1
    status: ApplicationStatus = ApplicationStatus.SUBMITTED
    credit_snapshot: Optional[dict] = None
    weight: Optional[float] = None
    order_key: Optional[float] = None
    order_index: Optional[int] = None
    submitted_at: Optional[datetime] = None
    version: int = 0


# ── Allotment ────────────────────────────────────────────────────────────────
# NO payment fields — just accept_status per member.

class AllotmentMember(BaseDocument):
    user_id: str
    accept_status: str = "PENDING"   # "PENDING" | "ACCEPTED" | "DECLINED"
    accepted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class AllotmentDoc(BaseDocument):
    cycle_id: str
    application_id: str
    group_id: str
    room_id: str
    group_size: int
    rank_obtained: int
    round_no: int = 1
    status: AllotmentStatus = AllotmentStatus.HELD
    is_active: bool = True
    held_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    grace_used: bool = False
    confirmed_at: Optional[datetime] = None
    release_reason: Optional[str] = None
    members: list[dict] = Field(default_factory=list)
    run_id: Optional[str] = None


# ── Credit ────────────────────────────────────────────────────────────────────

class CreditAccountDoc(BaseDocument):
    user_id: str
    credits: int = 3
    version: int = 0


class CreditLedgerDoc(BaseDocument):
    user_id: str
    cycle_id: str
    event_type: str
    delta: int
    credits_before: int
    credits_after: int
    ref_id: Optional[str] = None
    reason: str = ""


# ── Audit / Notification ──────────────────────────────────────────────────────

class AuditLogDoc(BaseDocument):
    actor_id: str
    role: str
    action: str
    target_type: str
    target_id: str
    before: Optional[dict] = None
    after: Optional[dict] = None
    request_id: str = ""
    ip: str = ""
    ts: Optional[datetime] = None


class NotificationDoc(BaseDocument):
    user_id: str
    type: str
    title: str
    body: str
    read: bool = False


class OutboxDoc(BaseDocument):
    channel: str
    to: str
    payload: dict = Field(default_factory=dict)
    status: str = "PENDING"
    attempts: int = 0
    next_attempt_at: Optional[datetime] = None


# ── Role Grant ────────────────────────────────────────────────────────────────

class RoleGrantDoc(BaseDocument):
    email: str
    role: str
    hostel_ids: list[str] = Field(default_factory=list)
    status: RoleGrantStatus = RoleGrantStatus.PENDING
    granted_by: str
    granted_at: Optional[datetime] = None
    applied_user_id: Optional[str] = None
    applied_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revoked_at: Optional[datetime] = None


# ── Allocation Run ────────────────────────────────────────────────────────────

class AllocationRunDoc(BaseDocument):
    cycle_id: str
    round_no: int = 1
    type: str = "MAIN"
    algorithm_version: str = "rsd-weighted-1.0"
    params: dict = Field(default_factory=dict)
    seed_commitment: Optional[str] = None
    seed_revealed: Optional[str] = None
    input_hash: str = ""
    output_hash: str = ""
    stats: dict = Field(default_factory=dict)
    status: str = "COMPLETED"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    triggered_by: str = ""
