"""RBAC permission helpers and FastAPI dependencies."""

from __future__ import annotations

from typing import Callable

from bson import ObjectId
from fastapi import Request

from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token


async def get_current_user(request: Request, db) -> dict:
    """
    Extract and validate the Bearer token, then load the user from DB.
    Checks token_version to support logout-all.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header", code="MISSING_TOKEN")

    token = auth_header[len("Bearer "):]
    payload = decode_access_token(token)

    user_id = payload["sub"]
    lookup_id = ObjectId(user_id) if ObjectId.is_valid(str(user_id)) else user_id
    user = await db["users"].find_one({"_id": lookup_id})
    if user is None:
        raise UnauthorizedError("User not found", code="USER_NOT_FOUND")

    if user.get("token_version", 0) != payload.get("tv", 0):
        raise UnauthorizedError("Token has been invalidated", code="TOKEN_INVALIDATED")

    if user.get("status") in ("LOCKED", "DISABLED", "INVITED"):
        raise ForbiddenError(f"Account is {user['status'].lower()}", code="ACCOUNT_INACTIVE")

    return user


def require_roles(*roles: str) -> Callable:
    """
    Returns a FastAPI dependency factory that enforces one of the given roles.
    Usage:  Depends(require_roles("ADMIN", "SUPER_ADMIN"))
    """

    async def _dep(request: Request, db=None) -> dict:
        # db is injected by the route's own Depends(get_db); we re-read it here.
        # Routes must include db as a param so it flows in; alternatively we
        # call get_current_user with the db already in scope.
        user = await get_current_user(request, db)
        if user["role"] not in roles:
            raise ForbiddenError(
                f"Required role(s): {roles}. Your role: {user['role']}",
                code="INSUFFICIENT_ROLE",
            )
        return user

    return _dep


async def require_leader(group_id: str, current_user: dict, db) -> dict:
    """
    Verify that current_user is the LEADER of group_id.
    Raises ForbiddenError otherwise.
    """
    membership = await db["memberships"].find_one(
        {
            "group_id": group_id,
            "user_id": str(current_user["_id"]),
            "role": "LEADER",
            "status": "ACCEPTED",
        }
    )
    if membership is None:
        raise ForbiddenError("You are not the leader of this group", code="NOT_LEADER")
    return membership


def assert_owns(user: dict, obj_user_id: str) -> None:
    """
    Raise NotFoundError (not 403) if the user does not own the object.
    This prevents resource enumeration by attackers.
    """
    if str(user["_id"]) != str(obj_user_id):
        raise NotFoundError("Resource not found")
