"""Pure functions for allocation verification (seed commitment + output hash)."""
import hashlib
import json
from typing import List


def compute_seed_commitment(seed_secret: str) -> str:
    """SHA-256 of the seed secret. Stored BEFORE allocation runs."""
    return hashlib.sha256(seed_secret.encode("utf-8")).hexdigest()


def compute_input_hash(applications: List[dict]) -> str:
    """
    Deterministic hash of the application set.
    applications: list of {"group_id": str, "choices": list[str], "weight": float}
    """
    normalized = sorted(
        [
            {
                "group_id": str(a["group_id"]),
                "choices": [str(c) for c in a.get("choices", [])],
                "weight": float(a.get("weight", 1.0)),
            }
            for a in applications
        ],
        key=lambda x: x["group_id"],
    )
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def compute_output_hash(allotments: List[dict]) -> str:
    """
    Deterministic hash of the allocation output.
    allotments: list of {"group_id": str, "room_id": str|None, "order_index": int}
    """
    normalized = sorted(
        [
            {
                "group_id": str(a["group_id"]),
                "room_id": str(a.get("room_id")) if a.get("room_id") else None,
                "order_index": int(a.get("order_index", 0)),
            }
            for a in allotments
        ],
        key=lambda x: x["group_id"],
    )
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
