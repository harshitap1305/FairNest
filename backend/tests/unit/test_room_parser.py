"""Unit tests for comma-separated room list parser & capacity overrides (T19, T20)."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.services.catalogue_service import parse_room_entries, parse_room_list


def test_parse_room_list_basic():
    res = parse_room_list("101, 102,, 103\n101")
    assert [r["room_no"] for r in res] == ["101", "102", "103", "101"]
    assert res[0]["is_duplicate"] is False
    assert res[3]["is_duplicate"] is True


def test_parse_room_entries_capacity_overrides():
    parsed, dups, invalid = parse_room_entries("101, 102:3, A-10:4, 101", default_capacity=2)
    assert dups == ["101"]
    assert invalid == []
    assert parsed == [
        {"room_no": "101", "capacity": 2},
        {"room_no": "102", "capacity": 3},
        {"room_no": "A-10", "capacity": 4},
    ]


def test_parse_room_entries_flags_invalid_tokens():
    parsed, dups, invalid = parse_room_entries("201, bad@@room, 202:9, 203:0, 204:abc", default_capacity=2)
    assert parsed == [{"room_no": "201", "capacity": 2}]
    assert dups == []
    assert len(invalid) == 4


def test_parse_room_entries_enforces_200_max():
    raw = ",".join(str(i) for i in range(1, 202))
    with pytest.raises(ValidationError):
        parse_room_entries(raw, default_capacity=2, max_tokens=200)
