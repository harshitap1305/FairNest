"""Fairness engine: policy, weights, settlement, metrics."""

from __future__ import annotations

from typing import Optional


# ─────────────────────────── policy ──────────────────────────────────────────

DEFAULT_POLICY: dict = {
    "c_init": 3,
    "c_min": 0,
    "c_max": 10,
    "weight_formula": "1 + credits",
    "group_weight_policy": "MEAN",
    "fill_rule": "EXACT",
    "rank_deltas": {"1": -3, "2": -2, "3": -1, "4": 0, "5": 0, "default": 1},
    "unallotted_delta": 2,
    "forfeit_delta": -2,
    "late_cancel_delta": -1,
    "carry_over_factor": 0.5,
}


def get_policy(cycle_policy: dict) -> dict:
    """Merge cycle-specific policy over defaults."""
    merged = {**DEFAULT_POLICY, **cycle_policy}
    # Ensure rank_deltas is merged too
    if "rank_deltas" in cycle_policy:
        merged["rank_deltas"] = {**DEFAULT_POLICY["rank_deltas"], **cycle_policy["rank_deltas"]}
    return merged


# ─────────────────────────── weights ─────────────────────────────────────────

def member_weight(credits: int) -> float:
    return 1.0 + credits


def group_weight(member_credits: list[int], policy: str = "MEAN") -> float:
    """Convert member credits to a group lottery weight."""
    if not member_credits:
        return 1.0
    weights = [member_weight(c) for c in member_credits]
    if policy == "MIN":
        return float(min(weights))
    if policy == "MAX":
        return float(max(weights))
    return float(sum(weights)) / len(weights)   # MEAN


# ─────────────────────────── settlement ──────────────────────────────────────

SETTLEMENT_EVENT_MAP = {
    "CONFIRMED":      "SETTLEMENT_CONFIRMED",
    "UNALLOTTED":     "SETTLEMENT_UNALLOTTED",
    "FORFEITED":      "SETTLEMENT_FORFEITED",
    "LATE_CANCELLED": "SETTLEMENT_LATE_CANCELLED",
    "REVOKED":        "SETTLEMENT_REVOKED",
}


def delta_for_outcome(policy: dict, outcome: str,
                      rank_obtained: Optional[int] = None,
                      n_choices: int = 0) -> tuple[int, str]:
    """
    Return (delta, event_type) for a member's settlement.

    outcome : "CONFIRMED" | "UNALLOTTED" | "FORFEITED" | "LATE_CANCELLED" | "REVOKED"
    """
    event_type = SETTLEMENT_EVENT_MAP.get(outcome, "SETTLEMENT_REVOKED")

    if outcome == "UNALLOTTED":
        return policy["unallotted_delta"], event_type

    if outcome == "FORFEITED":
        return policy["forfeit_delta"], event_type

    if outcome == "LATE_CANCELLED":
        return policy["late_cancel_delta"], event_type

    if outcome == "REVOKED":
        return 0, event_type

    if outcome == "CONFIRMED" and rank_obtained is not None:
        rank_deltas: dict = policy.get("rank_deltas", DEFAULT_POLICY["rank_deltas"])
        # Fallback rooms: rank_obtained > n_choices → use "default"
        if rank_obtained > n_choices:
            return rank_deltas.get("default", 1), event_type
        return rank_deltas.get(str(rank_obtained), rank_deltas.get("default", 1)), event_type

    return 0, event_type


def settle_members(members_with_outcomes: list[dict], policy: dict) -> list[dict]:
    """
    Compute settlement rows for a list of member outcome dicts.

    Each input dict: {user_id, outcome, rank_obtained (optional), n_choices (optional)}
    Returns list of {user_id, delta, event_type, reason}
    """
    rows = []
    for m in members_with_outcomes:
        delta, event_type = delta_for_outcome(
            policy,
            outcome=m["outcome"],
            rank_obtained=m.get("rank_obtained"),
            n_choices=m.get("n_choices", 0),
        )
        rows.append({
            "user_id": m["user_id"],
            "delta": delta,
            "event_type": event_type,
            "reason": _settlement_reason(m["outcome"], m.get("rank_obtained"), delta),
        })
    return rows


def _settlement_reason(outcome: str, rank: Optional[int], delta: int) -> str:
    if outcome == "CONFIRMED":
        rank_str = f"rank {rank}" if rank else "fallback"
        sign = "+" if delta > 0 else ""
        return f"Confirmed ({rank_str}): credits {sign}{delta}"
    if outcome == "UNALLOTTED":
        return f"Not allotted: credits +{delta}"
    if outcome == "FORFEITED":
        return f"Allotment forfeited (declined or expired): credits {delta}"
    if outcome == "LATE_CANCELLED":
        return f"Late cancellation: credits {delta}"
    if outcome == "REVOKED":
        return "Allotment revoked by admin: no credit change"
    return ""


# ─────────────────────────── metrics ─────────────────────────────────────────

def jain_index(success_rates: list[float]) -> float:
    """Jain's fairness index. 1.0 = perfect equality."""
    if not success_rates:
        return 0.0
    n = len(success_rates)
    s = sum(success_rates)
    sq = sum(x * x for x in success_rates)
    return (s * s) / (n * sq) if sq > 0 else 1.0


def success_by_credit_band(student_history: list[dict]) -> dict[str, float]:
    """
    student_history: list of {credits_at_time, got_room (bool)}
    Returns {band_label: success_rate} for bands 0-2, 3-5, 6-10.
    """
    bands = {"0-2": [], "3-5": [], "6-10": []}
    for rec in student_history:
        c = rec.get("credits", 0)
        v = 1.0 if rec.get("got_room") else 0.0
        if c <= 2:
            bands["0-2"].append(v)
        elif c <= 5:
            bands["3-5"].append(v)
        else:
            bands["6-10"].append(v)
    return {k: (sum(v) / len(v) if v else 0.0) for k, v in bands.items()}


def average_rank(confirmed_allotments: list[dict]) -> float:
    ranks = [a["rank_obtained"] for a in confirmed_allotments
             if a.get("rank_obtained") is not None]
    return sum(ranks) / len(ranks) if ranks else 0.0


def top_k_rate(confirmed_allotments: list[dict], k: int = 1) -> float:
    total = len(confirmed_allotments)
    if total == 0:
        return 0.0
    top_k = sum(1 for a in confirmed_allotments if (a.get("rank_obtained") or 999) <= k)
    return top_k / total


def group_vs_solo_success(outcomes: list[dict]) -> dict[str, float]:
    """
    outcomes: list of {group_size, got_room (bool)}
    Returns {solo: rate, group: rate}
    """
    solo, grp = [], []
    for o in outcomes:
        v = 1.0 if o.get("got_room") else 0.0
        if o.get("group_size", 1) == 1:
            solo.append(v)
        else:
            grp.append(v)
    return {
        "solo": sum(solo) / len(solo) if solo else 0.0,
        "group": sum(grp) / len(grp) if grp else 0.0,
    }


def longest_losing_streak(student_history: list[bool]) -> int:
    """student_history: list of bool (got_room) ordered by cycle."""
    max_streak = current = 0
    for got in student_history:
        if not got:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


# ─────────────────────────── scalar credit helpers ───────────────────────────

def clamp_credit(value: float, cap: float) -> float:
    """Clamp *value* to the range [0.0, cap]."""
    return max(0.0, min(cap, value))


def settle(balance: float, delta: float, cap: float) -> float:  # noqa: F811
    """
    Apply *delta* to *balance* and clamp the result to [0, cap].

    This is the scalar form used by pure-function tests and simulators.
    The batch settlement helper (settle_members) handles full member rows.
    """
    return clamp_credit(balance + delta, cap)
