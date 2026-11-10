"""Apply MongoDB JSON Schema validators to collections."""

from __future__ import annotations

import logging

from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)


async def create_validators(db) -> None:
    """Apply $jsonSchema validators. Safe to call on an existing collection."""

    room_inventory_schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["cycle_id", "room_id", "capacity", "status"],
            "properties": {
                "cycle_id": {"bsonType": "string"},
                "room_id": {"bsonType": "string"},
                "capacity": {"bsonType": ["int", "long"], "minimum": 1, "maximum": 8},
                "status": {"enum": ["AVAILABLE", "HELD", "CONFIRMED", "BLOCKED"]},
            },
        }
    }

    # Try to modify existing collection validator
    for collection_name, validator in [
        ("room_inventory", room_inventory_schema),
    ]:
        try:
            await db.command(
                "collMod",
                collection_name,
                validator=validator,
                validationLevel="moderate",
                validationAction="error",
            )
        except OperationFailure as exc:
            # Collection doesn't exist yet (or Atlas user lacks collMod privilege) — create it
            try:
                await db.create_collection(
                    collection_name,
                    validator=validator,
                    validationLevel="moderate",
                    validationAction="error",
                )
            except OperationFailure as create_exc:
                if exc.code == 13 and create_exc.code == 48:
                    logger.warning(
                        "Skipping collMod validator update on existing collection %s (insufficient privileges)",
                        collection_name,
                    )
                elif create_exc.code != 48:
                    raise
