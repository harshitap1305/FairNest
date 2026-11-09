"""Unit tests for the canonical Efraimidis-Spirakis allocator & verification hashes."""

from __future__ import annotations

import hashlib

from app.allocator.core import (
    AppIn,
    Choice,
    Fallback,
    Policy,
    RoomIn,
    _room_sort_key,
    allocate,
    assign_in_order,
    compute_weight,
    run_allocation_pure,
)
from app.allocator.verify import (
    compute_input_hash,
    compute_output_hash,
    compute_seed_commitment,
)


def test_seed_commitment_deterministic_sha256():
    secret = "my_secret_seed_abc123"
    c1 = compute_seed_commitment(secret)
    c2 = compute_seed_commitment(secret)
    assert c1 == c2
    assert len(c1) == 64
    assert c1 == hashlib.sha256(secret.encode()).hexdigest()


def test_input_and_output_hashes_order_independent():
    apps_a = [
        {"group_id": "g1", "choices": ["r1"], "weight": 1.0},
        {"group_id": "g2", "choices": ["r2"], "weight": 2.0},
    ]
    apps_b = list(reversed(apps_a))
    assert compute_input_hash(apps_a) == compute_input_hash(apps_b)

    out1 = [{"group_id": "g1", "room_id": "r1", "order_index": 0}]
    out2 = [{"group_id": "g1", "room_id": "r2", "order_index": 0}]
    assert compute_output_hash(out1) == compute_output_hash(out1)
    assert compute_output_hash(out1) != compute_output_hash(out2)


def test_room_natural_sort_key():
    rooms = ["201", "A-10", "21", "A-2", "102", "101"]
    sorted_rooms = sorted(rooms, key=_room_sort_key)
    assert sorted_rooms.index("21") < sorted_rooms.index("201")
    assert sorted_rooms.index("A-2") < sorted_rooms.index("A-10")
    assert sorted_rooms.index("101") < sorted_rooms.index("102")


def test_compute_weight_policies():
    assert compute_weight([2, 4], "MEAN") == 4.0
    assert compute_weight([2, 4], "MIN") == 3.0
    assert compute_weight([2, 4], "MAX") == 5.0


def test_tier0_accessibility_beats_high_credit_tier1():
    rooms = {"r1": RoomIn("H1", 1, "101", 1)}
    apps = [
        AppIn("a_high", tier=1, group_size=1, choices=[Choice("ROOM", room_id="r1")], fallback=Fallback.NONE, weight=11.0),
        AppIn("a_acc", tier=0, group_size=1, choices=[Choice("ROOM", room_id="r1")], fallback=Fallback.NONE, weight=1.0),
    ]
    for s in [b"seed1", b"seed2", b"seed3", b"seed4"]:
        res = allocate(apps, rooms, {"r1"}, s, Policy())
        assert len(res.allotments) == 1
        assert res.allotments[0].app_id == "a_acc"
        assert [w.app_id for w in res.waitlisted] == ["a_high"]


def test_exact_vs_at_most_fill_rule():
    rooms = {"r_cap3": RoomIn("H1", 1, "201", 3)}
    apps = [
        AppIn("a_pair", tier=1, group_size=2, choices=[Choice("ROOM", room_id="r_cap3")], fallback=Fallback.NONE, weight=5.0),
    ]
    res_exact = allocate(apps, rooms, {"r_cap3"}, b"s1", Policy(fill_rule="EXACT"))
    assert len(res_exact.allotments) == 0
    assert len(res_exact.waitlisted) == 1

    res_at_most = allocate(apps, rooms, {"r_cap3"}, b"s1", Policy(fill_rule="AT_MOST"))
    assert len(res_at_most.allotments) == 1
    assert res_at_most.allotments[0].room_id == "r_cap3"


def test_floor_choice_picks_lowest_natural_room_no():
    rooms = {
        "r210": RoomIn("H1", 2, "210", 2),
        "r202": RoomIn("H1", 2, "202", 2),
        "r21": RoomIn("H1", 2, "21", 2),
    }
    app = AppIn(
        "g1",
        tier=1,
        group_size=2,
        choices=[Choice("FLOOR", hostel_id="H1", floor_no=2)],
        fallback=Fallback.NONE,
        weight=4.0,
    )
    res = allocate([app], rooms, {"r210", "r202", "r21"}, b"seed", Policy())
    assert len(res.allotments) == 1
    assert res.allotments[0].room_id == "r21"
    assert res.allotments[0].rank_obtained == 1


def test_fallback_any_eligible_vs_none():
    rooms = {
        "r101": RoomIn("H1", 1, "101", 1),
        "r102": RoomIn("H1", 1, "102", 1),
    }
    apps = [
        AppIn("a1", tier=1, group_size=1, choices=[Choice("ROOM", room_id="r101", hostel_id="H1")], fallback=Fallback.NONE, weight=10.0),
        AppIn("a2", tier=1, group_size=1, choices=[Choice("ROOM", room_id="r101", hostel_id="H1")], fallback=Fallback.ANY_ELIGIBLE, weight=10.0),
    ]
    res = allocate(apps, rooms, {"r101", "r102"}, b"fixed_seed", Policy())
    allotted_map = {a.app_id: a for a in res.allotments}
    # Regardless of which goes first, a2 either gets rank 1 or fallback rank 2 in r102
    assert "a2" in allotted_map
    assert allotted_map["a2"].rank_obtained in (1, 2)


def test_assign_in_order_preserves_round1_order_and_reinsert_priority():
    rooms = {"r1": RoomIn("H1", 1, "101", 1)}
    apps = [
        AppIn("later", tier=1, group_size=1, choices=[Choice("ROOM", room_id="r1")], fallback=Fallback.NONE, weight=100.0, reinsert=False, order_index=7),
        AppIn("earlier", tier=1, group_size=1, choices=[Choice("ROOM", room_id="r1")], fallback=Fallback.NONE, weight=1.0, reinsert=False, order_index=2),
        AppIn("revoked", tier=1, group_size=1, choices=[Choice("ROOM", room_id="r1")], fallback=Fallback.NONE, weight=1.0, reinsert=True, order_index=9),
    ]
    res = assign_in_order(apps, rooms, {"r1"}, Policy())
    assert len(res.allotments) == 1
    assert res.allotments[0].app_id == "revoked"
    assert res.allotments[0].order_index == 9


def test_run_allocation_pure_is_deterministic():
    apps = [
        {"group_id": f"g{i}", "choices": ["r1", "r2"], "weight": float(1 + i)}
        for i in range(5)
    ]
    rooms = [
        {"room_id": "r1", "hostel_id": "h1", "floor_no": 1, "room_no": "101", "capacity": 1},
        {"room_id": "r2", "hostel_id": "h1", "floor_no": 1, "room_no": "102", "capacity": 1},
    ]
    o1 = run_allocation_pure(apps, rooms, "seed_xyz")
    o2 = run_allocation_pure(apps, rooms, "seed_xyz")
    assert o1 == o2
    allotted_rooms = [x["room_id"] for x in o1 if x["room_id"] is not None]
    assert len(allotted_rooms) == len(set(allotted_rooms)) == 2
