"""Catalogue service: room list parsing and availability summary."""

from __future__ import annotations

import re


_VALID_ROOM_NO = re.compile(r"^[A-Z0-9\-/]{1,10}$")


def parse_room_list(raw: str) -> list[dict]:
    """
    Split a comma-separated string of room numbers, strip whitespace,
    skip empty tokens, deduplicate, and return a list of dicts.

    Returns:
        list of {"room_no": str, "is_duplicate": bool}
    """
    tokens = [t.strip() for t in re.split(r"[,\n]", raw or "") if t.strip()]
    seen: set[str] = set()
    result: list[dict] = []

    for token in tokens:
        no = token.split(":", 1)[0].strip().upper()
        is_dup = no in seen
        seen.add(no)
        result.append({"room_no": no, "is_duplicate": is_dup})

    return result


def parse_room_entries(
    room_numbers: str,
    default_capacity: int,
    *,
    max_tokens: int = 200,
) -> tuple[list[dict], list[str], list[dict]]:
    """
    Parse comma/newline-separated room entries (supporting '203:3' capacity overrides).
    Returns (parsed_rooms, duplicates_in_input, invalid).
    """
    tokens = [t.strip() for t in re.split(r"[,\n]", room_numbers or "") if t.strip()]
    if len(tokens) > max_tokens:
        from app.core.errors import ValidationError
        raise ValidationError(f"Maximum {max_tokens} rooms per batch (got {len(tokens)})")

    seen: set[str] = set()
    dups: list[str] = []
    parsed: list[dict] = []
    invalid: list[dict] = []

    for token in tokens:
        capacity = default_capacity
        if ":" in token:
            parts = token.split(":", 1)
            token_no = parts[0].strip().upper()
            try:
                capacity = int(parts[1].strip())
                if capacity < 1 or capacity > 8:
                    invalid.append({"token": token, "reason": "Capacity must be 1-8"})
                    continue
            except ValueError:
                invalid.append({"token": token, "reason": "Invalid capacity"})
                continue
        else:
            token_no = token.upper()

        if not _VALID_ROOM_NO.match(token_no):
            invalid.append({"token": token, "reason": "Invalid characters or length"})
            continue

        if token_no in seen:
            dups.append(token_no)
            continue

        seen.add(token_no)
        parsed.append({"room_no": token_no, "capacity": capacity})

    return parsed, dups, invalid


async def get_availability_summary(db, cycle_id: str) -> dict:
    """Query room_inventory for the given cycle and return a summary of bed counts."""
    pipeline = [
        {"$match": {"cycle_id": cycle_id}},
        {"$group": {"_id": "$status", "beds": {"$sum": "$capacity"}}},
    ]
    cursor = await db["room_inventory"].aggregate(pipeline)
    rows = await cursor.to_list(length=20)
    counts: dict[str, int] = {row["_id"]: row["beds"] for row in rows}

    total = sum(counts.values())
    occupied = counts.get("CONFIRMED", 0)
    held = counts.get("HELD", 0)
    available = counts.get("AVAILABLE", 0)

    return {
        "total_beds": total,
        "occupied_beds": occupied,
        "available_beds": available,
        "held_beds": held,
    }
