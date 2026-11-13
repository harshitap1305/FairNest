"""Student-facing insights: aggregate room demand and personal waitlist position.

Everything here is read-only and aggregate. Room demand never exposes who ranked a
room, and is withheld entirely while too few applications exist to stay anonymous.
Because Weighted RSD is strategy-proof, showing demand cannot help anyone game the
draw: ranking rooms truthfully stays optimal. It only helps students pick sensible
backup choices instead of listing rooms that are certain to go early.
"""

from __future__ import annotations

from collections import Counter, defaultdict

# Below this many counted applications, per-room numbers could reveal an
# individual group's choices, so the endpoint reports "insufficient data".
MIN_APPLICATIONS_FOR_DEMAND = 3

# Applications that express real demand (drafts and withdrawn ones do not).
DEMAND_STATUSES = (
    "SUBMITTED", "ALLOTTED", "WAITLISTED", "CONFIRMED", "FORFEITED", "UNALLOTTED",
)


def _fits(fill_rule: str, group_size: int, capacity: int) -> bool:
    if fill_rule == "AT_MOST":
        return group_size <= capacity
    return group_size == capacity


def _level(score: float, max_score: float) -> str:
    if score <= 0 or max_score <= 0:
        return "NONE"
    ratio = score / max_score
    if ratio >= 0.6:
        return "HIGH"
    if ratio >= 0.25:
        return "MEDIUM"
    return "LOW"


def compute_room_demand(
    applications: list[dict],
    inventory: list[dict],
    *,
    fill_rule: str = "EXACT",
    min_applications: int = MIN_APPLICATIONS_FOR_DEMAND,
) -> dict:
    """Pure aggregation of ranked choices into per-room / per-floor / per-size demand.

    A room's ``score`` weights each mention by 1/rank, so a first choice counts fully
    and a tenth choice counts a tenth. ``level`` buckets the score relative to the
    most wanted room in the cycle.
    """
    counted = [a for a in applications if a.get("status") in DEMAND_STATUSES]
    n_apps = len(counted)

    # Competition by group size is safe to show even with few applications.
    groups_by_size = Counter(int(a.get("group_size", 1) or 1) for a in counted)
    by_size = []
    for size in sorted(groups_by_size):
        rooms = sum(1 for inv in inventory if _fits(fill_rule, size, int(inv.get("capacity", 0))))
        groups = groups_by_size[size]
        by_size.append({
            "group_size": size,
            "groups": groups,
            "matching_rooms": rooms,
            "groups_per_room": round(groups / rooms, 2) if rooms else None,
        })

    if n_apps < min_applications:
        return {
            "applications_counted": n_apps,
            "insufficient_data": True,
            "min_applications": min_applications,
            "rooms": {},
            "floors": {},
            "by_size": by_size,
        }

    first = Counter()
    top3 = Counter()
    mentions = Counter()
    score: dict[str, float] = defaultdict(float)
    floor_mentions = Counter()
    for app in counted:
        choices = sorted(app.get("ranked_choices", []), key=lambda c: c.get("rank", 99))
        for pos, ch in enumerate(choices, start=1):
            rank = int(ch.get("rank") or pos)
            if ch.get("kind", "ROOM") == "FLOOR":
                if ch.get("floor_no") is not None:
                    floor_mentions[str(ch["floor_no"])] += 1
                continue
            rid = ch.get("room_id")
            if not rid:
                continue
            mentions[rid] += 1
            score[rid] += 1.0 / max(rank, 1)
            if rank == 1:
                first[rid] += 1
            if rank <= 3:
                top3[rid] += 1

    max_score = max(score.values(), default=0.0)
    rooms = {}
    for inv in inventory:
        rid = inv["room_id"]
        s = score.get(rid, 0.0)
        rooms[rid] = {
            "first_choice": first.get(rid, 0),
            "top3": top3.get(rid, 0),
            "mentions": mentions.get(rid, 0),
            "score": round(s, 3),
            "level": _level(s, max_score),
        }

    return {
        "applications_counted": n_apps,
        "insufficient_data": False,
        "min_applications": min_applications,
        "rooms": rooms,
        "floors": dict(floor_mentions),
        "by_size": by_size,
    }


def cascade_sort_key(app: dict):
    """Same ordering run_cascade uses: reinserts first, then original Round-1 order."""
    oi = app.get("order_index")
    return (not bool(app.get("reinsert", False)), oi if oi is not None else 10**9, str(app.get("_id")))


def compute_waitlist_position(
    my_app: dict,
    waitlisted: list[dict],
    available_inventory: list[dict],
    *,
    fill_rule: str = "EXACT",
) -> dict:
    """Where an application sits in the cascade queue and how many free rooms fit it."""
    ordered = sorted(waitlisted, key=cascade_sort_key)
    ids = [str(a["_id"]) for a in ordered]
    my_id = str(my_app["_id"])
    size = int(my_app.get("group_size", 1) or 1)
    position = ids.index(my_id) + 1 if my_id in ids else None
    ahead = ordered[: position - 1] if position else []
    return {
        "status": my_app.get("status"),
        "on_waitlist": position is not None,
        "position": position,
        "total_waitlisted": len(ordered),
        "ahead_same_size": sum(1 for a in ahead if int(a.get("group_size", 1) or 1) == size),
        "reinserted": bool(my_app.get("reinsert", False)),
        "group_size": size,
        "fitting_rooms_available": sum(
            1 for inv in available_inventory if _fits(fill_rule, size, int(inv.get("capacity", 0)))
        ),
    }
