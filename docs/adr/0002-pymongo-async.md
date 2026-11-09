# ADR-0002: PyMongo Native Async API (`AsyncMongoClient`) Over Motor

- **Status:** Accepted
- **Date:** 2026-11-09
- **Components:** [`requirements.txt`](../../backend/requirements.txt), [`db/client.py`](../../backend/app/db/client.py), [`db/transactions.py`](../../backend/app/db/transactions.py)

---

## Context

Historically, FastAPI + MongoDB services relied on `motor`, an asynchronous wrapper built atop synchronous PyMongo with background threadpools. However, MongoDB introduced first-party native `AsyncMongoClient` directly inside PyMongo 4.x (`pymongo==4.12.1`), unifying async and sync driver internals and deprecating Motor's separate abstraction layer.

Using Motor introduces extra wrapper overhead, divergent cursor APIs, and migration debt as PyMongo's native async engine becomes the official standard.

## Decision

Adopt **`pymongo==4.12.1`** directly using `from pymongo import AsyncMongoClient` in [`db/client.py`](../../backend/app/db/client.py), removing `motor` from backend dependencies entirely. All repository queries, aggregations (`async for doc in await col.aggregate(...)`), index/validator creation, and `async with client.start_session() as session:` transactions execute directly against `AsyncMongoClient`.

## Consequences

- **Positive:** Zero wrapper mismatch; first-class `with_transaction` retryable semantics; clean modern typing and reduced dependency footprint in Docker builds.
- **Trade-off:** Engineers familiar with older Motor idioms must remember that `collection.aggregate(...)` is awaited (`await db[...].aggregate(...)`) before iterating cursors in PyMongo 4.12+ async.

---

**Related:** [ADR-0001: MongoDB Transactions](0001-mongo-transactions.md) · [System Architecture](../architecture.md)
