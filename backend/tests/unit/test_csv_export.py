"""Unit tests for CSV export helpers (formula-injection safety, formatting)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.csv_export import build_csv, sanitize_cell


def test_formula_like_cells_are_neutralised():
    assert sanitize_cell("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert sanitize_cell("+1+1") == "'+1+1"
    assert sanitize_cell("@SUM(A1)") == "'@SUM(A1)"
    assert sanitize_cell("-cmd") == "'-cmd"


def test_plain_values_pass_through():
    assert sanitize_cell("Room 101") == "Room 101"
    assert sanitize_cell(-2) == "-2"
    assert sanitize_cell("-1.5") == "-1.5"
    assert sanitize_cell(None) == ""
    assert sanitize_cell(True) == "yes"
    assert sanitize_cell(datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)) == "2026-01-02T03:04:00+00:00"


def test_build_csv_quotes_commas_and_newlines():
    out = build_csv(["a", "b"], [["x,y", "line1\nline2"], [1, None]])
    assert out.splitlines()[0] == "a,b"
    assert '"x,y"' in out and '"line1\nline2"' in out
    assert out.endswith("1,\n")
