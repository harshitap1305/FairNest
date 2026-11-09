"""Fairness metrics wrapping backend.app.fairness.engine directly."""

from __future__ import annotations

from typing import Dict, List

from app.fairness.engine import (
    average_rank,
    group_vs_solo_success,
    jain_index,
    longest_losing_streak,
    success_by_credit_band,
    top_k_rate,
)

__all__ = [
    "average_rank",
    "compute_all_metrics",
    "group_vs_solo_success",
    "jain_index",
    "longest_losing_streak",
    "success_by_credit_band",
    "top_k_rate",
]


def compute_all_metrics(run_results: List[dict]) -> Dict[str, float | int]:
    """Aggregate fairness and efficiency metrics across simulation runs."""
    if not run_results:
        return {}
    n = len(run_results)
    allocation_rates = [float(r.get("allocation_rate", 0.0)) for r in run_results]
    confirm_rates = [float(r.get("confirm_rate", 0.0)) for r in run_results]
    jains = [float(r.get("jain_index", r.get("allocation_rate", 0.0))) for r in run_results]
    avg_ranks = [float(r.get("average_rank", 0.0)) for r in run_results if r.get("average_rank", 0.0) > 0]
    top1s = [float(r.get("top_1_rate", 0.0)) for r in run_results]
    streaks = [int(r.get("max_losing_streak", 0)) for r in run_results]

    return {
        "n_runs": n,
        "mean_allocation_rate": round(sum(allocation_rates) / n, 4),
        "mean_confirm_rate": round(sum(confirm_rates) / n, 4),
        "mean_jain_index": round(sum(jains) / n, 4),
        "mean_average_rank": round(sum(avg_ranks) / len(avg_ranks), 4) if avg_ranks else 0.0,
        "mean_top_1_rate": round(sum(top1s) / n, 4),
        "max_losing_streak": max(streaks) if streaks else 0,
    }
