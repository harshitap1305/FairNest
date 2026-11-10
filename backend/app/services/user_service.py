"""User service: CSV student import and role grant management."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Optional

from bson import ObjectId

from app.core import clock as _clock
from app.core.config import get_settings
from app.core.constants import Role
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.core.security import generate_opaque_token, hash_token
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.repositories import users as user_repo


_VALID_GENDERS = {"M", "F", "OTHER", "MALE", "FEMALE"}
_VALID_ROLES = {r.value for r in Role}


def _norm_gender(g: str) -> str:
    g = g.strip().upper()
    if g in ("F", "FEMALE"):
        return "F"
    if g in ("M", "MALE"):
        return "M"
    return "OTHER"


async def import_students_csv(
    db,
    csv_content: str,
    hostel_id: Optional[str] = None,
) -> dict:
    """
    Parse CSV string (supports canonical schema `roll_no,name,email,gender,year,program,hostel_code`
    and legacy column aliases `student_id`, `full_name`) and upsert students as INVITED.
    """
    created = 0
    updated = 0
    errors: list[str] = []
    settings = get_settings()
    now = _clock.now()

    try:
        reader = csv.DictReader(io.StringIO(csv_content.lstrip("\ufeff").strip()))
    except Exception as exc:
        return {"created": 0, "updated": 0, "errors": [f"CSV parse error: {exc}"]}

    if not reader.fieldnames:
        return {"created": 0, "updated": 0, "errors": ["CSV has no header row"]}

    tokens_issued: list[dict] = []

    for row_no, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items() if k}
        email = row.get("email", "").lower()
        name = row.get("name") or row.get("full_name", "")
        roll_no = row.get("roll_no") or row.get("student_id", "")
        gender = row.get("gender", "").upper()

        if not email or "@" not in email:
            errors.append(f"Row {row_no}: invalid or missing email")
            continue
        allowed_domains = settings.allowed_email_domains_list
        if allowed_domains and email.rsplit("@", 1)[-1] not in allowed_domains:
            errors.append(f"Row {row_no}: email domain not allowed for '{email}'")
            continue
        if not name:
            errors.append(f"Row {row_no}: missing name for '{email}'")
            continue
        if not roll_no:
            errors.append(f"Row {row_no}: missing roll_no for '{email}'")
            continue
        if gender not in _VALID_GENDERS:
            errors.append(f"Row {row_no}: invalid gender '{gender}' for '{email}'")
            continue

        # Resolve hostel codes -> hostel_ids
        hostel_ids: list[str] = []
        raw_codes = row.get("hostel_code") or row.get("hostel_preference") or ""
        if raw_codes:
            bad_code = False
            for code in [c.strip().upper() for c in raw_codes.split("|") if c.strip()]:
                h = await cat_repo.get_hostel_by_code(db, code)
                if not h:
                    errors.append(f"Row {row_no}: unknown hostel code '{code}'")
                    bad_code = True
                    break
                hostel_ids.append(str(h["_id"]))
            if bad_code:
                continue
        elif hostel_id:
            hostel_ids = [hostel_id]

        year_raw = row.get("year")
        try:
            year_val = int(year_raw) if year_raw else 1
        except ValueError:
            year_val = 1

        existing = await user_repo.find_user_by_email(db, email)
        if existing:
            upd = {
                "name": name,
                "roll_no": roll_no,
                "gender": _norm_gender(gender),
                "year": year_val,
                "program": row.get("program", existing.get("program", "")),
            }
            if hostel_ids:
                upd["hostel_ids"] = hostel_ids
            await user_repo.update_user(db, str(existing["_id"]), upd)
            updated += 1
        else:
            activation_token = generate_opaque_token()
            uid = await user_repo.create_user(db, {
                "roll_no": roll_no,
                "email": email,
                "name": name,
                "password_hash": "",
                "role": "STUDENT",
                "hostel_ids": hostel_ids,
                "managed_hostel_ids": [],
                "status": "INVITED",
                "gender": _norm_gender(gender),
                "year": year_val,
                "program": row.get("program", ""),
                "accessibility_verified": False,
                "failed_logins": 0,
                "locked_until": None,
                "token_version": 0,
                "activation_token_hash": hash_token(activation_token),
                "activation_expires_at": now + timedelta(hours=72),
            })
            await repo.create_credit_account(db, uid, settings.C_INIT)
            tokens_issued.append({"user_id": uid, "roll_no": roll_no, "token": activation_token})
            created += 1

    return {
        "created": created,
        "updated": updated,
        "errors": errors,
        "activation_tokens": tokens_issued[:20],
    }


async def grant_role_by_email(
    db,
    *,
    email: str,
    role: str,
    hostel_ids: list[str],
    actor: dict,
) -> dict:
    """
    Grant a role by email enforcing hierarchy, hostel existence, and non-self-grant:
    - SUPER_ADMIN can grant ADMIN, WARDEN, AUDITOR, SUPER_ADMIN, STUDENT
    - ADMIN can ONLY grant WARDEN scoped to their own managed_hostel_ids
    - Scoped roles (ADMIN, WARDEN) require valid non-empty hostel_ids
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValidationError("Valid email is required")
    allowed_domains = get_settings().allowed_email_domains_list
    if allowed_domains and email.rsplit("@", 1)[-1] not in allowed_domains:
        raise ValidationError(f"Email domain must be one of: {', '.join(allowed_domains)}")
    if role not in _VALID_ROLES:
        raise ValidationError(f"Invalid role: {role}")
    if email == actor.get("email", "").lower():
        raise ForbiddenError("Cannot grant a role to yourself")

    actor_role = actor.get("role")
    if actor_role == "ADMIN":
        if role != "WARDEN":
            raise ForbiddenError("ADMIN can only grant WARDEN role")
        managed = set(actor.get("managed_hostel_ids", []))
        if not hostel_ids or not set(hostel_ids).issubset(managed):
            raise ForbiddenError(
                "ADMIN can only grant WARDEN within their managed hostels",
                code="HOSTEL_SCOPE_DENIED",
            )
    elif actor_role != "SUPER_ADMIN":
        raise ForbiddenError("Insufficient privileges to grant roles")

    if role in ("WARDEN", "ADMIN"):
        if not hostel_ids:
            raise ValidationError(f"hostel_ids must be non-empty for role {role}")
        for hid in hostel_ids:
            h = await cat_repo.get_hostel(db, hid)
            if not h:
                raise NotFoundError(f"Hostel {hid} not found")

    now = _clock.now()
    existing_user = await user_repo.find_user_by_email(db, email)

    # Ensure no duplicate active grant of same role
    active_same = await db["role_grants"].find_one(
        {"email": email, "role": role, "status": {"$in": ["PENDING", "ACTIVE"]}}
    )
    if active_same:
        # Update hostel scope on existing grant cleanly
        await db["role_grants"].update_one(
            {"_id": active_same["_id"]},
            {"$set": {"hostel_ids": hostel_ids, "granted_by": str(actor["_id"]), "granted_at": now}},
        )
        grant_id = str(active_same["_id"])
    else:
        grant_id = await user_repo.create_role_grant(db, {
            "email": email,
            "role": role,
            "hostel_ids": hostel_ids,
            "status": "ACTIVE" if existing_user else "PENDING",
            "granted_by": str(actor["_id"]),
            "granted_at": now,
            "applied_user_id": str(existing_user["_id"]) if existing_user else None,
            "applied_at": now if existing_user else None,
        })

    if existing_user:
        await user_repo.update_user(db, str(existing_user["_id"]), {
            "role": role,
            "managed_hostel_ids": hostel_ids,
        })
        await user_repo.bump_token_version(db, str(existing_user["_id"]))
        status_out = "ACTIVE"
        msg = "Role granted and applied immediately"
    else:
        status_out = "PENDING"
        msg = "Grant recorded (PENDING) — applies automatically upon activation"

    await repo.create_audit_log(db, {
        "actor_id": str(actor["_id"]),
        "role": actor_role or "",
        "action": "GRANT_ROLE",
        "target_type": "role_grant",
        "target_id": grant_id,
        "before": None,
        "after": {"email": email, "role": role, "hostel_ids": hostel_ids, "status": status_out},
        "request_id": "",
        "ip": "",
    })

    doc = await db["role_grants"].find_one({"_id": ObjectId(grant_id)})
    return {**(doc or {}), "_id": grant_id, "id": grant_id, "status": status_out, "message": msg}
