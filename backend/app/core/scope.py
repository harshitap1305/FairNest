"""Hostel scope guards for multi-hostel access control."""

from __future__ import annotations

from app.core import clock as _clock
from app.core.errors import ForbiddenError, NotFoundError


def assert_student_scope(user_doc: dict, hostel_id: str) -> None:
    """
    Raise NotFoundError if the student does not belong to hostel_id.
    Uses NotFoundError (not 403) to avoid leaking hostel existence.
    """
    hostel_ids = user_doc.get("hostel_ids", [])
    if hostel_id not in hostel_ids:
        raise NotFoundError("Resource not found")


async def assert_student_eligible_for_hostel(db, user_doc: dict, hostel_id: str) -> dict:
    """
    Two-layer student check (R-ELIG & R-SCOPE):
    1. Student must have hostel_id in user_doc['hostel_ids']
    2. Hostel must exist, be active, and match student's gender/year rules.
    Raises NotFoundError (404) on mismatch so hidden hostels are not leaked.
    """
    from app.repositories import catalogue as cat_repo

    assert_student_scope(user_doc, hostel_id)
    hostel = await cat_repo.get_hostel(db, hostel_id)
    if not hostel or not hostel.get("active", True):
        raise NotFoundError("Resource not found")

    allowed_gender = hostel.get("allowed_gender", "ANY")
    if allowed_gender and allowed_gender != "ANY":
        if user_doc.get("gender") != allowed_gender:
            raise NotFoundError("Resource not found")

    allowed_years = hostel.get("allowed_years") or []
    if allowed_years:
        if user_doc.get("year") not in allowed_years:
            raise NotFoundError("Resource not found")

    return hostel


def assert_staff_scope(user_doc: dict, hostel_id: str) -> None:
    """
    Raise ForbiddenError(HOSTEL_SCOPE_DENIED) if the staff user is not authorised
    for hostel_id. SUPER_ADMIN (and global AUDITOR without managed_hostel_ids) is permitted.
    """
    role = user_doc.get("role", "")
    if role == "SUPER_ADMIN":
        return
    managed = user_doc.get("managed_hostel_ids", [])
    if role == "AUDITOR" and not managed:
        return
    if hostel_id not in managed:
        raise ForbiddenError(
            f"You do not have access to hostel {hostel_id}",
            code="HOSTEL_SCOPE_DENIED",
        )


def assert_user_hostel_scope(user_doc: dict, hostel_id: str) -> None:
    """Dispatch scope check for student (404) vs staff (403)."""
    if user_doc.get("role") == "STUDENT":
        assert_student_scope(user_doc, hostel_id)
    else:
        assert_staff_scope(user_doc, hostel_id)


def filter_hostel_ids_for_user(user_doc: dict) -> list[str] | None:
    """
    Return the hostel IDs the user may see, or None for global unrestricted access:
    - SUPER_ADMIN: None (all hostels)
    - AUDITOR with empty managed_hostel_ids: None (all hostels)
    - Students: their hostel_ids list
    - Staff (WARDEN, ADMIN, scoped AUDITOR): their managed_hostel_ids
    """
    role = user_doc.get("role", "")
    if role == "SUPER_ADMIN":
        return None
    if role == "AUDITOR" and not user_doc.get("managed_hostel_ids"):
        return None
    if role == "STUDENT":
        return user_doc.get("hostel_ids", [])
    return user_doc.get("managed_hostel_ids", [])


async def audit_scope_violation(
    db,
    *,
    actor_id: str,
    role: str,
    action: str,
    target_type: str,
    target_id: str,
    hostel_id: str,
    request_id: str = "",
    ip: str = "",
) -> None:
    """Persist an audit log record whenever a staff/user crosses a hostel scope boundary."""
    from app.repositories import core_repos as repo

    await repo.create_audit_log(db, {
        "actor_id": actor_id,
        "role": role,
        "action": f"SCOPE_DENIED:{action}",
        "target_type": target_type,
        "target_id": target_id,
        "before": None,
        "after": {"hostel_id": hostel_id},
        "request_id": request_id,
        "ip": ip,
        "ts": _clock.now(),
    })
