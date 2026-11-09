#!/usr/bin/env python3
"""Verify an allocation run: check seed commitment, input hash, and Round-1 output hash."""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings
from app.db.client import close_db, connect_db, get_db
from app.services import allocation_service


async def main() -> None:
    parser = argparse.ArgumentParser(description="Verify FairNest allocation integrity")
    parser.add_argument("--cycle", required=True, help="Cycle ID (ObjectId string)")
    args = parser.parse_args()

    settings = get_settings()
    await connect_db(settings.MONGO_URI)
    try:
        db = get_db(settings.MONGO_DB)
        result = await allocation_service.verify_allocation(db, args.cycle)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await close_db()

    checks = result["checks"]
    print(f"Seed commitment: {'PASS ✓' if checks['seed_ok'] else 'FAIL ✗'}")
    print(f"  commitment: {result['seed_commitment']}")
    print(f"Input hash:      {'PASS ✓' if checks['input_ok'] else 'FAIL ✗'}")
    print(f"  stored  : {result['stored_input_hash']}")
    print(f"  computed: {result['computed_input_hash']}")
    print(f"Output hash:     {'PASS ✓' if checks['output_ok'] else 'FAIL ✗'}")
    print(f"  stored  : {result['stored_output_hash']}")
    print(f"  computed: {result['computed_output_hash']}")

    if result["passed"]:
        print("\nVerification PASSED ✓")
        sys.exit(0)
    print("\nVerification FAILED ✗")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
