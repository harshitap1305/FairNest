"""Allocation cycle document model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core.constants import CycleStatus
from app.fairness.engine import DEFAULT_POLICY
from app.models.base import BaseDocument, PyObjectId


class CycleDoc(BaseDocument):
    id: PyObjectId = ""  # type: ignore[assignment]
    name: str
    academic_year: str  # e.g. "2024-25"
    hostel_id: str
    status: CycleStatus = CycleStatus.DRAFT
    apply_open_at: Optional[datetime] = None
    apply_close_at: Optional[datetime] = None
    schedule_history: list[dict] = []
    final_deadline_at: Optional[datetime] = None
    freeze_hours: int = 48
    policy: dict = {}
    seed_commitment: Optional[str] = None  # sha256(seed_secret)
    seed_secret: Optional[str] = None      # revealed after allocation
    seed_revealed_at: Optional[datetime] = None
    created_by: str = ""

    def effective_policy(self) -> dict:
        return {**DEFAULT_POLICY, **self.policy}
