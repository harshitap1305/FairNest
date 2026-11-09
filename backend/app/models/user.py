"""User document model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core.constants import Role, UserStatus
from app.models.base import BaseDocument, PyObjectId


class UserDoc(BaseDocument):
    id: PyObjectId = ""  # type: ignore[assignment]
    roll_no: Optional[str] = None
    email: str  # always lowercase
    name: str
    password_hash: Optional[str] = None
    role: Role = Role.STUDENT
    hostel_ids: list[str] = []
    managed_hostel_ids: list[str] = []
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
