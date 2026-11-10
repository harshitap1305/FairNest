# FairNest Documentation

FairNest is a **zero-payment, multi-hostel, fairness-aware hostel room booking and allotment platform** built around **Weighted Random Serial Dictatorship (RSD)**, bounded inter-cycle fairness credits, unanimous group consent, cryptographic commit–reveal auditability, and a shared Monte Carlo policy simulator.

> [!IMPORTANT]
> **Zero-Payment Domain Model:** FairNest intentionally contains **no payment gateway, billing, or fee settlement**. Every offered room transitions cleanly through **`HELD` → unanimous member `accept` → `CONFIRMED`** within a configurable freeze window (`freeze_hours`, default 48 hours). Any legacy endpoint such as `/allotments/{id}/pay` is absent (`404`).

---

## Documentation Map

| Document | Audience | What It Covers |
|---|---|---|
| [Quick Setup Guide (Docker & Local)](../SETUP.md) | All Developers, Evaluators | Step-by-step installation, `.env` setup for `iitbhilai.demo`, Docker Compose & local native setup (Atlas or local `rs0`), seeding, tests, and troubleshooting. |
| [System Architecture & Design](architecture.md) | Engineers, Architects | Modular monolith layering, Docker/native runtime topology, FastAPI API, background worker, MongoDB `rs0`, React 18 SPA + in-memory JWT/refresh rotation, request lifecycles. |
| [Complete Features & Workflows](features.md) | Product, QA, Admins, Students | Every feature across all 5 RBAC roles (`STUDENT`, `WARDEN`, `ADMIN`, `AUDITOR`, `SUPER_ADMIN`), public auth pages, worker automation, and CLI tools, mapped to UI routes, endpoints, and services. |
| [Unique Design Aspects & Core Algorithms](uniqueness-and-algorithms.md) | Faculty, Reviewers, Algorithm Engineers | Deep technical walkthrough of every novel FairNest innovation: unanimous consent, `[0, 10]` fairness credits, Efraimidis–Spirakis HMAC-SHA256 RSD, Tier-0 accessibility isolation, no-re-randomization cascade, commit–reveal auditability, single-live-release lock, one-time grace extension, natural room sorting, and comma-list dry-run parser. |
| [Non-Functional Requirements & Implementation](non-functional-requirements.md) | Security Engineers, Reviewers, SREs | Exhaustive breakdown of every NFR (concurrency safety, ACID atomicity, idempotency, Argon2id/JWT security, IDOR 404 masking vs staff 403 audit, performance, reliability, observability, determinism) and the exact code mechanisms enforcing them. |
| [Data Model, State Machines & Invariants](data-model-and-invariants.md) | Backend Engineers, DBAs | All 20 MongoDB collections, enumerations, state diagrams (`Cycle`, `Allotment`, `Group`, `Application`), full index catalog (partial unique & TTL), `$jsonSchema` validator, and runtime/CLI invariants. |
| [REST API Reference](api-reference.md) | Frontend/Integration Devs, QA | Complete `/api/v1` endpoint specification (auth, roles, scope rules, `Idempotency-Key`/`If-Match`, request/response shapes, and all backend error codes). |
| [Policy Simulator & Fairness Analysis](simulator-and-fairness-analysis.md) | Researchers, Policy Designers | Offline Monte Carlo engine sharing the production `app/allocator` & `app/fairness` core, configs (`base`, `high_groups`, `low_confirm`, `skewed`), scenarios `S1`–`S8`, policies, fairness metrics, and CLI usage. |
| [Operations, Testing & Runbook](operations-testing-and-runbook.md) | DevOps, Maintainers, Graders | Environment setup (`.env`), Docker Compose & native dev instructions, worker cadence, CLI operational scripts (`create_super_admin.py`, `load_demo_data.py`, `verify_allocation.py`, `check_invariants.py`), failure recovery, and the full 38-test inventory. |

---

## Architecture Decision Records (`docs/adr/`)

| ADR | Title | Decision Summary |
|---|---|---|
| [ADR-0001](adr/0001-mongo-transactions.md) | MongoDB Replica Set & Multi-Document ACID Transactions | Require MongoDB `rs0` (`w="majority"`) so multi-collection hold, confirm, release, cascade, and cycle open/close state transitions execute atomically. |
| [ADR-0002](adr/0002-pymongo-async.md) | PyMongo Async API (`AsyncMongoClient`) over Motor | Adopt `pymongo==4.12.1` native `AsyncMongoClient` directly rather than deprecated Motor wrappers. |
| [ADR-0003](adr/0003-commit-reveal.md) | Cryptographic Commit–Reveal & Input/Output Hashing | Commit `SHA-256(seed_secret)` at cycle open, hide `seed_secret` until Round-1 execution, and allow independent hash verification afterwards. |
| [ADR-0004](adr/0004-weighted-rsd-and-bounded-credits.md) | Weighted RSD (Efraimidis–Spirakis) & Bounded `[0, 10]` Credits | Use strategy-proof Weighted RSD paired with outcome-adjusted bounded credits and inter-cycle damping instead of FCFS, greedy point bidding, or pure unweighted lotteries. |
| [ADR-0005](adr/0005-zero-payment-group-consent-model.md) | Zero-Payment Unanimous Group Consent Confirmation | Decouple room allocation from payments using per-member atomic acceptance, cascade on decline/timeout, and a single automatic 10-minute worker grace extension. |
| [ADR-0006](adr/0006-modular-monolith-and-hostel-scoped-rbac.md) | Modular Monolith & Two-Mode Hostel-Scoped RBAC | Share pure domain packages cleanly between API/worker/simulator; separate student privacy masking (`404`) from audited staff scope enforcement (`403 HOSTEL_SCOPE_DENIED`). |

---

## Recommended Reading Order

1. **Evaluating System Design & Novelty:** Start with [Unique Design Aspects & Core Algorithms](uniqueness-and-algorithms.md) → [Non-Functional Requirements & Implementation](non-functional-requirements.md) → [ADRs](adr/0001-mongo-transactions.md).
2. **Reviewing Full Feature Surface:** Read [Complete Features & Workflows](features.md) alongside [REST API Reference](api-reference.md).
3. **Working on Backend / Database:** Read [System Architecture & Design](architecture.md) → [Data Model, State Machines & Invariants](data-model-and-invariants.md) → [Operations, Testing & Runbook](operations-testing-and-runbook.md).
4. **Running Fairness Experiments:** Read [Policy Simulator & Fairness Analysis](simulator-and-fairness-analysis.md).

---

## Quick System Snapshot

| Aspect | Value / Implementation | Source |
|---|---|---|
| Backend Runtime | Python 3.11, FastAPI `0.111.0`, Uvicorn (`--workers 1` default container) | [Dockerfile](../backend/Dockerfile), [main.py](../backend/app/main.py) |
| Database | MongoDB 7/8 single-node replica set (`rs0`), `pymongo==4.12.1` (`AsyncMongoClient`) | [docker-compose.yml](../docker-compose.yml), [client.py](../backend/app/db/client.py) |
| Background Worker | `python -m app.worker` (`30s` polling cadence, `10m` invariant checks) | [worker.py](../backend/app/worker.py) |
| Frontend | React `18.3.1`, MUI v5, React Query v5, Axios, Vite `5.2.13`, Nginx | [package.json](../frontend/package.json), [nginx.conf](../frontend/nginx.conf) |
| Core Allocation Engine | Pure Python Efraimidis–Spirakis Weighted RSD + Deterministic `assign_in_order` Cascade | [allocator/core.py](../backend/app/allocator/core.py) |
| Fairness Bounds | `C_MIN=0`, `C_INIT=3`, `C_MAX=10`, weight `1 + credits`, factor `0.5` carry-over | [config.py](../backend/app/core/config.py), [fairness/engine.py](../backend/app/fairness/engine.py) |
| RBAC Roles | `STUDENT`, `WARDEN`, `ADMIN`, `AUDITOR`, `SUPER_ADMIN` | [constants.py](../backend/app/core/constants.py) |
