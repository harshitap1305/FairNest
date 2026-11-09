"""Generate matplotlib charts from simulation results."""

from __future__ import annotations

import os
from typing import List

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def plot_jain_by_policy(results: List[dict], output_dir: str = ".") -> str:
    """Bar chart: Mean Jain Fairness Index per policy."""
    if not HAS_MATPLOTLIB or not results:
        return ""
    policies = sorted({r["policy"] for r in results})
    jain_vals = []
    for p in policies:
        vals = [float(r["jain_index"]) for r in results if r["policy"] == p]
        jain_vals.append(sum(vals) / len(vals) if vals else 0.0)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(policies, jain_vals, color="#1565C0")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Mean Jain Fairness Index (Multi-Cycle Student Success)")
    ax.set_title("Jain Fairness Index by Allocation Policy")
    ax.axhline(1.0, color="green", linestyle="--", label="Perfect Fairness")
    ax.legend()
    path = os.path.join(output_dir, "jain_by_policy.png")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_confirm_rate_by_policy(results: List[dict], output_dir: str = ".") -> str:
    """Bar chart: Confirmation rate per policy."""
    if not HAS_MATPLOTLIB or not results:
        return ""
    policies = sorted({r["policy"] for r in results})
    rates = []
    for p in policies:
        vals = [float(r["confirm_rate"]) for r in results if r["policy"] == p]
        rates.append(sum(vals) / len(vals) if vals else 0.0)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(policies, rates, color="#E65100")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Mean Confirmation Rate")
    ax.set_title("Confirmation Rate by Allocation Policy")
    path = os.path.join(output_dir, "confirm_by_policy.png")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_credit_bands(results: List[dict], output_dir: str = ".") -> str:
    """Bar chart: Credit-weighted success rate across canonical credit bands (0-2, 3-5, 6-10)."""
    if not HAS_MATPLOTLIB or not results:
        return ""
    cw = [r for r in results if r["policy"] == "credit_weighted"] or results
    bands = ["0-2", "3-5", "6-10"]
    vals = [
        sum(float(r.get("band_0_2", 0.0)) for r in cw) / len(cw),
        sum(float(r.get("band_3_5", 0.0)) for r in cw) / len(cw),
        sum(float(r.get("band_6_10", 0.0)) for r in cw) / len(cw),
    ]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(bands, vals, color=["#78909C", "#2E7D32", "#1565C0"])
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Credit Band (Canonical [0..10])")
    ax.set_ylabel("Cycle Success Rate")
    ax.set_title("Room Allotment Success Rate by Credit Band")
    path = os.path.join(output_dir, "credit_bands.png")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path
