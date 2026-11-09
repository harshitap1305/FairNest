"""Application-wide enumerations."""

from enum import Enum


class Role(str, Enum):
    STUDENT = "STUDENT"
    WARDEN = "WARDEN"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"
    AUDITOR = "AUDITOR"


class UserStatus(str, Enum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"


class CycleStatus(str, Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    APPLICATIONS_OPEN = "APPLICATIONS_OPEN"
    APPLICATIONS_CLOSED = "APPLICATIONS_CLOSED"
    ALLOCATING = "ALLOCATING"
    ALLOTMENT_ACTIVE = "ALLOTMENT_ACTIVE"
    CLOSED = "CLOSED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class RoomStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"


class InventoryStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    BLOCKED = "BLOCKED"


class AllotmentStatus(str, Enum):
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    DECLINED = "DECLINED"
    REVOKED = "REVOKED"
    CANCELLED = "CANCELLED"


class ApplicationStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    ALLOTTED = "ALLOTTED"
    WAITLISTED = "WAITLISTED"
    CONFIRMED = "CONFIRMED"
    FORFEITED = "FORFEITED"
    WITHDRAWN = "WITHDRAWN"
    UNALLOTTED = "UNALLOTTED"


class GroupStatus(str, Enum):
    FORMING = "FORMING"
    READY = "READY"
    SUBMITTED = "SUBMITTED"
    LOCKED = "LOCKED"
    WITHDRAWN = "WITHDRAWN"
    DISBANDED = "DISBANDED"


class MembershipStatus(str, Enum):
    INVITED = "INVITED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    LEFT = "LEFT"
    REMOVED = "REMOVED"


class FillRule(str, Enum):
    EXACT = "EXACT"
    AT_MOST = "AT_MOST"


class GroupWeightPolicy(str, Enum):
    MEAN = "MEAN"
    MIN = "MIN"
    MAX = "MAX"


class ChoiceKind(str, Enum):
    ROOM = "ROOM"
    FLOOR = "FLOOR"


class Fallback(str, Enum):
    ANY_ELIGIBLE = "ANY_ELIGIBLE"
    NONE = "NONE"


class RoleGrantStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
