"""Unit tests for fairness engine: canonical [0..10] policy, weights, settlement, carry-over."""

from __future__ import annotations

from app.allocator.core import apply_carry_over, clamp_credits
from app.fairness.engine import (
    DEFAULT_POLICY,
    delta_for_outcome,
    group_vs_solo_success,
    group_weight,
    jain_index,
    longest_losing_streak,
    settle_members,
    success_by_credit_band,
)


def test_jain_index_edge_cases():
    assert abs(jain_index([1.0, 1.0, 1.0, 1.0]) - 1.0) < 1e-6
    assert abs(jain_index([1.0] + [0.0] * 9) - 0.1) < 1e-6
    assert jain_index([]) == 0.0
    assert abs(jain_index([42.0]) - 1.0) < 1e-6
    assert jain_index([0.0, 0.0, 0.0]) in (0.0, 1.0)


def test_canonical_credit_bounds_and_carry_over():
    assert DEFAULT_POLICY["c_init"] == 3
    assert DEFAULT_POLICY["c_min"] == 0
    assert DEFAULT_POLICY["c_max"] == 10

    assert clamp_credits(15, 0, 10) == 10
    assert clamp_credits(-4, 0, 10) == 0
    assert clamp_credits(6, 0, 10) == 6

    # Carry-over fades toward C_INIT=3 by factor 0.5
    assert apply_carry_over(9, 3, 0.5) == 6
    assert apply_carry_over(3, 3, 0.5) == 3
    assert apply_carry_over(1, 3, 0.5) == 2


def test_group_weight_variants():
    assert group_weight([1, 5], "MEAN") == 4.0  # mean of (2, 6)
    assert group_weight([1, 5], "MIN") == 2.0
    assert group_weight([1, 5], "MAX") == 6.0
    assert group_weight([], "MEAN") == 1.0


def test_settlement_deltas_no_payment():
    p = DEFAULT_POLICY
    assert delta_for_outcome(p, "CONFIRMED", rank_obtained=1, n_choices=5) == (-3, "SETTLEMENT_CONFIRMED")
    assert delta_for_outcome(p, "CONFIRMED", rank_obtained=2, n_choices=5) == (-2, "SETTLEMENT_CONFIRMED")
    assert delta_for_outcome(p, "CONFIRMED", rank_obtained=3, n_choices=5) == (-1, "SETTLEMENT_CONFIRMED")
    assert delta_for_outcome(p, "CONFIRMED", rank_obtained=4, n_choices=5) == (0, "SETTLEMENT_CONFIRMED")
    assert delta_for_outcome(p, "CONFIRMED", rank_obtained=5, n_choices=5) == (0, "SETTLEMENT_CONFIRMED")
    # Fallback room (rank_obtained > n_choices) -> default (+1)
    assert delta_for_outcome(p, "CONFIRMED", rank_obtained=6, n_choices=5) == (1, "SETTLEMENT_CONFIRMED")
    assert delta_for_outcome(p, "UNALLOTTED") == (2, "SETTLEMENT_UNALLOTTED")
    assert delta_for_outcome(p, "FORFEITED") == (-2, "SETTLEMENT_FORFEITED")
    assert delta_for_outcome(p, "LATE_CANCELLED") == (-1, "SETTLEMENT_LATE_CANCELLED")
    assert delta_for_outcome(p, "REVOKED") == (0, "SETTLEMENT_REVOKED")

    rows = settle_members(
        [
            {"user_id": "u1", "outcome": "CONFIRMED", "rank_obtained": 1, "n_choices": 3},
            {"user_id": "u2", "outcome": "UNALLOTTED"},
            {"user_id": "u3", "outcome": "REVOKED"},
        ],
        p,
    )
    assert [r["delta"] for r in rows] == [-3, 2, 0]


def test_credit_bands_and_streaks():
    history = [
        {"credits": 1, "got_room": False},
        {"credits": 4, "got_room": True},
        {"credits": 8, "got_room": True},
        {"credits": 9, "got_room": False},
    ]
    bands = success_by_credit_band(history)
    assert bands["0-2"] == 0.0
    assert bands["3-5"] == 1.0
    assert bands["6-10"] == 0.5

    gvs = group_vs_solo_success([
        {"group_size": 1, "got_room": True},
        {"group_size": 3, "got_room": False},
    ])
    assert gvs == {"solo": 1.0, "group": 0.0}
    assert longest_losing_streak([True, False, False, False, True, False]) == 3
