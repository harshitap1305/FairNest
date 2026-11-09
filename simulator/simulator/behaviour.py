"""Simulate student acceptance/decline behaviour (strictly NO payment step)."""

from __future__ import annotations

import random
from typing import Dict, List

from .generators import SimGroup


def simulate_confirmations(
    allotted_rooms: Dict[str, str],  # group_id -> room_id
    groups: List[SimGroup],
    p_confirm: float,
    seed: int,
) -> Dict[str, str]:
    """
    All members of a HELD allotment must accept within the hold window.
    Returns group_id -> "CONFIRMED" | "DECLINED" | "EXPIRED".
    """
    rng = random.Random(seed)
    outcomes: Dict[str, str] = {}
    group_map = {g.group_id: g for g in groups}

    for gid in sorted(allotted_rooms.keys()):
        g = group_map.get(gid)
        if not g:
            continue
        all_accept = all(rng.random() < p_confirm for _ in g.member_ids)
        outcomes[gid] = "CONFIRMED" if all_accept else rng.choice(["DECLINED", "EXPIRED"])

    return outcomes
