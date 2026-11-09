# Policy Simulator & Fairness Analysis

FairNest includes an offline **Monte Carlo policy simulation suite** (`simulator/`) built to empirically validate fairness, efficiency, and long-horizon starvation resistance across allocation mechanisms before deploying parameter tuning into production.

> [!IMPORTANT]
> **Zero Algorithmic Drift:** [`simulator/engine.py`](../simulator/simulator/engine.py) directly imports the production backend packages [`app.allocator.core`](../backend/app/allocator/core.py) (`allocate`, `assign_in_order`, `apply_carry_over`, `clamp_credits`) and [`app.fairness.engine`](../backend/app/fairness/engine.py) (`DEFAULT_POLICY`, `delta_for_outcome`, `group_weight`, `jain_index`, `success_by_credit_band`, `average_rank`, `top_k_rate`, `group_vs_solo_success`, `longest_losing_streak`). Experiment findings therefore measure the exact production allocator and settlement logic.

---

## 1. Architecture of `simulator/`

| Module | Responsibility | Link |
|---|---|---|
| **CLI Runner** | Parses `--config`, `--policy`, `--cycles`, `--seeds`, `--out`, `--output`, `--plots-dir`, `--no-plots`; emits `results.csv`, `summary.json`, and 3 PNG charts. | [`run.py`](../simulator/simulator/run.py) |
| **Experiments Matrix** | Orchestrates scenarios `S1`–`S8` across YAML configs and RNG seeds. | [`experiments.py`](../simulator/simulator/experiments.py) |
| **Simulation Engine** | Multi-cycle orchestrator (`simulate_multi_cycle`) running Round 1, up to `max_cascade_rounds` (default `3`), outcome settlement, and inter-cycle credit carry-over. | [`engine.py`](../simulator/simulator/engine.py) |
| **Policies** | Weight functions for `random`, `credit_weighted` (MEAN), `min_credit`, `max_credit`, `static_priority`, and `fcfs`. | [`policies.py`](../simulator/simulator/policies.py) |
| **Synthetic Cohort Generators** | Generates students across 4 synthetic hostels (`H_M1, H_M2, H_F1, H_F2`), mixed-capacity rooms, roommate groups, and ranked choices + fallback choices. | [`generators.py`](../simulator/simulator/generators.py) |
| **Zero-Payment Confirmation Model** | Models member accept/decline (`CONFIRMED` iff **all** members draw `< p_confirm`; zero payment checks). | [`behaviour.py`](../simulator/simulator/behaviour.py) |
| **Metrics & Charts** | Wraps canonical fairness metrics and renders Matplotlib comparisons (`jain_by_policy.png`, `confirm_by_policy.png`, `credit_bands.png`). | [`metrics.py`](../simulator/simulator/metrics.py), [`plots.py`](../simulator/simulator/plots.py) |

---

## 2. Configuration Presets (`simulator/configs/`)

[`base.yaml`](../simulator/configs/base.yaml) defines baseline scarcity (**200 competing students for 100 beds**, 2:1 oversubscription), and scenario overrides perturb specific stresses:

| Parameter | `base.yaml` | `high_groups.yaml` | `low_confirm.yaml` | `skewed.yaml` |
|---|---|---|---|---|
| `n_students` | `200` | *(inherited: 200)* | *(inherited: 200)* | *(inherited: 200)* |
| `n_beds` | `100` | *(inherited: 100)* | *(inherited: 100)* | *(inherited: 100)* |
| `cycles` | `20` | *(inherited: 20)* | *(inherited: 20)* | *(inherited: 20)* |
| `seeds` | `30` | *(inherited: 30)* | *(inherited: 30)* | *(inherited: 30)* |
| `p_confirm` | `0.85` | `0.85` | **`0.55`** | **`0.70`** |
| `p_group` | `0.40` | **`0.75`** | `0.40` | `0.40` |
| `max_group_size` | `4` | `4` | `4` | `4` |
| `p_tier0` | `0.03` | `0.03` | `0.03` | `0.03` |
| `skew_credits` | `false` | `false` | `false` | **`true`** |
| `carry_over_factor` | `0.5` | `0.5` | `0.5` | `0.5` |
| `fill_rule` | `EXACT` | `EXACT` | `EXACT` | `EXACT` |
| `group_weight_policy` | `MEAN` | `MEAN` | `MEAN` | `MEAN` |

---

## 3. Policies Evaluated (`S1`–`S8` Benchmark Suite)

[`experiments.py`](../simulator/simulator/experiments.py) runs **8 standardized scenarios** (`SCENARIOS`):

| Scenario | Policy | Config Preset | What It Tests |
|---|---|---|---|
| `S1_baseline_random` | `random` | `base` | Unweighted RSD baseline (`weight = 1.0`, Tier-0 disabled in simulator to test pure lottery). |
| `S2_credit_weighted` | `credit_weighted` | `base` | **Canonical FairNest mechanism:** `MEAN(1 + credits)` + Tier-0 priority + bounded credits + damping. |
| `S3_min_credit` | `min_credit` | `base` | Evaluates conservative roommate penalty (`MIN(1 + credits)` so low-credit member caps group weight). |
| `S4_max_credit` | `max_credit` | `base` | Evaluates high-credit anchor effect (`MAX(1 + credits)`), testing credit-boosting behavior. |
| `S5_fcfs` | `fcfs` | `base` | Deterministic shuffled arrival order executed via `assign_in_order`. |
| `S6_high_groups_credit` | `credit_weighted` | `high_groups` | Stress-tests `75%` multi-student group formation against `EXACT` room-size packing. |
| `S7_skewed_credit` | `credit_weighted` | `skewed` | Starts students with highly skewed credit balances + lower confirm rate (`0.70`) to measure convergence/recovery. |
| `S8_low_confirm` | `credit_weighted` | `low_confirm` | Stress-tests `p_confirm = 0.55` churn to verify cascade efficiency (`max_cascade_rounds = 3`) & forfeit credit feedback. |

Additional policy `static_priority` (`1 + mean(year)`) is implemented in [`policies.py`](../simulator/simulator/policies.py#L41-L46) for `--policy static_priority` comparative experiments.

---

## 4. Multi-Cycle Simulation Loop Mechanics

For each `(scenario, seed)`:
1. **Generate Persistent Student Cohort:** `n_students` start at `c_init=3` (or polarized distribution when `skew_credits=true`), with `p_tier0=0.03` disability/accessibility rate.
2. **Repeat Across `cycles` (e.g., 20 sequential terms):**
   - Form solo/multi-person groups (`p_group`, `max_group_size`).
   - Run **Round 1** via `core_allocate` (or `assign_in_order` for `fcfs`) using SHA-256 derived seed bytes `f"{cycle_id}:{seed}"`.
   - Simulate **up to 3 cascade rounds** (`round_no = 1..4`): every group in `current_holds` confirms iff **all** members draw `< p_confirm` in `simulate_confirmations`; forfeited rooms return to `free_rooms`, and `assign_in_order` fills waitlisted groups strictly in immutable Round-1 order.
   - Settle student credits using production `delta_for_outcome`: `rank_deltas` on `CONFIRMED`, `+2` on `UNALLOTTED`, `-2` on `FORFEITED`, clamped to `[0, 10]`.
   - Between cycles (`c_idx < n_cycles - 1`), apply inter-cycle damping (`apply_carry_over(..., 0.5)`).

---

## 5. Evaluation Metrics & Output Artifacts

[`metrics.py`](../simulator/simulator/metrics.py) + [`engine.py`](../simulator/simulator/engine.py) compute:
- **Allocation & Confirmation Rate:** Fraction of groups securing a `CONFIRMED` room (`allocation_rate`) and conversion efficiency of offered holds (`confirm_rate`).
- **Jain's Fairness Index (`jain_index`):** Computed over every student's longitudinal win rate $r_i \in [0, 1]$ across cycles:
  $$J = \frac{\left(\sum_{i=1}^n r_i\right)^2}{n \sum_{i=1}^n r_i^2} \in \left[\frac{1}{n},\, 1\right]$$
  Values closer to `1.0` indicate more equal lifetime access across students under 2:1 oversubscription.
- **Efficiency & Preference Satisfaction:** `average_rank` and `top_1_rate` over confirmed allotments.
- **Starvation Protection:** `max_losing_streak` (worst consecutive-cycle shutout experienced by any student).
- **Equity Stratification (`success_by_credit_band`):** Win rate broken down across low (`0-2`), medium (`3-5`), and high (`6-10`) prior credit bands, confirming monotonic credit lift.
- **Structural Bias Check (`group_vs_solo_success`):** Compares solo (`size == 1`) vs. group (`size > 1`) allotment rates under `EXACT` fit.

---

## 6. Running Simulator Experiments & Tests

### Execute Full Benchmark Suite (from `Makefile`)

```bash
make sim
# Equivalent to:
cd simulator && PYTHONPATH=../backend:. python -m simulator.run --config configs/base.yaml --cycles 20 --seeds 30 --out results/s1
```

### Custom Fast Run / Single Policy

```bash
cd simulator
PYTHONPATH=../backend:. python -m simulator.run --policy credit_weighted --cycles 10 --seeds 5 --out results/quick --no-plots
```

Generated outputs in `--out`:
- `results.csv` — One row per `(scenario, seed)` run with all metrics.
- `summary.json` — Overall and per-scenario aggregated JSON report.
- `jain_by_policy.png`, `confirm_by_policy.png`, `credit_bands.png` — Bar/grouped comparison plots (when Matplotlib is installed and `--no-plots` is omitted).

### Simulator Determinism Test Suite

[`simulator/tests/test_determinism.py`](../simulator/tests/test_determinism.py) verifies reproducible single-cycle/multi-cycle runs, zero dependency on payment fields, and invariant satisfaction (`6 tests`):

```bash
cd simulator && pytest tests/test_determinism.py
```

---

**Related:** [Unique Design Aspects & Algorithms](uniqueness-and-algorithms.md) · [ADR-0004: Weighted RSD & Bounded Credits](adr/0004-weighted-rsd-and-bounded-credits.md) · [Operations & Runbook](operations-testing-and-runbook.md)
