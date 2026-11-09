"""Tests for FairNest policy simulator: determinism, allocator alignment, fairness invariants, no payment."""

import os
import sys

_SIM_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND_DIR = os.path.abspath(os.path.join(_SIM_ROOT, "..", "backend"))
for p in (_SIM_ROOT, _BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.allocator.core import AppIn, Choice, Policy, RoomIn, assign_in_order  # noqa: E402
from simulator.engine import allocate, run_simulation, simulate_multi_cycle  # noqa: E402
from simulator.generators import (  # noqa: E402
    SimCycleInput,
    SimGroup,
    SimRoom,
    SimStudent,
    generate_cycle_input,
    generate_groups,
    generate_rooms,
    generate_students,
)


def test_same_seed_same_result():
    for seed in [0, 42, 999]:
        students = generate_students(60, seed)
        rooms = generate_rooms(24, seed)
        groups = generate_groups(students, 0.4, 4, seed)
        ci = generate_cycle_input(students, rooms, groups, "c0", seed)
        r1 = allocate(ci, "credit_weighted", seed)
        r2 = allocate(ci, "credit_weighted", seed)
        assert r1 == r2, f"Non-deterministic for seed {seed}"


def test_different_seeds_differ():
    students = generate_students(80, 0)
    rooms = generate_rooms(32, 0)
    groups = generate_groups(students, 0.4, 4, 0)
    ci = generate_cycle_input(students, rooms, groups, "c0", 0)
    r1 = allocate(ci, "random", 1)
    r2 = allocate(ci, "random", 99)
    assert isinstance(r1, dict) and isinstance(r2, dict)
    assert r1 != r2


def test_no_overbooking_and_exact_fit():
    seed = 7
    students = generate_students(100, seed)
    rooms = generate_rooms(60, seed)
    groups = generate_groups(students, 0.35, 3, seed)
    ci = generate_cycle_input(students, rooms, groups, "c0", seed, fill_rule="EXACT")
    allotments = allocate(ci, "credit_weighted", seed, fill_rule="EXACT")

    room_usage = {}
    room_cap = {r.room_id: r.capacity for r in rooms}
    group_map = {g.group_id: g for g in groups}
    for gid, room_id in allotments.items():
        if room_id:
            size = len(group_map[gid].member_ids)
            assert size == room_cap[room_id], "EXACT fill rule violated"
            room_usage[room_id] = room_usage.get(room_id, 0) + size

    for room_id, used in room_usage.items():
        assert used <= room_cap[room_id]


def test_tier0_accessibility_prioritized():
    """Tier-0 (accessibility verified) solo student beats high-credit Tier-1 solo student for same room."""
    students = [
        SimStudent("s_acc", "M", credit_balance=0, hostel_id="H_M1", accessibility_verified=True),
        SimStudent("s_high", "M", credit_balance=10, hostel_id="H_M1", accessibility_verified=False),
    ]
    rooms = [SimRoom("r101", "H_M1", 1, "101", "M", capacity=1)]
    groups = [
        SimGroup("g_acc", "H_M1", ["s_acc"], tier=0),
        SimGroup("g_high", "H_M1", ["s_high"], tier=1),
    ]
    choice = [Choice(kind="ROOM", room_id="r101", hostel_id="H_M1")]
    ci = SimCycleInput(
        cycle_id="tier0_test",
        students=students,
        rooms=rooms,
        groups=groups,
        applications={"g_acc": choice, "g_high": choice},
        fallbacks={"g_acc": "NONE", "g_high": "NONE"},
    )
    for seed in range(10):
        res = allocate(ci, "credit_weighted", seed)
        assert res["g_acc"] == "r101"
        assert res["g_high"] is None


def test_cascade_preserves_round1_order():
    """assign_in_order re-offers released rooms by Round-1 order_index, reinsert=True first."""
    rooms = {
        "r1": RoomIn(hostel_id="H1", floor_no=1, room_no="101", capacity=1),
    }
    apps = [
        AppIn(id="g_later", tier=1, group_size=1, choices=[Choice(kind="ROOM", room_id="r1", hostel_id="H1")], fallback="NONE", weight=10.0, reinsert=False, order_index=5),
        AppIn(id="g_earlier", tier=1, group_size=1, choices=[Choice(kind="ROOM", room_id="r1", hostel_id="H1")], fallback="NONE", weight=1.0, reinsert=False, order_index=2),
    ]
    res = assign_in_order(apps, rooms, {"r1"}, Policy())
    assert len(res.allotments) == 1
    assert res.allotments[0].app_id == "g_earlier"

    # Reinsert takes top priority even if order_index is larger
    apps.append(
        AppIn(id="g_revoked", tier=1, group_size=1, choices=[Choice(kind="ROOM", room_id="r1", hostel_id="H1")], fallback="NONE", weight=1.0, reinsert=True, order_index=9)
    )
    res2 = assign_in_order(apps, rooms, {"r1"}, Policy())
    assert res2.allotments[0].app_id == "g_revoked"


def test_multi_cycle_credits_stay_clamped_and_no_payment():
    cfg = {
        "n_students": 40,
        "n_beds": 20,
        "cycles": 8,
        "c_init": 3,
        "c_min": 0,
        "c_max": 10,
        "carry_over_factor": 0.5,
        "p_confirm": 0.75,
        "p_group": 0.4,
        "max_group_size": 3,
    }
    summary = simulate_multi_cycle(cfg, "credit_weighted", seed=123)
    assert 0.0 <= summary["jain_index"] <= 1.0
    assert 0.0 <= summary["allocation_rate"] <= 1.0

    # Verify individual cycle student bounds & zero payment attributes
    students = generate_students(40, 123)
    rooms = generate_rooms(20, 123)
    for c in range(8):
        groups = generate_groups(students, 0.4, 3, c + 1)
        ci = generate_cycle_input(students, rooms, groups, f"c{c}", c + 1)
        run_simulation(ci, "credit_weighted", c + 1, p_confirm=0.75)
        for s in students:
            assert 0 <= s.credit_balance <= 10
            assert not hasattr(s, "payment_status")
