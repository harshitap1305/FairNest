"""FastAPI dependencies: DB, current user, role guards."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import UnauthorizedError, ForbiddenError
from app.core.security import decode_access_token
from app.db.client import get_db as _get_db_client
from app.repositories import users as user_repo

_bearer = HTTPBearer(auto_error=False)


async def get_db(request: Request):
    settings = get_settings()
    return _get_db_client(settings.MONGO_DB)


async def get_client():
    from app.db.client import get_client as _gc
    return _gc()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db=Depends(get_db),
) -> dict:
    if not credentials:
        raise UnauthorizedError("Not authenticated", code="UNAUTHORIZED")
    payload = decode_access_token(credentials.credentials)
    user = await user_repo.find_user_by_id(db, payload["sub"])
    if not user:
        raise UnauthorizedError("User not found", code="UNAUTHORIZED")
    if user.get("status") in ("DISABLED", "INVITED"):
        raise UnauthorizedError("Account not accessible", code="UNAUTHORIZED")
    if user.get("token_version", 0) != payload.get("tv", 0):
        raise UnauthorizedError("Session invalidated", code="TOKEN_INVALID")
    return user


def require_roles(*roles: str):
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise ForbiddenError(f"Required role: {', '.join(roles)}")
        return user
    return _dep


async def current_student(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in ("STUDENT", "SUPER_ADMIN"):
        raise ForbiddenError("Students only")
    return user


async def current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in ("ADMIN", "SUPER_ADMIN"):
        raise ForbiddenError("Admins only")
    return user


async def current_warden(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in ("WARDEN", "ADMIN", "SUPER_ADMIN"):
        raise ForbiddenError("Wardens only")
    return user


async def current_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "SUPER_ADMIN":
        raise ForbiddenError("Super admins only")
    return user


async def current_auditor(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in ("AUDITOR", "SUPER_ADMIN", "ADMIN"):
        raise ForbiddenError("Auditors only")
    return user
