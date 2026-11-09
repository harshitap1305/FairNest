# ADR-0006: Layered Modular Monolith & Dual-Mode Hostel-Scoped RBAC

- **Status:** Accepted
- **Date:** 2026-11-09
- **Components:** [`main.py`](../../backend/app/main.py), [`worker.py`](../../backend/app/worker.py), [`deps.py`](../../backend/app/api/deps.py), [`scope.py`](../../backend/app/core/scope.py), [`simulator/`](../../simulator/simulator/engine.py)

---

## Context

FairNest must serve three execution contexts (`uvicorn` HTTP API, `python -m app.worker` background scheduler/sweeper, and offline Monte Carlo policy simulator) while managing multi-hostel access control across five roles (`STUDENT`, `WARDEN`, `ADMIN`, `AUDITOR`, `SUPER_ADMIN`).

Splitting into separate microservices prematurely would fracture ACID MongoDB transactions across HTTP boundaries and force duplicate re-implementation of allocation/settlement math between backend and simulator. Additionally, uniform HTTP `403 Forbidden` responses across all roles leak confidential existence signals to students probing other hostels' groups, rooms, or cycles (IDOR enumeration).

## Decision

1. **Layered Modular Monolith:** Structure `backend/app/` strictly inward (`api/routes → services → repositories → pure core allocator/fairness → db`). Keep `app/allocator/` and `app/fairness/` free of FastAPI, MongoDB, clock, and global RNG imports so [`worker.py`](../../backend/app/worker.py) runs shared services natively and [`simulator/`](../../simulator/simulator/engine.py) imports the exact production math with zero drift.
2. **Five-Role RBAC Hierarchy ([`deps.py`](../../backend/app/api/deps.py)):** Enforce least-privilege dependencies (`current_student`, `current_warden`, `current_admin`, `current_auditor`, `current_super_admin`), keeping `AUDITOR` strictly read-only and preventing disabling/revoking the last active `SUPER_ADMIN` (`409 LAST_SUPER_ADMIN`).
3. **Dual-Mode Hostel Scope Enforcement ([`scope.py`](../../backend/app/core/scope.py)):**
   - **Students (`assert_student_scope` / `assert_student_eligible_for_hostel`):** Out-of-scope hostel, cycle, room, group, or eligibility checks raise **`404 NotFoundError`** (concealing resource existence against horizontal/vertical IDOR scans).
   - **Staff (`assert_staff_scope`):** Out-of-scope warden/admin/scoped-auditor operations raise **`403 ForbiddenError(code="HOSTEL_SCOPE_DENIED")`** and support audited breach logging (`SCOPE_DENIED:*`). Global `AUDITOR` (empty `managed_hostel_ids`) and `SUPER_ADMIN` retain campus-wide access.

## Consequences

- **Positive:** Single deployable backend/worker image, atomic in-process Mongo transactions, zero algorithmic skew between simulator metrics and production execution, and hardened multi-hostel isolation without student enumeration leaks.
- **Trade-off:** Scaling `RateLimiter` or high-throughput API replicas horizontally in the future will require extracting process-local rate-limit buckets ([`rate_limit.py`](../../backend/app/core/rate_limit.py)) into Redis.

---

**Related:** [System Architecture](../architecture.md) · [Non-Functional Requirements](../non-functional-requirements.md)
