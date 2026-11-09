"""Run S1-S8 experiments across allocation policies and seeds, export CSV."""

from __future__ import annotations

import csv
import os
from typing import Dict, List, Optional

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

from .engine import simulate_multi_cycle

SCENARIOS: Dict[str, dict] = {
    "S1_baseline_random": {"policy": "random"},
    "S2_credit_weighted": {"policy": "credit_weighted"},
    "S3_min_credit": {"policy": "min_credit"},
    "S4_max_credit": {"policy": "max_credit"},
    "S5_fcfs": {"policy": "fcfs"},
    "S6_high_groups_credit": {"policy": "credit_weighted", "config": "high_groups"},
    "S7_skewed_credit": {"policy": "credit_weighted", "config": "skewed"},
    "S8_low_confirm": {"policy": "credit_weighted", "config": "low_confirm"},
}


def _parse_simple_yaml(path: str) -> dict:
    """Fallback scalar YAML parser when PyYAML is not installed."""
    out: dict = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            k, v = [p.strip() for p in line.split(":", 1)]
            low = v.lower()
            if low in ("true", "false"):
                out[k] = low == "true"
            else:
                try:
                    out[k] = float(v) if "." in v else int(v)
                except ValueError:
                    out[k] = v.strip("\"'")
    return out


def _read_yaml_file(path: str) -> dict:
    if yaml is not None:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return _parse_simple_yaml(path)


def load_config(name_or_path: str = "base") -> dict:
    config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "configs"))
    base_path = os.path.join(config_dir, "base.yaml")
    config = _read_yaml_file(base_path)

    if name_or_path != "base":
        if os.path.exists(name_or_path):
            config.update(_read_yaml_file(name_or_path))
        else:
            override_path = os.path.join(config_dir, f"{name_or_path}.yaml")
            if os.path.exists(override_path):
                config.update(_read_yaml_file(override_path))
    return config


def run_all_experiments(
    output_csv: Optional[str] = "results.csv",
    *,
    config_path: Optional[str] = None,
    cycles_override: Optional[int] = None,
    seeds_override: Optional[int] = None,
    policy_filter: Optional[str] = None,
) -> List[dict]:
    all_results: List[dict] = []

    if policy_filter:
        scenarios = {f"custom_{policy_filter}": {"policy": policy_filter}}
    else:
        scenarios = SCENARIOS

    for scenario_name, scenario in scenarios.items():
        cfg = load_config(config_path or scenario.get("config", "base"))
        if scenario.get("config") and config_path:
            # Also apply scenario-specific overrides on top of custom base config
            cfg = {**cfg, **load_config(scenario["config"])}
            # Preserve CLI base cycles/seeds if passed
        if cycles_override is not None:
            cfg["cycles"] = cycles_override
        if seeds_override is not None:
            cfg["seeds"] = seeds_override

        policy = scenario["policy"]
        n_seeds = int(cfg.get("seeds", 10))

        for seed in range(n_seeds):
            res = simulate_multi_cycle(cfg, policy, seed)
            res["scenario"] = scenario_name
            all_results.append(res)

    if output_csv and all_results:
        os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_results[0].keys()))
            writer.writeheader()
            writer.writerows(all_results)
        print(f"Results written to {output_csv}")

    return all_results
