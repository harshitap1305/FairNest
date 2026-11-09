"""Group and Membership document models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core.constants import GroupStatus, MembershipStatus
from app.models.base import BaseDocument, PyObjectId


class GroupDoc(BaseDocument):
    id: PyObjectId = ""  # type: ignore[assignment]
    cycle_id: str
    leader_id: str
    name: str
    status: GroupStatus = GroupStatus.FORMING
    size: int = 1
    gender: str = ""


class MembershipDoc(BaseDocument):
    id: PyObjectId = ""  # type: ignore[assignment]
    cycle_id: str
    group_id: str
    user_id: str
    role: str = "MEMBER"  # "LEADER" | "MEMBER"
    status: MembershipStatus = MembershipStatus.INVITED
    invited_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
