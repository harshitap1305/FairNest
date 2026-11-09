# ADR-0004: Efraimidis–Spirakis Weighted RSD & Bounded `[0, 10]` Credits

- **Status:** Accepted
- **Date:** 2026-11-09
- **Components:** [`allocator/core.py`](../../backend/app/allocator/core.py), [`fairness/engine.py`](../../backend/app/fairness/engine.py), [`experiments.py`](../../simulator/simulator/experiments.py)

---

## Context

Alternatives evaluated for allocating oversubscribed rooms:
- **First-Come-First-Served (FCFS):** Rewards network speed and bot scripting over fairness.
- **Unweighted Pure Random Lottery:** Treats repeatedly unallotted students the same as first-rank winners every term, producing long losing streaks.
- **Competitive Credit Bidding (Boston/First-Price Mechanism):** Forces students to strategize how many points to wager on a room; miscalculating loses both the room and priority.
- **Unbounded Credit Accumulation:** Lets high-credit veterans permanently crowd out new cohorts ("rich-get-richer").

## Decision

1. **Intra-Cycle Weighted Random Serial Dictatorship (RSD):** Order each cycle using **Efraimidis–Spirakis** keys $\ln(u_a) / w_a$ driven by deterministic `HMAC-SHA256(seed, app_id)` ($u_a \in (0, 1)$), preceded strictly by Tier-0 verified accessibility groups (`tier = 0`). Rank preferences are **never** inspected during ordering, preserving single-cycle strategy-proofness.
2. **Bounded Fairness Credits (`[0, 10]`):** Initialize new accounts at `C_INIT = 3` and convert credits to weight via `1 + credits` (aggregated across group members by `MEAN` by default, or `MIN`/`MAX`), preventing zero weights while capping advantage ratio.
3. **Outcome-Adjusted Settlement & Inter-Cycle Damping:** Adjust balances post-cycle (`rank 1: -3`, `rank 2: -2`, `rank 3: -1`, `rank 4/5: 0`, fallback: `+1`, `UNALLOTTED: +2`, `FORFEITED: -2`, `LATE_CANCELLED: -1`, `REVOKED: 0`), with inter-cycle damping `C_INIT + round((credits - C_INIT) * 0.5)` supported in pure core and the offline simulator.
4. **No-Re-Randomization Cascade:** Released rooms flow to waitlisted groups strictly in original Round-1 `(not reinsert, order_index)` order (`assign_in_order`).

## Consequences

- **Positive:** Truthful ranking is dominant within each cycle; unallotted students climb rapidly out of losing streaks (`+2` per term); cascade behavior is completely transparent and free of mid-cycle lottery arbitrage; validated empirically across `S1`–`S8` in `simulator/`.
- **Trade-off:** Requires persisting `credit_snapshot` and immutable Round-1 `order_index` on applications so mid-cycle revokes or future cycles do not corrupt priority trails.

---

**Related:** [Unique Design Aspects & Algorithms](../uniqueness-and-algorithms.md) · [Simulator & Fairness Analysis](../simulator-and-fairness-analysis.md)
