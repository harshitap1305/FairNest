# Operations, Testing & Runbook

This guide covers environment configuration, Docker Compose and native local execution, operational CLI scripts, verification checklists, failure recovery procedures, and the complete automated test inventory.

---

## 1. Environment Configuration (`.env`)

Copy [`.env.example`](../.env.example) to `.env` at the repository root and update `JWT_SECRET` for non-local environments:

| Variable | `.env.example` / Compose Value | Code Default (`config.py`) | Purpose |
|---|---|---|---|
| `MONGO_URI` | `mongodb://mongo:27017/?replicaSet=rs0` | `mongodb://localhost:27017/?replicaSet=rs0` | Replica-set URI required for `session.with_transaction()`. |
| `MONGO_DB` | `hostel_allotment` | `fairnest` | Target MongoDB database name. |
| `JWT_SECRET` | `change-me-to-a-long-random-string-at-least-32-chars` | Change-me placeholder | HS256 signing key for 15m access tokens. |
| `JWT_ACCESS_MINUTES` | `15` | `15` | Access token TTL in minutes. |
| `REFRESH_DAYS` | `7` | `7` | Refresh cookie + DB `rt_ttl` lifetime in days. |
| `COOKIE_SECURE` | `false` (`true` behind HTTPS) | `False` | Sets `Secure` attribute on `refresh_token` cookie. |
| `CORS_ORIGINS` | `http://localhost:5173` | `http://localhost:5173` | Comma-separated allowlist for CORS & CSRF Origin check. |
| `FREEZE_HOURS_DEFAULT` | `48` | `48` | Default unanimous confirmation window when creating cycles. |
| `LOG_LEVEL` | `INFO` | `INFO` | `structlog` JSON verbosity. |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | `admin@iitbhilai.demo` | `""` | Default bootstrap hint email. |
| `ALLOWED_EMAIL_DOMAINS` | `iitbhilai.demo` | `""` | Optional comma-separated institutional email domain whitelist. |
| `C_INIT` / `C_MIN` / `C_MAX` | *(optional env overrides)* | `3` / `0` / `10` | Fairness credit initial value and hard clamp bounds. |
| `MIN_WINDOW_MINUTES` | *(optional env override)* | `60` | Minimum allowed scheduled open-to-close window length. |

---

## 2. Running the Stack

### Option A: Docker Compose (Recommended Production-Like Stack)

[`docker-compose.yml`](../docker-compose.yml) defines 5 services (`mongo`, `mongo-init`, `backend`, `worker`, `frontend`):

```bash
# Build & launch MongoDB rs0 (with automated rs.initiate()), API, Worker, and Nginx+SPA
make up
# Or: docker compose up --build -d

# Seed initial SUPER_ADMIN + demo dataset (4 hostels, 100 beds, 300 students)
make seed

# Tail API & Worker structured JSON logs
make logs

# Tear down stack and volumes cleanly
make down
```

- **Frontend UI:** `http://localhost:5173` (Nginx serves SPA and proxies `/api/` → `backend:8000`).
- **Backend API Direct:** `http://localhost:8000/api/v1/health/ready`.

### Option B: Native Local Development

Requires a running MongoDB instance initialized as replica set `rs0` (`mongod --replSet rs0` + `rs.initiate()`):

```bash
# 1. Backend API
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. Background Worker (separate terminal)
cd backend
python -m app.worker

# 3. Frontend Dev Server (Vite proxies /api -> localhost:8000 via vite.config.js)
cd frontend
npm install && npm run dev
```

---

## 3. Operational CLI Scripts (`backend/scripts/`)

| Script | Purpose & Usage | Exit Behavior |
|---|---|---|
| [`create_super_admin.py`](../backend/scripts/create_super_admin.py) | Bootstraps or promotes a `SUPER_ADMIN` user (`--email`, `--password`, `--name`, or interactive prompt; enforces ≥12-character password) and initializes indexes/validators. | Exits `0` after idempotent upsert. |
| [`load_demo_data.py`](../backend/scripts/load_demo_data.py) | Seeds 4 hostels (`BH1`, `BH2`, `GH1`, `GH2`), 5 floors each (~100 total beds), and 300 active demo students (`student1@iitbhilai.demo`–`student300@iitbhilai.demo`, password `demo_password_123`) with initial credit accounts (`3`). | Exits `0` idempotently. |
| [`verify_allocation.py`](../backend/scripts/verify_allocation.py) | Standalone cryptographic Round-1 verifier:<br>`python scripts/verify_allocation.py --cycle <CYCLE_ID>` | Prints `seed_ok`, `input_ok`, `output_ok`, hashes; exits `0` on full pass, `1` on tamper/mismatch. |
| [`check_invariants.py`](../backend/scripts/check_invariants.py) | Audits all 6 global DB invariants (`HELD`/`CONFIRMED` room exclusivity + capacity, single `is_live` per room, single `MAIN` run per cycle, credit `[C_MIN, C_MAX]` bounds, 100% `ACCEPTED` on `CONFIRMED` allotments, ≤1 `ACCEPTED` membership per `(cycle_id, user_id)`). | Prints `All invariants OK ✓` (`0`) or lists violations (`1`). |

---

## 4. Production Deployment & Lifecycle Runbook

### Pre-Release Checklist (Before Opening a Hostel Cycle)
1. Confirm `GET /api/v1/health/ready` returns `{"status": "ok", "db": "connected"}` and `worker` is running (`run_invariant_check` runs every `10m`).
2. Verify physical rooms on [`/warden/rooms`](features.md#3-warden-workflows-warden-plus-admin--super_admin) (`ACTIVE` vs `MAINTENANCE`).
3. Verify any accessibility priority requests in `/warden/accessibility` **before** `close-window` runs (because Tier `0` vs Tier `1` is snapshotted onto `SUBMITTED` applications at `close-window`).
4. Ensure overlapping cycles on the same physical rooms are closed/settled (`is_live: false`), avoiding `409 ROOM_IN_LIVE_RELEASE`.

### Incident Recovery Procedures

| Incident | Diagnosis | Recovery Procedure |
|---|---|---|
| **Allocation failed mid-flight leaving cycle in `ALLOCATING`** | Check `backend` JSON logs by `X-Request-ID`. | `allocation_service.run_allocation` contains an `except:` rollback to `APPLICATIONS_CLOSED`. If the container was `SIGKILL`ed before reaching `except:`, verify no `MAIN` run was inserted in `allocation_runs`, then safely reset `cycles.status` back to `APPLICATIONS_CLOSED` via mongosh and retry `/allocate`. |
| **Room reported unsafe / uninhabitable after allotment** | Student reports maintenance emergency on `HELD` or `CONFIRMED` room. | Do **not** toggle maintenance first (`409 ROOM_BUSY`). Open `/warden/allotments`, **Revoke** the allotment with an audit reason (≥10 chars) to put the displaced group at the front of the next cascade (`reinsert=True`, `0` penalty), then mark the room `MAINTENANCE` (`BLOCKED`). |
| **Student group stuck awaiting 1 confirmation before deadline** | Roommate has temporary connectivity/travel issue. | Worker automatically applies one `+10m` grace extension when expired if a member is still `PENDING`. If more time is required, Warden/Admin can click **Extend Hold** (+1–72h, once per allotment) in `/warden/allotments`. |
| **Audit hash check (`verify_allocation`) fails** | Compare `computed_input_hash` vs `stored_input_hash` and `seed_ok`. | Inspect `audit_logs` around cycle `RUN_ALLOCATION`, `CLOSE_WINDOW`, and user accessibility updates. Never manually mutate `applications.weight`, `tier`, or `ranked_choices` after `APPLICATIONS_CLOSED`. |
| **Account locked after failed logins** | Student hit 5 wrong passwords (`LOCKED` for 15m). | Wait 15m or unlock immediately in `/admin/users` (`PUT /api/v1/admin/users/{id}/unlock`). |
| **Suspected session hijacking (`TOKEN_REUSE`)** | `audit_logs` contains `TOKEN_REUSE_DETECTED`. | Reuse detection already revoked the entire refresh token family; instruct the user to change password (`POST /auth/change-password`) which bumps `token_version` globally. |

---

## 5. Testing, Linting & Build Verification

### Full Automated Test Inventory (**38 Verified Tests**)

| Suite | File | Count | What Is Verified |
|---|---|---|---|
| **Backend Unit — Allocator** | [`test_allocator.py`](../backend/tests/unit/test_allocator.py) | `10` | Weighted RSD determinism, statistical weight bias (`10 > 0`), Tier-0 isolation, natural room sort (`21 < 201`), `FLOOR` lowest-room pickup, `EXACT` vs `AT_MOST`, spare-capacity fallback, `reinsert=True` cascade precedence without re-randomization, `compute_weight` (`MEAN`/`MIN`/`MAX`), `apply_carry_over`. |
| **Backend Unit — Fairness** | [`test_fairness.py`](../backend/tests/unit/test_fairness.py) | `5` | Rank deltas, fallback `+1`, `UNALLOTTED +2`, `FORFEITED -2`, `LATE_CANCELLED -1`, `REVOKED 0`, clamping `[0, 10]`, Jain index equality/dispersion. |
| **Backend Unit — Parser** | [`test_room_parser.py`](../backend/tests/unit/test_room_parser.py) | `4` | Comma/newline room tokenization, `:capacity` override parsing, duplicate detection, invalid token & `>200` cap rejection. |
| **Backend Integration — Lifecycle** | [`test_allotments.py`](../backend/tests/integration/test_allotments.py) | `5` | End-to-end Round-1 allocation, commit–reveal audit verification (`seed_ok`, `input_ok`, `output_ok`), zero-payment unanimous confirm (`HELD → CONFIRMED`), decline cascade refill, self-cancel & cutoff guard, idempotent cycle credit settlement (`credit_ledger`), admin revoke rescue (`reinsert=True`), worker auto-grace extension (`try_extend_grace`) + expiry cascade. |
| **Backend Concurrency** | [`test_concurrent_accept.py`](../backend/tests/concurrency/test_concurrent_accept.py) | `3` | Concurrent `asyncio.gather` member accepts promote cleanly once (`CONFIRMED`), `accept + decline` race preserves room integrity without double-booking, concurrent `Idempotency-Key` replay & payload conflict (`409 IDEMPOTENCY_CONFLICT`). |
| **Backend Security & RBAC** | [`test_rbac.py`](../backend/tests/security/test_rbac.py) | `5` | Student `404` IDOR concealment on cross-hostel rooms/cycles/groups, Warden `403 HOSTEL_SCOPE_DENIED`, global vs scoped Auditor visibility, last active `SUPER_ADMIN` `409 LAST_SUPER_ADMIN` lockout protection, refresh token family revocation on replay (`401 TOKEN_REUSE`). |
| **Simulator Determinism** | [`test_determinism.py`](../simulator/tests/test_determinism.py) | `6` | Same-seed bit-identical replay, zero payment references, cascade waitlist refill consistency, multi-cycle bounded credit invariants, scenario config loading. |

### Execution Commands

```bash
# Containerized CI test run (spins up isolated Mongo rs0 + backend pytest via docker-compose.test.yml)
make test

# Native backend pytest (requires local MongoDB rs0 at MONGO_URI)
cd backend && pytest -v

# Native simulator pytest (no DB required)
cd simulator && PYTHONPATH=../backend:. pytest -v

# Linters & Frontend Production Build
make lint
cd frontend && npm run build
```

---

**Related:** [System Architecture](architecture.md) · [Data Model & Invariants](data-model-and-invariants.md) · [Simulator & Fairness Analysis](simulator-and-fairness-analysis.md)
