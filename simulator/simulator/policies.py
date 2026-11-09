"""Allocation weight policies aligned with backend fairness engine."""

from __future__ import annotations

from typing import Dict, Optional

from app.fairness.engine import group_weight
from .generators import SimGroup, SimStudent


def random_policy(
    group: SimGroup, students: Dict[str, SimStudent], arrival_order: Optional[Dict[str, int]] = None
) -> float:
    return 1.0


def credit_weighted_policy(
    group: SimGroup, students: Dict[str, SimStudent], arrival_order: Optional[Dict[str, int]] = None
) -> float:
    """FairNest canonical policy: MEAN of (1 + member credits)."""
    credits = [students[sid].credit_balance for sid in group.member_ids]
    return group_weight(credits, "MEAN")


def min_credit_policy(
    group: SimGroup, students: Dict[str, SimStudent], arrival_order: Optional[Dict[str, int]] = None
) -> float:
    """MIN of (1 + member credits)."""
    credits = [students[sid].credit_balance for sid in group.member_ids]
    return group_weight(credits, "MIN")


def max_credit_policy(
    group: SimGroup, students: Dict[str, SimStudent], arrival_order: Optional[Dict[str, int]] = None
) -> float:
    """MAX of (1 + member credits)."""
    credits = [students[sid].credit_balance for sid in group.member_ids]
    return group_weight(credits, "MAX")


def static_priority_policy(
    group: SimGroup, students: Dict[str, SimStudent], arrival_order: Optional[Dict[str, int]] = None
) -> float:
    """Seniority-based static weight (sum/mean of academic year)."""
    years = [students[sid].year for sid in group.member_ids]
    return float(1 + sum(years) / max(len(years), 1))


def fcfs_policy(
    group: SimGroup, students: Dict[str, SimStudent], arrival_order: Optional[Dict[str, int]] = None
) -> float:
    """First-come-first-served inverse arrival weight."""
    pos = arrival_order.get(group.group_id, 0) if arrival_order else 0
    return 1.0 / (pos + 1)


POLICIES = {
    "random": random_policy,
    "credit_weighted": credit_weighted_policy,
    "min_credit": min_credit_policy,
    "max_credit": max_credit_policy,
    "static_priority": static_priority_policy,
    "fcfs": fcfs_policy,
}
