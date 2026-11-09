"""Room inventory document model."""

from __future__ import annotations

from typing import Optional

from app.core.constants import InventoryStatus
from app.models.base import BaseDocument, PyObjectId


class RoomInventoryDoc(BaseDocument):
    id: PyObjectId = ""  # type: ignore[assignment]
    cycle_id: str
    room_id: str
    hostel_id: str
    floor_no: int
    capacity: int
    status: InventoryStatus = InventoryStatus.AVAILABLE
    allotment_id: Optional[str] = None
    is_live: bool = True
    version: int = 0
