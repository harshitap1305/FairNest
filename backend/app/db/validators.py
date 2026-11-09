"""Apply MongoDB JSON Schema validators to collections."""

from __future__ import annotations

from pymongo.errors import OperationFailure


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
        except OperationFailure:
            # Collection doesn't exist yet — create it with the validator
            await db.create_collection(
                collection_name,
                validator=validator,
                validationLevel="moderate",
                validationAction="error",
            )
