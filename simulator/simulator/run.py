"""CLI entry point for the FairNest simulator (matches Makefile and custom CLI args)."""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulator.experiments import run_all_experiments
from simulator.metrics import compute_all_metrics
from simulator.plots import (
    plot_confirm_rate_by_policy,
    plot_credit_bands,
    plot_jain_by_policy,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="FairNest Policy Simulator")
    parser.add_argument("--config", default=None, help="Path to base config YAML (e.g. configs/base.yaml)")
    parser.add_argument("--policy", default=None, help="Single policy to run (default: all S1-S8 scenarios)")
    parser.add_argument("--cycles", type=int, default=None, help="Number of cycles per run")
    parser.add_argument("--seeds", type=int, default=None, help="Number of random seeds per scenario")
    parser.add_argument("--out", default=None, help="Output directory for CSV, summary JSON, and plots")
    parser.add_argument("--output", default=None, help="Explicit output CSV file path (legacy alias)")
    parser.add_argument("--plots-dir", default=None, help="Directory to save plots (legacy alias)")
    parser.add_argument("--no-plots", action="store_true", help="Skip plot generation")
    args = parser.parse_args()

    out_dir = args.out or args.plots_dir or "results"
    os.makedirs(out_dir, exist_ok=True)
    csv_path = args.output or os.path.join(out_dir, "results.csv")
    plots_dir = args.plots_dir or out_dir

    print("Running FairNest policy simulation...")
    results = run_all_experiments(
        output_csv=csv_path,
        config_path=args.config,
        cycles_override=args.cycles,
        seeds_override=args.seeds,
        policy_filter=args.policy,
    )

    overall = compute_all_metrics(results)
    by_scenario = {}
    for scen in sorted({r["scenario"] for r in results}):
        scen_rows = [r for r in results if r["scenario"] == scen]
        by_scenario[scen] = compute_all_metrics(scen_rows)

    summary_path = os.path.join(out_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({"overall": overall, "scenarios": by_scenario}, f, indent=2)

    print("\n=== Scenario Summary ===")
    for scen, m in by_scenario.items():
        print(
            f"  {scen:<22} | alloc={m['mean_allocation_rate']:.3f} "
            f"| jain={m['mean_jain_index']:.4f} "
            f"| top1={m['mean_top_1_rate']:.3f} "
            f"| max_streak={m['max_losing_streak']}"
        )

    print("\n=== Overall Metrics ===")
    for k, v in overall.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    if not args.no_plots:
        os.makedirs(plots_dir, exist_ok=True)
        p1 = plot_jain_by_policy(results, plots_dir)
        p2 = plot_confirm_rate_by_policy(results, plots_dir)
        p3 = plot_credit_bands(results, plots_dir)
        saved = [p for p in (p1, p2, p3) if p]
        if saved:
            print(f"\nPlots saved: {', '.join(saved)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
