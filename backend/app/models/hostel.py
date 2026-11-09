"""Hostel, Floor, and Room document models."""

from __future__ import annotations

from app.core.constants import RoomStatus
from app.models.base import BaseDocument, PyObjectId


class HostelDoc(BaseDocument):
    id: PyObjectId = ""  # type: ignore[assignment]
    name: str
    code: str  # unique short code e.g. "BH1"
    allowed_gender: str = "ANY"  # "M" | "F" | "ANY"
    allowed_years: list[int] = []
    active: bool = True


class FloorDoc(BaseDocument):
    id: PyObjectId = ""  # type: ignore[assignment]
    hostel_id: str
    floor_no: int
    label: str
    active: bool = True


class RoomDoc(BaseDocument):
    id: PyObjectId = ""  # type: ignore[assignment]
    hostel_id: str
    floor_id: str
    floor_no: int
    room_no: str  # e.g. "101", "A-204"
    capacity: int  # 1-4
    features: list[str] = []
    status: RoomStatus = RoomStatus.ACTIVE
