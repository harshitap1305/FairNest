# ADR-0003: Cryptographic Commit–Reveal & Canonical Input/Output Hashing

- **Status:** Accepted
- **Date:** 2026-11-09
- **Components:** [`cycle_service.py`](../../backend/app/services/cycle_service.py), [`allocation_service.py`](../../backend/app/services/allocation_service.py), [`allocator/verify.py`](../../backend/app/allocator/verify.py), [`verify_allocation.py`](../../backend/scripts/verify_allocation.py)

---

## Context

Hostel allocation determines scarce housing assignments across hundreds of students. In a purely opaque backend lottery, students or faculty auditors have no proof that administrators did not cherry-pick a random seed after seeing group applications, or manually alter outputs post-run.

At the same time, publishing the raw RNG seed *before* the application window closes would allow colluding applicants to brute-force favorable application submission orders or IDs.

## Decision

Implement a three-stage **Cryptographic Commit–Reveal Verification** protocol:

1. **Commit at Cycle Open (`open_cycle_impl`):** Generate a 256-bit cryptographically random `seed_secret = os.urandom(32).hex()` and immediately store + expose its `seed_commitment = SHA-256(bytes.fromhex(seed_secret)).hexdigest()`. [`serialize_cycle`](../../backend/app/services/cycle_service.py#L50-L64) strips `seed_secret` and `seed_revealed` from all API responses until allocation completes (`ALLOTMENT_ACTIVE`, `CLOSED`, `SETTLED`).
2. **Record Canonical Snapshot at Allocation (`run_allocation`):** Serialize sorted applications (`id`, `weight`, `tier`, `group_size`, `fallback`, `choices`), sorted eligible `free_rooms`, and `seed.hex()` into canonical JSON to record `input_hash`, execute deterministic HMAC-SHA256 `allocate()`, record `output_hash` and `snapshot_room_ids` onto an immutable `MAIN` `allocation_runs` document, and transition the cycle to `ALLOTMENT_ACTIVE` (revealing `seed_secret`).
3. **Independent Verification (`GET /cycles/{id}/audit` & `scripts/verify_allocation.py`):** Re-load the preserved `snapshot_room_ids` and non-withdrawn/non-draft Round-1 application cohort (`for_verification=True`), recompute `SHA-256(bytes.fromhex(seed_revealed))`, `input_hash`, and `output_hash` by re-executing `allocate()`, and assert all three (`seed_ok`, `input_ok`, `output_ok`) match.

## Consequences

- **Positive:** Prevents both pre-close seed gaming by applicants and post-close seed cherry-picking or result tampering by staff; remains verifiable long after confirms, forfeits, cascades, and cycle settlement.
- **Constraint:** Post-close snapshots (`credit_snapshot`, `tier`, `ranked_choices`, `snapshot_room_ids`) must remain immutable once `APPLICATIONS_CLOSED` / Round 1 has run.

---

**Related:** [Unique Design Aspects & Algorithms](../uniqueness-and-algorithms.md) · [ADR-0004: Weighted RSD & Credits](0004-weighted-rsd-and-bounded-credits.md)
