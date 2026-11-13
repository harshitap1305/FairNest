"""Auth service: activation, login, refresh, logout, password reset."""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.core import clock as _clock
from app.core.config import get_settings
from app.core.errors import UnauthorizedError, ValidationError
from app.core.security import (
    hash_password, verify_password, create_access_token,
    hash_token, generate_opaque_token,
)
from app.repositories import core_repos as repo
from app.repositories import users as user_repo


_COMMON_PASSWORDS = {"password", "password123", "12345678901", "hostel123", "1234567890"}


def _validate_password(password: str, identifier: str = "") -> None:
    if len(password) < 10:
        raise ValidationError("Password must be at least 10 characters")
    if identifier and password.lower() == identifier.lower():
        raise ValidationError("Password must not equal your roll number or email")
    if password.lower() in _COMMON_PASSWORDS:
        raise ValidationError("Password is too common")


async def _audit(db, actor_id: str, role: str, action: str, target_id: str,
                 after: dict | None = None, ip: str = "") -> None:
    try:
        await repo.create_audit_log(db, {
            "actor_id": actor_id,
            "role": role,
            "action": action,
            "target_type": "user",
            "target_id": target_id,
            "before": None,
            "after": after or {},
            "request_id": "",
            "ip": ip,
        })
    except Exception:
        pass  # Never block auth response if audit write encounters transient issue in mocked tests


async def activate_account(db, token: str, password: str, ip: str = "") -> dict:
    """Activate an INVITED account with the one-time token."""
    token_hash = hash_token(token)
    user = await user_repo.find_user_by_activation_token(db, token_hash)
    if not user:
        raise UnauthorizedError("Invalid or expired activation token", code="TOKEN_INVALID")
    now = _clock.now()
    if user.get("activation_expires_at") and user["activation_expires_at"] < now:
        raise UnauthorizedError("Activation token has expired", code="TOKEN_EXPIRED")
    _validate_password(password, identifier=user.get("roll_no") or user.get("email", ""))
    await user_repo.update_user(db, str(user["_id"]), {
        "password_hash": hash_password(password),
        "status": "ACTIVE",
        "activation_token_hash": None,
        "activation_expires_at": None,
    })
    # Apply any pending role grants
    grant = await user_repo.find_pending_grant(db, user["email"])
    if grant:
        await user_repo.apply_grant(db, str(grant["_id"]), str(user["_id"]), now)
        await user_repo.update_user(db, str(user["_id"]), {
            "role": grant["role"],
            "managed_hostel_ids": grant.get("hostel_ids", []),
        })
    # Ensure credit account exists for student
    if not await repo.get_credit_account(db, str(user["_id"])):
        settings = get_settings()
        await repo.create_credit_account(db, str(user["_id"]), settings.C_INIT)
    await _audit(db, str(user["_id"]), user.get("role", "STUDENT"), "ACTIVATE_ACCOUNT", str(user["_id"]), ip=ip)
    return await user_repo.find_user_by_id(db, str(user["_id"]))


async def login(db, identifier: str, password: str, ip: str = "",
                user_agent: str = "") -> tuple[str, str]:
    """
    Authenticate and return (access_token, refresh_token_opaque).
    Uses generic error messages to prevent user enumeration.
    """
    generic_err = UnauthorizedError("Invalid credentials", code="INVALID_CREDENTIALS")
    user = await user_repo.find_user_by_identifier(db, identifier)
    if not user:
        await _audit(db, "anonymous", "UNKNOWN", "LOGIN_FAILED", identifier, {"reason": "unknown_user"}, ip=ip)
        raise generic_err
    now = _clock.now()
    if user.get("locked_until") and user["locked_until"] > now:
        raise UnauthorizedError("Account is temporarily locked", code="ACCOUNT_LOCKED")
    if user.get("status") == "DISABLED":
        raise generic_err
    if user.get("status") == "INVITED":
        raise UnauthorizedError("Account not yet activated", code="ACCOUNT_NOT_ACTIVATED")
    if not verify_password(password, user.get("password_hash", "")):
        new_count = await user_repo.increment_failed_logins(db, str(user["_id"]))
        if new_count >= 5:
            lock_until = now + timedelta(minutes=15)
            await user_repo.update_user(
                db, str(user["_id"]), {"locked_until": lock_until, "status": "LOCKED"}
            )
        await _audit(db, str(user["_id"]), user.get("role", ""), "LOGIN_FAILED", str(user["_id"]),
                     {"failed_logins": new_count}, ip=ip)
        raise generic_err

    await user_repo.reset_failed_logins(db, str(user["_id"]))
    await user_repo.update_user(
        db, str(user["_id"]), {"last_login_at": now, "status": "ACTIVE"}
    )
    settings = get_settings()
    access_token = create_access_token(
        str(user["_id"]), user["role"], user.get("token_version", 0)
    )
    refresh_opaque = generate_opaque_token()
    refresh_hash = hash_token(refresh_opaque)
    family_id = str(uuid.uuid4())
    expires_at = now + timedelta(days=settings.REFRESH_DAYS)
    await user_repo.create_refresh_token(
        db, str(user["_id"]), family_id, refresh_hash, expires_at, ip, user_agent
    )
    await _audit(db, str(user["_id"]), user["role"], "LOGIN_SUCCESS", str(user["_id"]), ip=ip)
    return access_token, refresh_opaque


async def refresh_token(db, cookie_token: str) -> tuple[str, str]:
    """Rotate refresh token. Returns (new_access_token, new_refresh_opaque)."""
    token_hash = hash_token(cookie_token)
    record = await user_repo.find_refresh_token(db, token_hash)
    if not record:
        raise UnauthorizedError("Invalid refresh token", code="TOKEN_INVALID")
    # Reuse detection: revokes the entire token family immediately
    if record.get("revoked"):
        await user_repo.revoke_token_family(db, record["family_id"])
        await _audit(db, record["user_id"], "", "TOKEN_REUSE_DETECTED", record["family_id"])
        raise UnauthorizedError("Refresh token reuse detected", code="TOKEN_REUSE")
    now = _clock.now()
    if record["expires_at"] < now:
        raise UnauthorizedError("Refresh token expired", code="TOKEN_EXPIRED")
    user = await user_repo.find_user_by_id(db, record["user_id"])
    if not user or user.get("status") in ("DISABLED", "INVITED", "LOCKED"):
        raise UnauthorizedError("Account not accessible", code="INVALID_CREDENTIALS")
    # Rotate refresh token
    new_opaque = generate_opaque_token()
    new_hash = hash_token(new_opaque)
    settings = get_settings()
    new_expires = now + timedelta(days=settings.REFRESH_DAYS)
    await user_repo.revoke_refresh_token(db, token_hash, replaced_by=new_hash)
    await user_repo.create_refresh_token(
        db, record["user_id"], record["family_id"],
        new_hash, new_expires, record.get("ip", ""), record.get("user_agent", "")
    )
    new_access = create_access_token(
        record["user_id"], user["role"], user.get("token_version", 0)
    )
    return new_access, new_opaque


async def logout(db, cookie_token: str) -> None:
    token_hash = hash_token(cookie_token)
    record = await user_repo.find_refresh_token(db, token_hash)
    if record:
        await user_repo.revoke_token_family(db, record["family_id"])
        await _audit(db, record["user_id"], "", "LOGOUT", record["family_id"])


async def logout_all(db, user_id: str) -> None:
    await user_repo.bump_token_version(db, user_id)
    await db["refresh_tokens"].update_many(
        {"user_id": user_id, "revoked": False},
        {"$set": {"revoked": True}},
    )
    await _audit(db, user_id, "", "LOGOUT_ALL", user_id)


async def list_sessions(db, user_id: str, current_refresh_token: str | None = None) -> list[dict]:
    """Active refresh-token families of a user, newest first.

    When the caller's own refresh cookie is supplied, the matching session is flagged
    ``current`` so the UI can label "this device" and avoid revoking it by mistake.
    """
    current_family = None
    if current_refresh_token:
        record = await user_repo.find_refresh_token(db, hash_token(current_refresh_token))
        if record and record.get("user_id") == user_id:
            current_family = record.get("family_id")
    sessions = await user_repo.list_active_sessions(db, user_id)
    out = [
        {
            "family_id": s["family_id"],
            "ip": s.get("ip", ""),
            "user_agent": s.get("user_agent", ""),
            "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
            "expires_at": s["expires_at"].isoformat() if s.get("expires_at") else None,
            "current": s["family_id"] == current_family,
        }
        for s in sessions
    ]
    out.sort(key=lambda x: not x["current"])  # stable: current device first
    return out


SECURITY_EVENT_ACTIONS = (
    "LOGIN_SUCCESS",
    "LOGIN_FAILED",
    "ACCOUNT_LOCKED",
    "ACTIVATE_ACCOUNT",
    "PASSWORD_CHANGE",
    "PASSWORD_RESET",
    "LOGOUT_ALL",
    "REVOKE_SESSION",
    "TOKEN_REUSE_DETECTED",
)


async def list_security_activity(db, user_id: str, limit: int = 20) -> list[dict]:
    """Recent security-relevant audit events about the user's own account."""
    limit = max(1, min(limit, 100))
    rows = await db["audit_logs"].find(
        {
            "action": {"$in": list(SECURITY_EVENT_ACTIONS)},
            "$or": [{"target_id": user_id}, {"actor_id": user_id}],
        },
        {"action": 1, "ts": 1, "ip": 1, "after": 1},
    ).sort("ts", -1).limit(limit).to_list(length=limit)
    return [
        {
            "action": r["action"],
            "ts": r["ts"].isoformat() if r.get("ts") else None,
            "ip": r.get("ip", ""),
            "reason": (r.get("after") or {}).get("reason"),
        }
        for r in rows
    ]


async def revoke_session(db, user_id: str, family_id: str) -> bool:
    revoked = await user_repo.revoke_session_by_family(db, user_id, family_id)
    if revoked:
        await _audit(db, user_id, "", "REVOKE_SESSION", family_id)
    return revoked


async def forgot_password(db, email: str) -> None:
    """Always returns None — no user enumeration."""
    user = await user_repo.find_user_by_email(db, email)
    if not user or user.get("status") != "ACTIVE":
        return
    token = generate_opaque_token()
    token_hash = hash_token(token)
    now = _clock.now()
    expires = now + timedelta(minutes=30)
    await user_repo.update_user(db, str(user["_id"]), {
        "reset_token_hash": token_hash,
        "reset_token_expires_at": expires,
    })
    # Queue notification outbox event (never expose raw token in HTTP response)
    await db["outbox"].insert_one({
        "channel": "EMAIL",
        "to": user["email"],
        "payload": {"type": "PASSWORD_RESET", "reset_token_prefix": token[:8]},
        "status": "PENDING",
        "attempts": 0,
        "next_attempt_at": now,
        "created_at": now,
    })


async def reset_password(db, token: str, new_password: str, ip: str = "") -> None:
    token_hash = hash_token(token)
    user = await user_repo.find_user_by_reset_token(db, token_hash)
    if not user:
        raise UnauthorizedError("Invalid or expired reset token", code="TOKEN_INVALID")
    now = _clock.now()
    if user.get("reset_token_expires_at") and user["reset_token_expires_at"] < now:
        raise UnauthorizedError("Reset token expired", code="TOKEN_EXPIRED")
    _validate_password(new_password, identifier=user.get("roll_no") or user.get("email", ""))
    await user_repo.update_user(db, str(user["_id"]), {
        "password_hash": hash_password(new_password),
        "reset_token_hash": None,
        "reset_token_expires_at": None,
    })
    await logout_all(db, str(user["_id"]))
    await _audit(db, str(user["_id"]), user.get("role", ""), "PASSWORD_RESET", str(user["_id"]), ip=ip)


async def change_password(db, user_id: str, old_password: str, new_password: str, ip: str = "") -> None:
    user = await user_repo.find_user_by_id(db, user_id)
    if not user or not verify_password(old_password, user.get("password_hash", "")):
        raise UnauthorizedError("Current password is incorrect", code="INVALID_CREDENTIALS")
    _validate_password(new_password, identifier=user.get("roll_no") or user.get("email", ""))
    await user_repo.update_user(db, user_id, {"password_hash": hash_password(new_password)})
    await logout_all(db, user_id)
    await _audit(db, user_id, user.get("role", ""), "PASSWORD_CHANGE", user_id, ip=ip)
