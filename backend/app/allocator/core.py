"""
Pure-function allocator: no FastAPI, no DB, no clock, no global random.
Implements weighted Random Serial Dictatorship (Efraimidis–Spirakis).
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set, Dict


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ChoiceKind(str, Enum):
    ROOM = "ROOM"
    FLOOR = "FLOOR"


class FillRule(str, Enum):
    EXACT = "EXACT"
    AT_MOST = "AT_MOST"


class Fallback(str, Enum):
    ANY_ELIGIBLE = "ANY_ELIGIBLE"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Input data-classes
# ---------------------------------------------------------------------------

@dataclass
class Choice:
    """A single ranked preference."""
    kind: str                        # "ROOM" or "FLOOR"
    room_id: Optional[str] = None    # used when kind == "ROOM"
    hostel_id: Optional[str] = None  # used when kind == "FLOOR"
    floor_no: Optional[int] = None   # used when kind == "FLOOR"


@dataclass
class AppIn:
    """Input record for one application (one group)."""
    id: str                          # unique application identifier
    tier: int                        # 0 = highest priority (accessibility, etc.)
    group_size: int
    choices: List[Choice]            # ranked list, index 0 = rank 1
    fallback: str                    # "ANY_ELIGIBLE" or "NONE"
    weight: float                    # group lottery weight (≥ 1.0)
    reinsert: bool = False           # True for cascade reinserts (processed first)
    order_index: Optional[int] = None  # Existing Round-1 order_index (used in cascade)


@dataclass
class RoomIn:
    """Static room description."""
    hostel_id: str
    floor_no: int
    room_no: str
    capacity: int


# ---------------------------------------------------------------------------
# Output data-classes
# ---------------------------------------------------------------------------

@dataclass
class AllotmentOut:
    app_id: str
    room_id: str
    rank_obtained: int   # 1-based; len(choices)+1 for fallback room
    order_index: int     # position in the final sorted order


@dataclass
class WaitlistedOut:
    app_id: str
    order_index: int


@dataclass
class AllocationResult:
    order: List[str]                   # app_ids in processing order
    allotments: List[AllotmentOut]
    waitlisted: List[WaitlistedOut]


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

@dataclass
class Policy:
    fill_rule: str = "EXACT"          # "EXACT" | "AT_MOST"
    group_weight_policy: str = "MEAN" # "MEAN" | "MIN" | "MAX"
    c_init: int = 3
    c_min: int = 0
    c_max: int = 10
    rank_deltas: Dict[str, int] = field(default_factory=lambda: {
        "1": -3, "2": -2, "3": -1, "4": 0, "5": 0, "default": 1
    })
    unallotted_delta: int = 2
    forfeit_delta: int = -2
    late_cancel_delta: int = -1
    carry_over_factor: float = 0.5


# ---------------------------------------------------------------------------
# Deterministic HMAC-based uniform (0, 1)
# ---------------------------------------------------------------------------

def _hmac_uniform(seed: bytes, app_id: str) -> float:
    """Return a reproducible float in (0, 1) for the given seed + app_id."""
    mac = hmac.new(seed, app_id.encode(), hashlib.sha256).digest()
    # take first 8 bytes as an unsigned 64-bit integer
    val = struct.unpack(">Q", mac[:8])[0]
    # map to (0, 1) exclusive
    return (val + 1) / (2**64 + 1)


# ---------------------------------------------------------------------------
# Room-fit helpers
# ---------------------------------------------------------------------------

_ROOM_SPLIT_RE = re.compile(r"(\d+)")


def _room_sort_key(room_no: str) -> tuple:
    """Natural numeric sort key so '21' sorts before '201' and 'A-2' before 'A-10'."""
    parts = _ROOM_SPLIT_RE.split(str(room_no).strip().upper())
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts if p)


def _fits(room: RoomIn, group_size: int, fill_rule: str) -> bool:
    if fill_rule == FillRule.EXACT:
        return room.capacity == group_size
    return group_size <= room.capacity  # AT_MOST


def _resolve_choice(
    choice: Choice,
    group_size: int,
    rooms: Dict[str, RoomIn],
    free: Set[str],
    fill_rule: str,
) -> Optional[str]:
    if choice.kind == ChoiceKind.ROOM:
        r = rooms.get(choice.room_id)
        if r is None:
            return None
        return choice.room_id if choice.room_id in free and _fits(r, group_size, fill_rule) else None
    # FLOOR: take the lowest room_no (natural numeric sort) on the requested hostel+floor
    candidates = [
        rid for rid in free
        if rooms[rid].hostel_id == choice.hostel_id
        and rooms[rid].floor_no == choice.floor_no
        and _fits(rooms[rid], group_size, fill_rule)
    ]
    return min(candidates, key=lambda rid: (_room_sort_key(rooms[rid].room_no), rid)) if candidates else None


def _pick_fallback_room(
    app: AppIn,
    rooms: Dict[str, RoomIn],
    free: Set[str],
    fill_rule: str,
) -> Optional[str]:
    """
    Deterministic fallback: eligible rooms that fit, sorted by
    (spare_capacity, hostel_id, floor_no, natural(room_no)).  Return the first.
    """
    # Determine which hostel(s) the application belongs to.
    # We infer from choices; if no choices, accept any hostel.
    candidate_hostels: Optional[Set[str]] = None
    for ch in app.choices:
        if ch.hostel_id:
            if candidate_hostels is None:
                candidate_hostels = set()
            candidate_hostels.add(ch.hostel_id)
        elif ch.room_id and ch.room_id in rooms:
            if candidate_hostels is None:
                candidate_hostels = set()
            candidate_hostels.add(rooms[ch.room_id].hostel_id)

    eligible = [
        rid for rid in free
        if _fits(rooms[rid], app.group_size, fill_rule)
        and (candidate_hostels is None or rooms[rid].hostel_id in candidate_hostels)
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda rid: (
        rooms[rid].capacity - app.group_size,
        rooms[rid].hostel_id,
        rooms[rid].floor_no,
        _room_sort_key(rooms[rid].room_no),
        rid,
    ))
    return eligible[0]


# ---------------------------------------------------------------------------
# Main allocator entry-point
# ---------------------------------------------------------------------------

def _assign_ordered_apps(
    ordered_apps: List[AppIn],
    rooms: Dict[str, RoomIn],
    free_room_ids: Set[str],
    policy: Policy,
    *,
    preserve_order_index: bool = False,
) -> AllocationResult:
    """Assign rooms to pre-ordered applications cleanly (shared by MAIN and CASCADE)."""
    free: Set[str] = set(free_room_ids)
    allotments: List[AllotmentOut] = []
    waitlisted: List[WaitlistedOut] = []
    order: List[str] = []

    for index, a in enumerate(ordered_apps):
        out_index = a.order_index if (preserve_order_index and a.order_index is not None) else index
        order.append(a.id)
        room_id: Optional[str] = None
        rank: Optional[int] = None

        for rank_no, choice in enumerate(a.choices, start=1):
            room_id = _resolve_choice(choice, a.group_size, rooms, free, policy.fill_rule)
            if room_id:
                rank = rank_no
                break

        if room_id is None and a.fallback == Fallback.ANY_ELIGIBLE:
            room_id = _pick_fallback_room(a, rooms, free, policy.fill_rule)
            rank = len(a.choices) + 1 if room_id else None

        if room_id:
            free.discard(room_id)
            allotments.append(AllotmentOut(
                app_id=a.id,
                room_id=room_id,
                rank_obtained=rank,
                order_index=out_index,
            ))
        else:
            waitlisted.append(WaitlistedOut(app_id=a.id, order_index=out_index))

    return AllocationResult(order=order, allotments=allotments, waitlisted=waitlisted)


def assign_in_order(
    ordered_apps: List[AppIn],
    rooms: Dict[str, RoomIn],
    free_room_ids: Set[str],
    policy: Policy,
) -> AllocationResult:
    """
    Cascade assignment helper: skips Efraimidis-Spirakis random key recomputation
    and processes pre-sorted applications in (not reinsert, order_index) order.
    """
    sorted_apps = sorted(
        ordered_apps,
        key=lambda a: (not a.reinsert, a.order_index if a.order_index is not None else 10**9, a.id),
    )
    return _assign_ordered_apps(
        sorted_apps, rooms, free_room_ids, policy, preserve_order_index=True
    )


def allocate(
    applications: List[AppIn],
    rooms: Dict[str, RoomIn],
    free_room_ids: Set[str],
    seed: bytes,
    policy: Policy,
) -> AllocationResult:
    """
    Deterministic weighted-RSD allocation.

    Parameters
    ----------
    applications : list of AppIn
    rooms        : dict mapping room_id -> RoomIn (all rooms, not just free ones)
    free_room_ids: set of room_ids currently AVAILABLE
    seed         : bytes used for reproducible HMAC-based ordering
    policy       : Policy instance controlling fill_rule etc.

    Returns
    -------
    AllocationResult with order, allotments, and waitlisted lists.
    """
    # Build (sort_key_tuple, app) pairs
    keyed: List[tuple] = []
    for a in applications:
        u = _hmac_uniform(seed, a.id)
        # Efraimidis-Spirakis: ln(u)/weight, sort descending → negate for ascending sort
        key = math.log(u) / max(a.weight, 1e-9)
        # Sort order: reinserts first (False < True when negated), then tier asc, then key desc (negate)
        keyed.append((not a.reinsert, a.tier, -key, a.id, a))

    # Deterministic stable sort; ties broken by application id (string lex)
    keyed.sort(key=lambda t: t[:4])
    ordered_apps = [t[4] for t in keyed]

    return _assign_ordered_apps(ordered_apps, rooms, free_room_ids, policy)


# ---------------------------------------------------------------------------
# Credit helpers (pure, used by simulator and settlement service)
# ---------------------------------------------------------------------------

def compute_weight(member_credits: List[int], group_weight_policy: str = "MEAN") -> float:
    """
    Convert a list of member credit values to a group lottery weight.
    weight = f(1 + credits_i) according to group_weight_policy.
    """
    weights = [1 + c for c in member_credits]
    if group_weight_policy == "MIN":
        return float(min(weights))
    if group_weight_policy == "MAX":
        return float(max(weights))
    # MEAN (default)
    return float(sum(weights)) / len(weights)


def settle_delta(rank_obtained: Optional[int], n_choices: int, outcome: str, policy: Policy) -> int:
    """
    Return the credit delta for a single member based on their cycle outcome.

    Parameters
    ----------
    rank_obtained : 1-based rank if allotted, None if unallotted/forfeited
    n_choices     : number of ranked choices the group submitted
    outcome       : "CONFIRMED" | "FORFEITED" | "UNALLOTTED" | "LATE_CANCEL"
    policy        : Policy instance
    """
    if outcome == "UNALLOTTED":
        return policy.unallotted_delta
    if outcome == "FORFEITED":
        return policy.forfeit_delta
    if outcome == "LATE_CANCEL":
        return policy.late_cancel_delta
    if outcome == "CONFIRMED" and rank_obtained is not None:
        # Fallback rooms (rank_obtained > n_choices) → default delta
        if rank_obtained > n_choices:
            return policy.rank_deltas.get("default", 1)
        return policy.rank_deltas.get(str(rank_obtained), policy.rank_deltas.get("default", 1))
    return 0


def apply_carry_over(credits: int, c_init: int, carry_over_factor: float) -> int:
    """
    Fade credits toward C_INIT between cycles:
      new_credits = C_INIT + round((credits - C_INIT) * carry_over_factor)
    """
    return c_init + round((credits - c_init) * carry_over_factor)


def clamp_credits(credits: int, c_min: int, c_max: int) -> int:
    return max(c_min, min(c_max, credits))


# ---------------------------------------------------------------------------
# Pure top-level entry-point (used by tests and verify service)
# ---------------------------------------------------------------------------

def run_allocation_pure(
    apps: list[dict],
    rooms: list[dict],
    seed_str: str,
) -> list[dict]:
    """
    Stateless, pure allocation suitable for unit tests and verification.

    Parameters
    ----------
    apps : list of dicts with keys:
        group_id  : str   (used as the application id)
        choices   : list[str]   (room_ids, in preference order)
        weight    : float
        tier      : int   (optional, default 1)
        group_size: int   (optional, default 1)
        fallback  : str   (optional, default "ANY_ELIGIBLE")

    rooms : list of dicts with keys:
        room_id   : str
        hostel_id : str
        floor_no  : int
        room_no   : str
        capacity  : int

    seed_str : str — encoded to UTF-8 bytes and used as the HMAC seed.

    Returns
    -------
    list of dicts: {"group_id": str, "room_id": str | None, "order_index": int}
    """
    seed: bytes = seed_str.encode("utf-8")
    policy = Policy()

    rooms_dict: Dict[str, RoomIn] = {}
    for r in rooms:
        rid = str(r["room_id"])
        rooms_dict[rid] = RoomIn(
            hostel_id=str(r.get("hostel_id", "")),
            floor_no=int(r.get("floor_no", 0)),
            room_no=str(r.get("room_no", rid)),
            capacity=int(r.get("capacity", 1)),
        )
    free_room_ids: Set[str] = set(rooms_dict.keys())

    apps_in: List[AppIn] = []
    for a in apps:
        gid = str(a["group_id"])
        raw_choices = a.get("choices", [])
        choices = [Choice(kind="ROOM", room_id=str(rid)) for rid in raw_choices]
        apps_in.append(AppIn(
            id=gid,
            tier=int(a.get("tier", 1)),
            group_size=int(a.get("group_size", 1)),
            choices=choices,
            fallback=str(a.get("fallback", "ANY_ELIGIBLE")),
            weight=float(a.get("weight", 1.0)),
            reinsert=bool(a.get("reinsert", False)),
        ))

    result = allocate(apps_in, rooms_dict, free_room_ids, seed, policy)

    output: list[dict] = []
    allotted_ids: set[str] = set()

    for a_out in result.allotments:
        output.append({
            "group_id": a_out.app_id,
            "room_id": a_out.room_id,
            "order_index": a_out.order_index,
        })
        allotted_ids.add(a_out.app_id)

    for w_out in result.waitlisted:
        output.append({
            "group_id": w_out.app_id,
            "room_id": None,
            "order_index": w_out.order_index,
        })

    return output
