"""Generate synthetic student, room, group, and application cohorts for simulation."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List

from app.allocator.core import Choice


@dataclass
class SimStudent:
    student_id: str
    gender: str  # "M" or "F"
    credit_balance: int
    hostel_id: str
    accessibility_verified: bool = False
    year: int = 1


@dataclass
class SimRoom:
    room_id: str
    hostel_id: str
    floor_no: int
    room_no: str
    gender: str
    capacity: int


@dataclass
class SimGroup:
    group_id: str
    hostel_id: str
    member_ids: List[str]
    tier: int = 1


@dataclass
class SimCycleInput:
    cycle_id: str
    students: List[SimStudent]
    rooms: List[SimRoom]
    groups: List[SimGroup]
    applications: Dict[str, List[Choice]]
    fallbacks: Dict[str, str]


_HOSTELS = [
    ("H_M1", "M"),
    ("H_M2", "M"),
    ("H_F1", "F"),
    ("H_F2", "F"),
]


def generate_students(
    n: int,
    seed: int,
    c_init: int = 3,
    c_min: int = 0,
    c_max: int = 10,
    p_tier0: float = 0.03,
    skew_credits: bool = False,
) -> List[SimStudent]:
    rng = random.Random(seed)
    students: List[SimStudent] = []
    for i in range(n):
        gender = "M" if i < n // 2 else "F"
        hostel_id = rng.choice(["H_M1", "H_M2"] if gender == "M" else ["H_F1", "H_F2"])
        if skew_credits:
            # Polarized initial credit distribution within canonical [c_min, c_max]
            credit = rng.choice([0, 1, 2, 8, 9, 10])
        else:
            credit = c_init
        credit = max(c_min, min(c_max, int(credit)))
        tier0 = rng.random() < p_tier0
        year = rng.randint(1, 4)
        students.append(
            SimStudent(
                student_id=f"s{i:04d}",
                gender=gender,
                credit_balance=credit,
                hostel_id=hostel_id,
                accessibility_verified=tier0,
                year=year,
            )
        )
    return students


def generate_rooms(n_beds: int, seed: int) -> List[SimRoom]:
    rng = random.Random(seed)
    rooms: List[SimRoom] = []
    capacities = [1, 2, 3, 4]
    beds_per_hostel = max(4, n_beds // len(_HOSTELS))

    for hostel_id, gender in _HOSTELS:
        beds = 0
        floor_no = 1
        room_seq = 1
        while beds < beds_per_hostel:
            cap = rng.choice(capacities)
            if beds + cap > beds_per_hostel:
                cap = max(1, beds_per_hostel - beds)
                if cap > 4:
                    cap = 4
            room_no = f"{floor_no}{room_seq:02d}"
            rooms.append(
                SimRoom(
                    room_id=f"r_{hostel_id}_{room_no}",
                    hostel_id=hostel_id,
                    floor_no=floor_no,
                    room_no=room_no,
                    gender=gender,
                    capacity=cap,
                )
            )
            beds += cap
            room_seq += 1
            if room_seq > 10:
                floor_no += 1
                room_seq = 1
    return rooms


def generate_groups(
    students: List[SimStudent],
    p_group: float,
    max_group_size: int,
    seed: int,
) -> List[SimGroup]:
    """Form solo and same-hostel groups (matches single-hostel release scope R-RLS-1)."""
    rng = random.Random(seed)
    by_hostel: Dict[str, List[SimStudent]] = {}
    for s in students:
        by_hostel.setdefault(s.hostel_id, []).append(s)

    groups: List[SimGroup] = []
    gid = 0
    for hostel_id in sorted(by_hostel.keys()):
        ungrouped = list(by_hostel[hostel_id])
        rng.shuffle(ungrouped)
        while ungrouped:
            s = ungrouped.pop()
            if ungrouped and rng.random() < p_group:
                max_sz = min(max_group_size, len(ungrouped) + 1)
                size = rng.randint(2, max_sz) if max_sz >= 2 else 1
                members = [s]
                for _ in range(size - 1):
                    members.append(ungrouped.pop())
            else:
                members = [s]
            tier = 0 if any(m.accessibility_verified for m in members) else 1
            groups.append(
                SimGroup(
                    group_id=f"g{gid:04d}",
                    hostel_id=hostel_id,
                    member_ids=[m.student_id for m in members],
                    tier=tier,
                )
            )
            gid += 1
    return groups


def generate_cycle_input(
    students: List[SimStudent],
    rooms: List[SimRoom],
    groups: List[SimGroup],
    cycle_id: str,
    seed: int,
    fill_rule: str = "EXACT",
    floor_choice_prob: float = 0.2,
    fallback_prob: float = 0.6,
) -> SimCycleInput:
    """Generate ranked ROOM/FLOOR choices within the group's hostel matching fill_rule."""
    rng = random.Random(seed)
    applications: Dict[str, List[Choice]] = {}
    fallbacks: Dict[str, str] = {}

    for g in groups:
        gsize = len(g.member_ids)
        if fill_rule == "EXACT":
            eligible = [r for r in rooms if r.hostel_id == g.hostel_id and r.capacity == gsize]
        else:
            eligible = [r for r in rooms if r.hostel_id == g.hostel_id and r.capacity >= gsize]
        rng.shuffle(eligible)
        choices: List[Choice] = []
        floors_seen = set()
        for r in eligible[:6]:
            if rng.random() < floor_choice_prob and (r.hostel_id, r.floor_no) not in floors_seen:
                floors_seen.add((r.hostel_id, r.floor_no))
                choices.append(Choice(kind="FLOOR", hostel_id=r.hostel_id, floor_no=r.floor_no))
            else:
                choices.append(Choice(kind="ROOM", room_id=r.room_id, hostel_id=r.hostel_id))
        applications[g.group_id] = choices
        fallbacks[g.group_id] = "ANY_ELIGIBLE" if rng.random() < fallback_prob else "NONE"

    return SimCycleInput(
        cycle_id=cycle_id,
        students=students,
        rooms=rooms,
        groups=groups,
        applications=applications,
        fallbacks=fallbacks,
    )
