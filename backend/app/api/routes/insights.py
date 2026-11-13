"""Insight routes: aggregate room demand and the caller's waitlist position."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import current_student, get_current_user, get_db
from app.core.errors import NotFoundError
from app.core.scope import assert_user_hostel_scope
from app.repositories import catalogue as cat_repo
from app.repositories import core_repos as repo
from app.services import insights_service

router = APIRouter(tags=["insights"])


async def _load_cycle(db, cycle_id: str, user: dict) -> dict:
    cycle = await cat_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError("Cycle not found")
    assert_user_hostel_scope(user, cycle["hostel_id"])
    return cycle


@router.get("/cycles/{cycle_id}/room-demand")
async def room_demand(cycle_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    """Anonymous, aggregate popularity of each room in the cycle.

    Counts how often each room appears in submitted ranked lists (first choice,
    top three, any rank) plus competition per group size. Per-room numbers are
    withheld until enough applications exist that no single group can be identified.
    """
    cycle = await _load_cycle(db, cycle_id, user)
    apps = await db["applications"].find(
        {"cycle_id": cycle_id, "status": {"$in": list(insights_service.DEMAND_STATUSES)}},
        {"status": 1, "group_size": 1, "ranked_choices": 1},
    ).to_list(length=5000)
    inventory = await cat_repo.list_inventory(db, cycle_id)
    fill_rule = cycle.get("policy", {}).get("fill_rule", "EXACT")
    result = insights_service.compute_room_demand(apps, inventory, fill_rule=fill_rule)
    return {"cycle_id": cycle_id, "fill_rule": fill_rule, **result}


@router.get("/cycles/{cycle_id}/waitlist/me")
async def my_waitlist_position(cycle_id: str, user=Depends(current_student), db=Depends(get_db)):
    """Where the caller's group stands in the cascade queue for this cycle."""
    cycle = await _load_cycle(db, cycle_id, user)
    membership = await repo.get_accepted_membership(db, cycle_id, str(user["_id"]))
    if not membership:
        raise NotFoundError("You are not in a group for this cycle")
    my_app = await repo.get_application_by_group(db, cycle_id, membership["group_id"])
    if not my_app:
        raise NotFoundError("Your group has no application in this cycle")
    waitlisted = await repo.list_waitlisted_by_cycle(db, cycle_id)
    available = await cat_repo.list_inventory(db, cycle_id, status="AVAILABLE")
    fill_rule = cycle.get("policy", {}).get("fill_rule", "EXACT")
    result = insights_service.compute_waitlist_position(
        my_app, waitlisted, available, fill_rule=fill_rule
    )
    return {"cycle_id": cycle_id, "cycle_status": cycle.get("status"), **result}
