"""Main simulation engine using canonical backend allocator & fairness rules (NO payment)."""

from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional, Set, Tuple

from app.allocator.core import (
    AllocationResult,
    AppIn,
    Policy,
    RoomIn,
    allocate as core_allocate,
    apply_carry_over,
    assign_in_order,
    clamp_credits,
)
from app.fairness.engine import DEFAULT_POLICY, delta_for_outcome
from .behaviour import simulate_confirmations
from .generators import (
    SimCycleInput,
    SimStudent,
    generate_cycle_input,
    generate_groups,
    generate_rooms,
    generate_students,
)
from .metrics import (
    average_rank,
    group_vs_solo_success,
    jain_index,
    longest_losing_streak,
    success_by_credit_band,
    top_k_rate,
)
from .policies import POLICIES


def _build_core_inputs(
    cycle_input: SimCycleInput,
    policy_name: str,
    seed: int,
    fill_rule: str = "EXACT",
) -> Tuple[List[AppIn], Dict[str, RoomIn], Set[str], Policy, bytes]:
    if policy_name not in POLICIES:
        raise ValueError(f"Unknown policy: {policy_name}")

    policy_fn = POLICIES[policy_name]
    student_map = {s.student_id: s for s in cycle_input.students}

    rng = random.Random(seed)
    arrival_ids = [g.group_id for g in cycle_input.groups]
    rng.shuffle(arrival_ids)
    arrival_order = {gid: idx for idx, gid in enumerate(arrival_ids)}

    rooms_dict: Dict[str, RoomIn] = {
        r.room_id: RoomIn(
            hostel_id=r.hostel_id,
            floor_no=r.floor_no,
            room_no=r.room_no,
            capacity=r.capacity,
        )
        for r in cycle_input.rooms
    }
    free_room_ids: Set[str] = set(rooms_dict.keys())

    apps_in: List[AppIn] = []
    for g in cycle_input.groups:
        w = policy_fn(g, student_map, arrival_order)
        apps_in.append(
            AppIn(
                id=g.group_id,
                tier=0 if policy_name in ("credit_weighted", "min_credit", "max_credit") and g.tier == 0 else (g.tier if policy_name != "random" else 1),
                group_size=len(g.member_ids),
                choices=cycle_input.applications.get(g.group_id, []),
                fallback=cycle_input.fallbacks.get(g.group_id, "NONE"),
                weight=max(1e-6, float(w)),
                reinsert=False,
                order_index=arrival_order[g.group_id] if policy_name == "fcfs" else None,
            )
        )

    seed_bytes = hashlib.sha256(f"{cycle_input.cycle_id}:{seed}".encode("utf-8")).digest()
    policy_obj = Policy(fill_rule=fill_rule)
    return apps_in, rooms_dict, free_room_ids, policy_obj, seed_bytes


def allocate_detailed(
    cycle_input: SimCycleInput,
    policy_name: str,
    seed: int,
    fill_rule: str = "EXACT",
) -> Tuple[AllocationResult, List[AppIn], Dict[str, RoomIn], Policy]:
    """Run Round-1 allocation through canonical backend allocator."""
    apps_in, rooms_dict, free_room_ids, policy_obj, seed_bytes = _build_core_inputs(
        cycle_input, policy_name, seed, fill_rule=fill_rule
    )
    if policy_name == "fcfs":
        result = assign_in_order(apps_in, rooms_dict, free_room_ids, policy_obj)
    else:
        result = core_allocate(apps_in, rooms_dict, free_room_ids, seed_bytes, policy_obj)
    return result, apps_in, rooms_dict, policy_obj


def allocate(
    cycle_input: SimCycleInput,
    policy_name: str,
    seed: int,
    fill_rule: str = "EXACT",
) -> Dict[str, Optional[str]]:
    """Return group_id -> room_id (or None if waitlisted) using canonical allocator."""
    result, _, _, _ = allocate_detailed(cycle_input, policy_name, seed, fill_rule=fill_rule)
    allotments: Dict[str, Optional[str]] = {g.group_id: None for g in cycle_input.groups}
    for a_out in result.allotments:
        allotments[a_out.app_id] = a_out.room_id
    return allotments


def run_simulation(
    cycle_input: SimCycleInput,
    policy_name: str,
    seed: int,
    p_confirm: float,
    policy_cfg: Optional[dict] = None,
) -> dict:
    """
    Simulate one full cycle:
      Round-1 allocate -> HELD accept/decline (NO payment) -> Cascade rounds via assign_in_order
      -> Credit settlement via canonical engine.delta_for_outcome (clamped to [C_MIN, C_MAX]).
    """
    cfg = {**DEFAULT_POLICY, **(policy_cfg or {})}
    fill_rule = cfg.get("fill_rule", "EXACT")
    c_min = int(cfg.get("c_min", 0))
    c_max = int(cfg.get("c_max", 10))
    max_cascade_rounds = int(cfg.get("max_cascade_rounds", 3))

    result, apps_in, rooms_dict, policy_obj = allocate_detailed(
        cycle_input, policy_name, seed, fill_rule=fill_rule
    )
    app_lookup: Dict[str, AppIn] = {a.id: a for a in apps_in}
    student_map: Dict[str, SimStudent] = {s.student_id: s for s in cycle_input.students}

    free_rooms: Set[str] = set(rooms_dict.keys())
    confirmed: Dict[str, dict] = {}
    forfeited: Set[str] = set()
    n_round1_held = len(result.allotments)
    n_declined = 0
    n_cascade_confirmed = 0

    # Track Round-1 order_index onto apps so cascade preserves Round-1 order strictly
    order_pos = {app_id: idx for idx, app_id in enumerate(result.order)}
    for gid, a_in in app_lookup.items():
        a_in.order_index = order_pos.get(gid, 10**9)

    current_holds = result.allotments
    waitlisted_ids = [w.app_id for w in result.waitlisted]

    for a_out in current_holds:
        free_rooms.discard(a_out.room_id)

    round_no = 1
    while current_holds:
        held_map = {a.app_id: a.room_id for a in current_holds}
        outcomes = simulate_confirmations(held_map, cycle_input.groups, p_confirm, seed + round_no * 101)
        for a_out in current_holds:
            if outcomes.get(a_out.app_id) == "CONFIRMED":
                confirmed[a_out.app_id] = {
                    "room_id": a_out.room_id,
                    "rank_obtained": a_out.rank_obtained,
                    "n_choices": len(app_lookup[a_out.app_id].choices),
                    "round_no": round_no,
                }
                if round_no > 1:
                    n_cascade_confirmed += 1
            else:
                forfeited.add(a_out.app_id)
                free_rooms.add(a_out.room_id)
                n_declined += 1

        if round_no >= (1 + max_cascade_rounds) or not waitlisted_ids or not free_rooms:
            break

        waitlisted_apps = [app_lookup[gid] for gid in waitlisted_ids if gid in app_lookup]
        cascade_res = assign_in_order(waitlisted_apps, rooms_dict, free_rooms, policy_obj)
        if not cascade_res.allotments:
            break

        round_no += 1
        current_holds = cascade_res.allotments
        for a_out in current_holds:
            free_rooms.discard(a_out.room_id)
        waitlisted_ids = [w.app_id for w in cascade_res.waitlisted]

    # Settle credits using canonical fairness engine rules
    confirmed_list = []
    group_outcomes = []
    student_cycle_records = []

    for g in cycle_input.groups:
        gid = g.group_id
        initial_credits = [student_map[sid].credit_balance for sid in g.member_ids]
        if gid in confirmed:
            info = confirmed[gid]
            outcome = "CONFIRMED"
            rank_obtained = info["rank_obtained"]
            n_choices = info["n_choices"]
            confirmed_list.append({"rank_obtained": rank_obtained})
            got_room = True
        elif gid in forfeited:
            outcome = "FORFEITED"
            rank_obtained = None
            n_choices = 0
            got_room = False
        else:
            outcome = "UNALLOTTED"
            rank_obtained = None
            n_choices = 0
            got_room = False

        group_outcomes.append({"group_size": len(g.member_ids), "got_room": got_room})
        delta, _ = delta_for_outcome(cfg, outcome, rank_obtained, n_choices)

        for idx, sid in enumerate(g.member_ids):
            st = student_map[sid]
            student_cycle_records.append({
                "student_id": sid,
                "credits": initial_credits[idx],
                "got_room": got_room,
                "group_size": len(g.member_ids),
            })
            st.credit_balance = clamp_credits(st.credit_balance + delta, c_min, c_max)

    n_confirmed = len(confirmed)
    gvs = group_vs_solo_success(group_outcomes)

    return {
        "cycle_id": cycle_input.cycle_id,
        "policy": policy_name,
        "seed": seed,
        "n_groups": len(cycle_input.groups),
        "n_round1_held": n_round1_held,
        "n_allocated": n_confirmed,
        "n_confirmed": n_confirmed,
        "n_cascade_confirmed": n_cascade_confirmed,
        "n_declined": n_declined,
        "allocation_rate": round(n_confirmed / max(len(cycle_input.groups), 1), 4),
        "confirm_rate": round(n_confirmed / max(n_round1_held + n_cascade_confirmed, 1), 4),
        "average_rank": round(average_rank(confirmed_list), 4),
        "top_1_rate": round(top_k_rate(confirmed_list, k=1), 4),
        "solo_success": round(gvs["solo"], 4),
        "group_success": round(gvs["group"], 4),
        "student_records": student_cycle_records,
    }


def simulate_multi_cycle(
    cfg: dict,
    policy_name: str,
    seed: int,
) -> dict:
    """Run multiple sequential cycles for one seed with persistent cohorts and credit carry-over."""
    n_students = int(cfg.get("n_students", 200))
    n_beds = int(cfg.get("n_beds", 100))
    n_cycles = int(cfg.get("cycles", 20))
    c_init = int(cfg.get("c_init", 3))
    c_min = int(cfg.get("c_min", 0))
    c_max = int(cfg.get("c_max", 10))
    carry_factor = float(cfg.get("carry_over_factor", 0.5))
    do_carry_over = bool(cfg.get("apply_carry_over", True))

    students = generate_students(
        n_students,
        seed=seed,
        c_init=c_init,
        c_min=c_min,
        c_max=c_max,
        p_tier0=float(cfg.get("p_tier0", 0.03)),
        skew_credits=bool(cfg.get("skew_credits", False)),
    )
    rooms = generate_rooms(n_beds, seed=seed)

    per_student_got: Dict[str, List[bool]] = {s.student_id: [] for s in students}
    all_student_records = []
    cycle_alloc_rates = []
    cycle_confirm_rates = []
    cycle_avg_ranks = []
    cycle_top1_rates = []

    for c_idx in range(n_cycles):
        cycle_seed = seed * 1000 + c_idx + 1
        groups = generate_groups(
            students,
            p_group=float(cfg.get("p_group", 0.4)),
            max_group_size=int(cfg.get("max_group_size", 4)),
            seed=cycle_seed,
        )
        ci = generate_cycle_input(
            students,
            rooms,
            groups,
            cycle_id=f"c{c_idx:02d}",
            seed=cycle_seed,
            fill_rule=str(cfg.get("fill_rule", "EXACT")),
        )
        res = run_simulation(
            ci,
            policy_name=policy_name,
            seed=cycle_seed,
            p_confirm=float(cfg.get("p_confirm", 0.85)),
            policy_cfg=cfg,
        )
        cycle_alloc_rates.append(res["allocation_rate"])
        cycle_confirm_rates.append(res["confirm_rate"])
        if res["average_rank"] > 0:
            cycle_avg_ranks.append(res["average_rank"])
        cycle_top1_rates.append(res["top_1_rate"])

        for rec in res["student_records"]:
            per_student_got[rec["student_id"]].append(bool(rec["got_room"]))
            all_student_records.append(rec)

        if do_carry_over and c_idx < n_cycles - 1:
            for s in students:
                s.credit_balance = clamp_credits(
                    apply_carry_over(s.credit_balance, c_init, carry_factor),
                    c_min,
                    c_max,
                )

    per_student_rates = [
        sum(1.0 for v in hist if v) / len(hist)
        for hist in per_student_got.values()
        if hist
    ]
    bands = success_by_credit_band(all_student_records)
    gvs = group_vs_solo_success(all_student_records)
    max_streak = max((longest_losing_streak(h) for h in per_student_got.values()), default=0)

    return {
        "policy": policy_name,
        "seed": seed,
        "cycles": n_cycles,
        "allocation_rate": round(sum(cycle_alloc_rates) / max(len(cycle_alloc_rates), 1), 4),
        "confirm_rate": round(sum(cycle_confirm_rates) / max(len(cycle_confirm_rates), 1), 4),
        "jain_index": round(jain_index(per_student_rates), 4),
        "average_rank": round(sum(cycle_avg_ranks) / max(len(cycle_avg_ranks), 1), 4),
        "top_1_rate": round(sum(cycle_top1_rates) / max(len(cycle_top1_rates), 1), 4),
        "max_losing_streak": max_streak,
        "band_0_2": round(bands.get("0-2", 0.0), 4),
        "band_3_5": round(bands.get("3-5", 0.0), 4),
        "band_6_10": round(bands.get("6-10", 0.0), 4),
        "solo_success": round(gvs.get("solo", 0.0), 4),
        "group_success": round(gvs.get("group", 0.0), 4),
    }
