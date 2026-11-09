# ADR-0001: MongoDB Replica Set (`rs0`) & Multi-Document ACID Transactions

- **Status:** Accepted
- **Date:** 2026-11-09
- **Components:** [`db/client.py`](../../backend/app/db/client.py), [`db/transactions.py`](../../backend/app/db/transactions.py), [`db/indexes.py`](../../backend/app/db/indexes.py), [`docker-compose.yml`](../../docker-compose.yml)

---

## Context

Core FairNest booking operations modify multiple collections together that must never diverge:
- Opening a cycle snapshots `room_inventory` documents (`is_live: true`), stores the seed commitment on `cycles`, and logs an audit entry.
- Confirming the final member acceptance transitions `allotments` (`HELD → CONFIRMED`), `room_inventory` (`HELD → CONFIRMED`), `applications` (`ALLOTTED → CONFIRMED`), and writes member `notifications`.
- Declining, expiring, cancelling, or revoking an allotment must release `room_inventory` back to `AVAILABLE` while marking the allotment inactive (`is_active: false`) and updating `applications`.

Running MongoDB as a standalone server forbids multi-document ACID transactions (`Transaction numbers are only allowed on a replica set member or mongos`), which would leave partial room holds or leaked locks upon process crashes or mid-operation conflicts.

## Decision

1. Require MongoDB configured as replica set **`rs0`** across development, production Docker Compose ([`docker-compose.yml`](../../docker-compose.yml) with `mongo-init` running `rs.initiate()`), and CI tests ([`docker-compose.test.yml`](../../docker-compose.test.yml)).
2. Configure `AsyncMongoClient` with `w="majority"` and `tz_aware=True` in [`db/client.py`](../../backend/app/db/client.py).
3. Wrap compound mutations inside `session.with_transaction(...)` combined with conditional compare-and-swap (CAS) filters (`status`, `allotment_id`, `version += 1`) and partial unique indexes (`allotments_active_room_unique`, `inv_live_room_unique`).
4. Isolate per-user credit settlement (`settle_cycle`) into small single-user ACID transactions rather than one giant batch transaction, backed by pre-checks and `cl_settlement_unique` (`DuplicateKeyError` idempotency guard) to avoid `WriteConflict` aborts on large cohorts.

## Consequences

- **Positive:** Eliminates split-brain room/allotment states under concurrent accepts, declines, cascades, and cycle opens; database-enforced invariants hold even under network retries or concurrent workers.
- **Trade-off:** Requires `rs0` replica-set initialization even for single-node local setups (`--replSet rs0` + `rs.initiate()`).

---

**Related:** [ADR-0002: PyMongo Async](0002-pymongo-async.md) · [Data Model & Invariants](../data-model-and-invariants.md)
