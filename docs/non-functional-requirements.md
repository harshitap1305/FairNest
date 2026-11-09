# Non-Functional Requirements (NFRs) & Implementation

This document maps every **Non-Functional Requirement** of FairNest—concurrency safety, ACID correctness, security, privacy, idempotency, reliability, observability, performance, and reproducibility—to the **exact mechanisms implemented in source code**.

---

## NFR Implementation Matrix

| NFR Category | Target / Guarantee | Verified Code Implementation |
|---|---|---|
| **Atomicity & Consistency** | Multi-collection state shifts never leave half-updated rooms/allotments | MongoDB `rs0` + `w="majority"` (`client.py`) + `session.with_transaction()` (`transactions.py`) |
| **Concurrency Safety** | Zero double-allotments, zero double-holds, race-safe member accepts | Partial unique indexes (`indexes.py`), CAS `$elemMatch` (`accept_member`), `version += 1` guards |
| **Idempotency & OCC** | Safe client retries without duplicate side effects or lost edits | `idempotency_keys` (`Idempotency-Key` SHA-256 hash + 24h TTL) & `If-Match` / `version` checks |
| **Authentication Security** | Resistant to offline brute-force, XSS token theft, & token replay | Argon2id (`64 MiB`), RAM-only JWT (`15m`), SHA-256 rotated HttpOnly refresh tokens + reuse family kill |
| **Authorization & IDOR** | Role least-privilege, hostel isolation, zero enumeration leaks | RBAC guards (`deps.py`), student `404` concealment vs. staff `403 HOSTEL_SCOPE_DENIED` (`scope.py`) |
| **Abuse & Transport Defense** | Brute-force throttling, CSRF defense, clickjacking/MIME protection | Sliding token-bucket `RateLimiter` + 15m lockout, Origin/Referer checks, `SecurityHeadersMiddleware` |
| **Reliability & Self-Healing** | Holds never leak if a client drops; crashes roll back cleanly | 4 fast `worker.py` jobs (`30s`) + 10m invariant audit, `ALLOCATING` crash rollback, `+10m` grace extension, `settle_cycle` per-user txns |
| **Observability & Auditability** | End-to-end request correlation and tamper-evident audit logs | `RequestIDMiddleware` (`X-Request-ID`), `structlog` UTC JSON, immutable `audit_logs` + `credit_ledger` |
| **Performance** | Avoid N+1 DB queries on dashboard, cascade, rooms, and audits | Batched `$in` room lookups, indexed projections, single-flight frontend refresh (`_refreshPromise`) |
| **Determinism & Testability** | Bit-identical replay under fixed seed and controllable clock | HMAC-SHA256 allocator without `random`/DB/clock + injectable `core/clock.py` |

---

## 1. Concurrency Safety & Multi-Document Atomicity

### MongoDB Replica Set & `with_transaction`

[`db/client.py`](../backend/app/db/client.py) creates a PyMongo `AsyncMongoClient` configured with `w="majority"` and `tz_aware=True`. All multi-document mutations execute inside `run_in_tx()` ([`db/transactions.py`](../backend/app/db/transactions.py)), which opens a MongoDB client session and runs `session.with_transaction(callback)` against replica set `rs0`.

### Atomic Compare-And-Swap (CAS) Guards

Even inside transactions or single-document updates, repositories guard against concurrent stale updates using conditional filters ([`repositories/core_repos.py`](../backend/app/repositories/core_repos.py)):

1. **Inventory Hold / Confirm / Release:**
   - `hold_room`: requires `status == "AVAILABLE"`, atomically sets `status = "HELD"` and `allotment_id = allotment_id`, increments `version += 1`.
   - `confirm_room`: requires `status == "HELD"` and `allotment_id == allotment_id`, increments `version += 1`.
   - `release_room`: requires `allotment_id == allotment_id` (plus status match), resets `allotment_id = None`, increments `version += 1`.
2. **Concurrent Roommate Consent (`accept_member`):**
   - Concurrent `POST /allotments/{id}/accept` requests from multiple roommates race on the same `allotments` document.
   - `accept_member` uses `find_one_and_update` matching `status: "HELD"`, `expires_at > now`, and `members: {"$elemMatch": {"user_id": uid, "accept_status": "PENDING"}}`, updating via positional `$` operator. Once every member in the returned `members` array is `"ACCEPTED"`, the caller promotes `allotments` and `room_inventory` to `CONFIRMED`.
3. **Grace Extension CAS (`try_extend_grace`):**
   - Invoked by `worker.run_expire_holds` when `expires_at <= now`. `update_one` requires `status == "HELD"`, `grace_used == False`, and `members` matching `$elemMatch: {"accept_status": "PENDING"}`, setting `grace_used = True` and pushing `expires_at` by `+10 minutes` atomically.
4. **Cycle State Locks:**
   - `transition_cycle_status` atomically switches `APPLICATIONS_CLOSED → ALLOCATING` before running Round 1 (returning `409 ALLOCATION_ALREADY_RUN` on duplicate triggers) and rolls back to `APPLICATIONS_CLOSED` in an `except` block if execution fails.
   - The background worker uses `SCHEDULED → APPLICATIONS_OPEN_PENDING` (`open_window`) before committing `APPLICATIONS_OPEN` + generating the cryptographic seed commitment.
5. **Atomic Clamped Credits & Duplicate-Safe Settlement:**
   - `credit_accounts` balances are updated inside MongoDB via aggregation-pipeline `update_one` (`$min` / `$max` clamping to `[C_MIN, C_MAX]`).
   - `settle_cycle` executes **outside** a long multi-write transaction: it pre-checks `credit_ledger` for `(cycle_id, user_id)` settlement uniqueness and relies on MongoDB's partial unique index `cl_settlement_unique` (catching `DuplicateKeyError`), preventing replica-set `WriteConflict` aborts on large batches while preserving idempotency.

---

## 2. Idempotency & Optimistic Concurrency Control (OCC)

| Mechanism | Scope | Behavior | Implementation |
|---|---|---|---|
| **`Idempotency-Key` Header** | `/invites/{id}/accept`, `/invites/{id}/decline`, `/groups/{id}/application/submit`, `/groups/{id}/application/withdraw`, `/allotments/{id}/{accept,decline,cancel}` | Optional HTTP header (`max 128 chars`). Computes `SHA-256(method:path:canonical_json_body)` scoped per `(user_id, key)`. Replaying the exact request returns the cached `{status_code, response}` within **24 hours** (`idempotency_ttl`). Reusing the same key with a different payload raises **`409 IDEMPOTENCY_CONFLICT`**. | [`core/idempotency.py`](../backend/app/core/idempotency.py) |
| **Optimistic Locking (`If-Match` / `version`)** | `PUT /groups/{id}/application` | Compares client `If-Match` header (or payload `version`) against `application.version` inside `update_one`; mismatches raise **`409 VERSION_CONFLICT`**. | [`group_service.py`](../backend/app/services/group_service.py), [`core_repos.py`](../backend/app/repositories/core_repos.py) |
| **Frontend Auto-Generation** | Group, allotment, cycle, & admin mutations | `client.js`, `cycle.js`, and `admin.js` attach UUID `Idempotency-Key` headers via `crypto.randomUUID()`. Backend endpoints enforcing `idempotency_keys` cache responses directly; cycle/admin mutations rely on atomic CAS & partial unique indexes. | [`frontend/src/api/`](../frontend/src/api/client.js) |

---

## 3. Authentication, Password Hardening & Session Security

### Password Policy & Hashing ([`core/security.py`](../backend/app/core/security.py))
- **Algorithm:** Argon2id via `argon2-cffi` (`time_cost=2`, `memory_cost=65536` / **64 MiB**, `parallelism=2`, `hash_len=32`, `salt_len=16`).
- **Strength Validation (`_validate_password`):** Minimum **10 characters** (enforced at 12 characters for CLI [`create_super_admin.py`](../backend/scripts/create_super_admin.py)), blocks common weak passwords (`password`, `1234567890`, `hostel123`, etc.), and rejects passwords matching the user's email or roll number.

### Dual-Token Lifecycle & Replay Protection
- **Access Token (JWT HS256, `JWT_ACCESS_MINUTES = 15`):**
  - Claims: `sub` (user ID), `role`, `tv` (`token_version`), `jti` (UUID), `iat`, `exp`.
  - Stored **exclusively in JavaScript memory** (`_accessToken` in [`client.js`](../frontend/src/api/client.js)) on the frontend—**never** in `localStorage` or `sessionStorage`, eliminating persistent XSS credential harvesting.
  - Axios shares a **single-flight `_refreshPromise`** across concurrent `401` responses so parallel API calls trigger only one `/auth/refresh` rotation rather than racing and false-tripping token reuse detection.
- **Refresh Token (Opaque 32-byte URL-safe hex, `REFRESH_DAYS = 7`):**
  - Delivered via cookie (`HttpOnly`, `SameSite=Strict`, `Secure` configurable via `COOKIE_SECURE`, scoped to `/api/v1/auth`).
  - Only its **SHA-256 hex digest** is persisted in `refresh_tokens`, along with `family_id`, `replaced_by`, `revoked`, and TTL index `rt_ttl`.
  - **Automatic Reuse Detection:** Every `/auth/refresh` call atomically marks the old token `revoked=True` and links `replaced_by`. Presenting an already-revoked token (`revoked=True`) immediately revokes **every token sharing that `family_id`**, writes a `TOKEN_REUSE_DETECTED` security audit log, and returns **`401 TOKEN_REUSE`**.
- **Instant Global Revocation (`token_version`):**
  - Calling `bump_token_version` increments `users.token_version` upon logout-all, password change/reset, account disable, role grant/revoke, or hostel scope reassignment. `get_current_user` compares JWT `tv` against `user.token_version`, rejecting stale access tokens immediately with `401 TOKEN_INVALID`.

---

## 4. Abuse Prevention, CSRF, CORS & Transport Headers

1. **Brute-Force Rate Limiting ([`core/rate_limit.py`](../backend/app/core/rate_limit.py)):**
   - Process-local sliding-window token bucket `RateLimiter`:
     - `check_login`: **10 requests / 60s per client IP (`request.client.host`)** on `/auth/login`.
     - `check_identifier`: **5 requests / 60s per email/roll number** on `/auth/login`.
     - `check_sensitive`: **5 requests / 60s per client IP** on `/auth/activate`, `/auth/forgot`, and `/auth/reset`.
   - **Account Lockout:** After **5 consecutive failed logins** (`new_count >= 5`), [`auth_service.py`](../backend/app/services/auth_service.py) transitions the account to `LOCKED` (`locked_until`) for **`15 minutes`**.
2. **Cookie CSRF Protection ([`api/routes/auth.py`](../backend/app/api/routes/auth.py)):**
   - Cookie-bearing state endpoints (`/auth/refresh` and `/auth/logout`) verify `Origin` against `CORS_ORIGINS` (`_check_origin_csrf`), rejecting mismatched origins with `403 CSRF_ORIGIN_MISMATCH`.
3. **Security Response Headers ([`core/middleware.py`](../backend/app/core/middleware.py)):**
   - `SecurityHeadersMiddleware` injects on every HTTP response:
     - `X-Content-Type-Options: nosniff`
     - `X-Frame-Options: DENY`
     - `Referrer-Policy: strict-origin-when-cross-origin`
     - `Content-Security-Policy: default-src 'self'`
   - In production Docker builds, [`nginx.conf`](../frontend/nginx.conf) also sets matching security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`) and disables directory listing.
4. **Input Validation & Mass-Assignment Prevention:**
   - Route handlers extract explicit allowlisted keys (`allowed_fields` on updates, service-level field picking) rather than passing arbitrary JSON dictionaries directly to `$set` updates.
   - [`catalogue_service.py`](../backend/app/services/catalogue_service.py) enforces strict `^[A-Z0-9\-/]{1,10}$` room codes, `capacity in [1, 8]`, and batch caps (`<= 200` rooms).
5. **Container Least Privilege:**
   - [`backend/Dockerfile`](../backend/Dockerfile) creates non-root user `appuser` (UID `1001`) before starting Uvicorn (`--workers 1`) or `python -m app.worker`.

> [!NOTE]
> `RateLimiter` is stored in-memory per Python process. The default single-process `--workers 1` configuration keeps counts consistent; multi-replica scaling in the future should back `RateLimiter` with Redis or shared counters.

---

## 5. Authorization, RBAC & IDOR Concealment

- **Five Strict Roles:** `STUDENT`, `WARDEN`, `ADMIN`, `AUDITOR`, `SUPER_ADMIN`.
- **RBAC Dependencies ([`api/deps.py`](../backend/app/api/deps.py)):** Route guards (`require_roles(...)`, `current_warden`, `current_admin`, `current_auditor`, `current_super_admin`) fail closed with `403 FORBIDDEN`. `AUDITOR` is strictly read-only.
- **Two-Mode Scope Checks ([`core/scope.py`](../backend/app/core/scope.py)):**
  - `STUDENT` accessing a hostel/cycle/group/allotment outside their `hostel_ids` or gender/year rules receives **`404 NotFoundError`** (preventing inference about whether rooms/groups exist in other hostels).
  - `WARDEN`, `ADMIN`, or scoped `AUDITOR` accessing another hostel receives **`403 ForbiddenError(code="HOSTEL_SCOPE_DENIED")`** with an explicit error detail and audit helper hooks (`audit_scope_violation`).
- **Last-Super-Admin Protection:** `disable_user` and `revoke_role_grant` ([`admin.py`](../backend/app/api/routes/admin.py)) refuse to demote or disable the final active `SUPER_ADMIN` (`409 LAST_SUPER_ADMIN`).

---

## 6. Reliability, Fault Tolerance & Self-Healing

- **Automated Background Maintenance ([`worker.py`](../backend/app/worker.py)):**
  - Runs 4 idempotent lifecycle jobs on a `30s` loop (`run_expire_holds`, `run_open_window`, `run_close_window`, `run_close_cycle_check`), plus a `10m` invariant sanity audit (`run_invariant_check`).
  - `allocation_service.run_allocation` wraps execution in an `except:` guard that rolls an interrupted `ALLOCATING` cycle cleanly back to `APPLICATIONS_CLOSED`.
- **Orphan / Dead-Process Safety:**
  - Closing (`run_close_cycle_check`), settling (`settle_cycle`), or cancelling (`cancel_cycle`) releases `is_live: False` on `room_inventory` so rooms never remain permanently stranded across cycles.
- **Deterministic Clock Injection ([`core/clock.py`](../backend/app/core/clock.py)):**
  - Every timestamp check (`now()`) passes through `core/clock.py`, enabling integration tests to fast-forward `freeze_hours` or `grace_window` cleanly without brittle `sleep()` calls.

---

## 7. Observability, Auditability & Performance

### Structured Logging & Request Correlation
- [`core/logging.py`](../backend/app/core/logging.py) configures `structlog` emitting UTC ISO-8601 JSON logs (`service="fairnest"`, level filtering via `LOG_LEVEL`).
- `RequestIDMiddleware` reads inbound `X-Request-ID` or generates a UUIDv4, propagates it onto `request.state.request_id` and response `X-Request-ID` headers, and embeds it into every JSON error envelope:
  ```json
  { "error": { "code": "...", "message": "...", "request_id": "..." } }
  ```
- Global exception handlers in [`main.py`](../backend/app/main.py) convert `AppError`, `RequestValidationError`, and uncaught exceptions cleanly without leaking raw Python stack traces to API callers.

> [!NOTE]
> `core/middleware.py` also defines `TimingMiddleware` (`X-Process-Time-Ms`), though only `CORSMiddleware`, `SecurityHeadersMiddleware`, and `RequestIDMiddleware` are currently mounted in [`main.py`](../backend/app/main.py).

### Immutable Audit Trail & Financial-Grade Ledger Integrity
- **Append-Only Audit Logs (`audit_logs`):** Captures `actor_id`, `role`, `action` (`RUN_ALLOCATION`, `OPEN_CYCLE`, `CLOSE_WINDOW`, `REVOKE_ALLOTMENT`, `EXTEND_HOLD`, `TOKEN_REUSE_DETECTED`, `VERIFY_ACCESSIBILITY`, etc.), `target_type`, `target_id`, `before`, `after`, `request_id`, `ip`, and UTC `ts`.
- **Double-Entry Credit Ledger (`credit_ledger`):** Every credit settlement writes `{user_id, cycle_id, event_type, delta, credits_before, credits_after, ref_id, reason, created_at}` guarded by partial unique index `cl_settlement_unique`.

### Query Performance & N+1 Prevention
- **Batched `$in` Lookups:**
  - `_load_snapshot` in `allocation_service.py` batch-fetches `rooms`, `users`, and `credit_accounts` with `$in` instead of querying per application.
  - `run_cascade` pre-loads all `rooms` once before spawning cascade holds.
  - `list_cycle_rooms` in `catalogue.py` uses batched `$in` room lookups.
  - `get_audit_logs` in `admin.py` batch-loads actor emails.
- **Targeted Indexes & TTLs:** 19 collections carry tailored B-tree, compound, partial-unique, and MongoDB TTL auto-expiry indexes ([Data Model & Invariants](data-model-and-invariants.md)).

---

## 8. Determinism & Reproducibility

- [`allocator/core.py`](../backend/app/allocator/core.py) has **zero imports** of `fastapi`, `pymongo`, `random`, or wall-clock APIs.
- Given identical `applications`, `rooms`, `free_room_ids`, `seed`, and `Policy`, `allocate()` and `assign_in_order()` execute bit-for-bit identically across local dev, Docker CI, audit verification CLI ([`scripts/verify_allocation.py`](../backend/scripts/verify_allocation.py)), and the offline Monte Carlo simulator ([`simulator/`](../simulator/simulator/engine.py)).

---

**Related:** [System Architecture](architecture.md) · [Data Model & Invariants](data-model-and-invariants.md) · [Operations, Testing & Runbook](operations-testing-and-runbook.md)
