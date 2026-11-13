"""Unit tests for the pure room-demand and waitlist-position helpers."""

from __future__ import annotations

from app.services.insights_service import compute_room_demand, compute_waitlist_position

INVENTORY = [
    {"room_id": "r101", "capacity": 2},
    {"room_id": "r102", "capacity": 2},
    {"room_id": "r103", "capacity": 1},
    {"room_id": "r104", "capacity": 3},
]


def _app(choices, size=2, status="SUBMITTED"):
    return {
        "status": status,
        "group_size": size,
        "ranked_choices": [
            {"kind": "ROOM", "room_id": rid, "rank": i + 1} if not str(rid).startswith("F")
            else {"kind": "FLOOR", "floor_no": int(rid[1:]), "rank": i + 1}
            for i, rid in enumerate(choices)
        ],
    }


def test_demand_counts_first_choice_top3_and_levels():
    apps = [
        _app(["r101", "r102"]),
        _app(["r101", "F1"]),
        _app(["r102", "r101", "r104"]),
        _app(["r103"], size=1),
    ]
    d = compute_room_demand(apps, INVENTORY)
    assert d["insufficient_data"] is False
    assert d["applications_counted"] == 4
    r101 = d["rooms"]["r101"]
    assert (r101["first_choice"], r101["top3"], r101["mentions"]) == (2, 3, 3)
    assert r101["level"] == "HIGH"
    assert d["rooms"]["r104"]["level"] == "LOW"  # only ever a 3rd choice
    assert d["floors"] == {"1": 1}
    assert d["rooms"]["r101"]["score"] == 2.5  # 1 + 1 + 1/2


def test_rooms_nobody_wants_are_none():
    apps = [_app(["r101"]) for _ in range(3)]
    d = compute_room_demand(apps, INVENTORY)
    assert d["rooms"]["r102"] == {"first_choice": 0, "top3": 0, "mentions": 0, "score": 0, "level": "NONE"}


def test_drafts_and_withdrawn_are_ignored_and_small_samples_hidden():
    apps = [
        _app(["r101"]),
        _app(["r101"], status="DRAFT"),
        _app(["r101"], status="WITHDRAWN"),
        _app(["r102"]),
    ]
    d = compute_room_demand(apps, INVENTORY)
    assert d["applications_counted"] == 2
    assert d["insufficient_data"] is True
    assert d["rooms"] == {} and d["floors"] == {}
    # Size-level competition is still reported
    assert d["by_size"] == [{"group_size": 2, "groups": 2, "matching_rooms": 2, "groups_per_room": 1.0}]


def test_by_size_respects_fill_rule():
    apps = [_app(["r101"], size=1) for _ in range(3)]
    exact = compute_room_demand(apps, INVENTORY, fill_rule="EXACT")["by_size"][0]
    at_most = compute_room_demand(apps, INVENTORY, fill_rule="AT_MOST")["by_size"][0]
    assert exact["matching_rooms"] == 1
    assert at_most["matching_rooms"] == 4
    assert exact["groups_per_room"] == 3.0


def _w(_id, order_index, size=2, reinsert=False):
    return {"_id": _id, "order_index": order_index, "group_size": size, "reinsert": reinsert,
            "status": "WAITLISTED"}


def test_waitlist_position_follows_cascade_order():
    waitlisted = [_w("a", 5), _w("b", 2, size=1), _w("c", 9, reinsert=True), _w("me", 7)]
    available = [{"capacity": 2}, {"capacity": 1}, {"capacity": 2}]
    res = compute_waitlist_position(waitlisted[3], waitlisted, available)
    # Order: c (reinsert) -> b (2) -> a (5) -> me (7)
    assert res["position"] == 4
    assert res["total_waitlisted"] == 4
    assert res["ahead_same_size"] == 2  # c and a
    assert res["fitting_rooms_available"] == 2
    assert res["on_waitlist"] is True


def test_not_on_waitlist():
    me = {"_id": "me", "status": "CONFIRMED", "group_size": 2}
    res = compute_waitlist_position(me, [_w("a", 1)], [])
    assert res["on_waitlist"] is False and res["position"] is None
    assert res["status"] == "CONFIRMED"
