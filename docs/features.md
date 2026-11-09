# Complete Features & Workflows

FairNest supports **5 distinct RBAC roles** (`STUDENT`, `WARDEN`, `ADMIN`, `AUDITOR`, `SUPER_ADMIN`) plus public authentication flows, automated background jobs, and operator CLI utilities. This document details every implemented feature alongside its exact UI route, API endpoint(s), service layer function, and validation rules.

> [!NOTE]
> `SUPER_ADMIN` passes every role guard (`current_student`, `current_warden`, `current_admin`, `current_auditor`, `current_super_admin`) in [`deps.py`](../backend/app/api/deps.py#L53-L79), while `ADMIN` also passes `current_warden` and `current_auditor`.

---

## 1. Public Authentication & Account Onboarding

| Feature | UI Route & Page | Backend Endpoint(s) | Implementation Details |
|---|---|---|---|
| **Login (Email or Roll No)** | `/login` ([`LoginPage.jsx`](../frontend/src/pages/public/LoginPage.jsx)) | `POST /api/v1/auth/login` | Accepts `email` or `roll_no` identifier + password. Enforces rate limits (`10/min/IP` & `5/min/identifier`), lockout after 5 failures (15 min `LOCKED`), returns JWT access token (in-memory) + sets `HttpOnly; SameSite=Strict` refresh cookie (`7d`). |
| **Account Activation** | `/activate` ([`ActivatePage.jsx`](../frontend/src/pages/public/ActivatePage.jsx)) | `POST /api/v1/auth/activate` | Consumes one-time SHA-256 activation token (`72h` TTL issued by CSV import), enforces password rules (min 10 chars, not common, not equal to identifier), activates account (`INVITED → ACTIVE`), auto-applies any `PENDING` role grant, and initializes `credit_accounts` at `C_INIT=3`. |
| **Forgot Password** | `/forgot` ([`ForgotPasswordPage.jsx`](../frontend/src/pages/public/ForgotPasswordPage.jsx)) | `POST /api/v1/auth/forgot` | Enumeration-safe generic response (`200`). For active users, stores SHA-256 `reset_token_hash` (30m expiry) and queues `PASSWORD_RESET` metadata in `outbox`. Rate-limited `5/min/IP`. |
| **Reset Password** | `/reset` ([`ResetPasswordPage.jsx`](../frontend/src/pages/public/ResetPasswordPage.jsx)) | `POST /api/v1/auth/reset` | Validates reset token hash & expiry, updates Argon2id hash, calls `logout_all` (`token_version += 1` and revokes all refresh tokens). |
| **Change Password & Sessions** | — (API supported) | `POST /api/v1/auth/change-password`<br>`GET /api/v1/auth/sessions`<br>`DELETE /api/v1/auth/sessions/{family_id}`<br>`POST /api/v1/auth/logout`<br>`POST /api/v1/auth/logout-all`<br>`POST /api/v1/auth/refresh` | Lists active device families, revokes single or all sessions, and rotates opaque refresh tokens with family-wide reuse detection (`TOKEN_REUSE`). Origin CSRF checked on `/refresh` & `/logout`. |

---

## 2. Student Workflows (`STUDENT`)

Students can only view hostels, floors, rooms, and cycles within their `hostel_ids` scope (`404` IDOR masking otherwise), and only create/join groups or submit applications in hostels matching `allowed_gender` and `allowed_years` ([`assert_student_eligible_for_hostel`](../backend/app/core/scope.py#L19-L43)).

### 2.1 Dashboard & Notifications
- **Student Home** (`/student`, [`Dashboard.jsx`](../frontend/src/pages/student/Dashboard.jsx)): Displays 4 live summary cards (Current Cycle status & close time, Group membership & size, Active Allotment & hold countdown, Fairness Credit balance) plus top 5 unread notifications.
- **Notification Inbox & Live Badge** (`/notifications`, [`NotificationsPage.jsx`](../frontend/src/pages/student/NotificationsPage.jsx), [`AppShell.jsx`](../frontend/src/components/layout/AppShell.jsx)): Unread badge polls `GET /api/v1/me/notifications/unread-count` every 60s. Supports marking individual alerts read (`POST /api/v1/me/notifications/{id}/read`). Alert types emitted by services/worker include `CYCLE_OPENED`, `GROUP_INVITE`, `ALLOTMENT_HELD`, `CASCADE_OFFER`, `WAITLISTED`, `ALLOTMENT_CONFIRMED`, `ALLOTMENT_DECLINED`, `ALLOTMENT_EXPIRED`, `ALLOTMENT_CANCELLED`, `ALLOTMENT_REVOKED`, and `HOLD_EXTENDED`.

### 2.2 Group Formation & Invitations
- **Page:** `/student/group` ([`MyGroupPage.jsx`](../frontend/src/pages/student/MyGroupPage.jsx))
- **Create Group or Apply Solo** (`POST /api/v1/cycles/{cycle_id}/groups`):
  - Multi-person groups start in `FORMING`; solo mode (`solo: true`) starts immediately in `READY`.
  - DB enforces at most one non-disbanded group led per `(cycle_id, leader_id)` and at most one `ACCEPTED` membership per `(cycle_id, user_id)`.
- **Invite Roommates by Roll No / Email** (`POST /api/v1/groups/{group_id}/invites`):
  - Leader-only, requires open cycle and non-solo group. Enforces max **4** active/invited members (`GROUP_FULL`), active `STUDENT` status, hostel/gender/year eligibility (`NOT_ELIGIBLE`), not already in a group (`ALREADY_IN_GROUP`), and no duplicate pending invite. Reverts `READY`/`SUBMITTED` groups to `FORMING` while invite is pending.
- **Accept / Decline Invites** (`GET /cycles/{id}/invites/mine`, `POST /invites/{id}/accept`, `POST /invites/{id}/decline`):
  - Idempotent via `Idempotency-Key`. Accepting automatically declines all other pending invites for that student in the same cycle (`decline_other_invites`). Once zero `INVITED` memberships remain, group transitions to `READY`.
- **Leave / Remove / Disband** (`DELETE /groups/{id}/members/{uid}`, `DELETE /groups/{id}`):
  - Leader cannot leave (must disband, which sets `DISBANDED`, releases memberships to `LEFT`, and withdraws any draft/submitted application).

### 2.3 Ranked Room & Floor Preferences
- **Page:** `/student/preferences` ([`PreferencesPage.jsx`](../frontend/src/pages/student/PreferencesPage.jsx), [`RoomGrid.jsx`](../frontend/src/components/preferences/RoomGrid.jsx), [`RankList.jsx`](../frontend/src/components/preferences/RankList.jsx))
- **Visual Room Browser & Filtering:** Calls `GET /cycles/{id}/rooms` and `GET /cycles/{id}/floors`. Supports floor dropdown filter and `Size matches group` checkbox enforcing `fill_rule` (`EXACT` vs `AT_MOST`). Rooms display live availability status and bed capacities.
- **Mixed Room + Floor Preference Ranking (Max 10):**
  - Leaders click rooms in `RoomGrid` or select an entire floor (`Add Floor`) to build an ordered list of `ROOM` and `FLOOR` choices, then reorder via drag-and-drop or keyboard arrows (`@dnd-kit`) in `RankList`.
  - `FLOOR` choices resolve dynamically at allocation time to the **lowest natural-sorted available room number** on that floor matching group size.
- **Fallback Policy Selection:**
  - `ANY_ELIGIBLE`: Auto-assigns the tightest-fitting available eligible room (`rank_obtained = len(choices) + 1`) if all ranked preferences are exhausted.
  - `NONE`: Waitlists group rather than assigning an unranked room (`+2` credits if still unallotted at settlement).
- **Versioned Draft Save, Submit & Withdraw:**
  - `PUT /groups/{id}/application` saves `DRAFT` (or updates an already `SUBMITTED` app while open) with optimistic concurrency check (`version` / `If-Match` → `409 VERSION_CONFLICT`).
  - `POST /groups/{id}/application/submit` requires all invites resolved (`GROUP_NOT_READY` if pending invites exist), ≥1 ranked choice, computes `credit_snapshot`, `weight`, and `tier`, and sets `SUBMITTED` (`Idempotency-Key` guarded).
  - `POST /groups/{id}/application/withdraw` sets `WITHDRAWN` and reverts group to `READY`.

### 2.4 Allotment Response, Unanimous Confirmation & Cancellation (Zero Payment)
- **Page:** `/student/allotment` ([`MyAllotmentPage.jsx`](../frontend/src/pages/student/MyAllotmentPage.jsx), [`HoldPanel.jsx`](../frontend/src/components/allotment/HoldPanel.jsx), [`CountdownTimer.jsx`](../frontend/src/components/common/CountdownTimer.jsx))
- **Hold Response (`HELD`):**
  - Displays room details, preference rank obtained, round number, live expiration countdown (`HoldPanel`), and real-time `PENDING`/`ACCEPTED`/`DECLINED` chips per member (polled every 30s).
  - **Accept (`POST /allotments/{id}/accept`):** Any group member accepts independently (idempotent on retries and concurrency-safe). The **final accepting member** atomically transitions `room_inventory` (`HELD → CONFIRMED`), `allotment` (`HELD → CONFIRMED`), and `application` (`ALLOTTED → CONFIRMED`).
  - **Decline (`POST /allotments/{id}/decline`):** Any single member can decline, immediately releasing the room (`HELD → AVAILABLE`), marking the application `FORFEITED`, notifying all members, and running `run_cascade` synchronously.
- **Self-Cancellation (`CONFIRMED`):**
  - Before `final_deadline_at` and before cycle `CLOSED`/`SETTLED`, confirmed students can cancel (`POST /allotments/{id}/cancel`), releasing the room (`CONFIRMED → AVAILABLE`), forfeiting their application (`LATE_CANCELLED: -1` credit at settlement), and triggering cascade allocation.

### 2.5 Fairness Credits & Personal Allocation Explanation
- **Credits & Ledger** (`/student/credits`, [`CreditsPage.jsx`](../frontend/src/pages/student/CreditsPage.jsx)): Calls `GET /api/v1/me/credits` showing current balance (`[0, 10]`, initial `3`) and paginated chronological ledger (`cycle_id`, `event_type`, `delta`, `credits_before`, `credits_after`, `reason`).
- **How Fairness Works (Personalized Explanation)** (`/student/fairness`, [`FairnessExplanationPage.jsx`](../frontend/src/pages/student/FairnessExplanationPage.jsx)): Calls `GET /api/v1/me/fairness`. Shows student's credits, group weight, Priority Tier (`0` Accessibility vs `1` Standard), exact draw position (`#order_index + 1 / total_applicants`), expected credit delta, **rank-by-rank choice explanation table** (`MATCHED` vs `SKIPPED` with plain-English reason per choice), and FAQ accordion.

---

## 3. Warden Workflows (`WARDEN`, plus `ADMIN` & `SUPER_ADMIN`)

All Warden routes enforce [`assert_staff_scope`](../backend/app/core/scope.py#L46-L61) against `managed_hostel_ids` (`403 HOSTEL_SCOPE_DENIED` + audit log if violated).

| Feature | UI Route & Page | Backend Endpoint(s) | Behavior |
|---|---|---|---|
| **Hostel Catalog & Floors** | `/warden/rooms` ([`RoomsPage.jsx`](../frontend/src/pages/warden/RoomsPage.jsx)) | `GET /hostels`, `GET /hostels/{id}/floors`, `GET /hostels/{id}/rooms`, `POST /admin/hostels/{id}/floors` | Lists scoped hostels with occupancy cards, floor switcher, natural-sorted room table, and floor creation dialog. (`POST /admin/hostels` requires `ADMIN`/`SUPER_ADMIN`). |
| **Comma-List Batch Room Entry + Dry-Run** | `/warden/rooms` ([`RoomListInput.jsx`](../frontend/src/components/rooms/RoomListInput.jsx)) | `POST /admin/floors/{id}/rooms/from-list?dry_run=...` | Parses up to 200 comma/newline tokens (supporting `room:capacity` overrides like `201, 202:3, A-10:4`). Live 350ms debounced dry-run groups tokens into `to_create`, `already_exist`, `duplicates_in_input`, and `invalid`. Commit runs inside an ACID transaction (`skip_existing` toggle + audit log). Range endpoint `/rooms/bulk` (`from_no`..`to_no`) also exposed via API. |
| **Room Maintenance Toggle & Safety Guard** | `/warden/rooms` | `PATCH /admin/rooms/{room_id}` | Updates `status` (`ACTIVE` ↔ `MAINTENANCE`), `capacity` (1–8), `features`, `room_no`. Setting `MAINTENANCE` blocks if any live cycle holds/confirms the room (`409 ROOM_BUSY`); otherwise marks `AVAILABLE` inventory `BLOCKED`. Returning to `ACTIVE` restores `BLOCKED → AVAILABLE`. |
| **Accessibility Priority Verification** | `/warden/accessibility` ([`AccessibilityQueuePage.jsx`](../frontend/src/pages/warden/AccessibilityQueuePage.jsx)) | `GET /warden/users`, `PUT /warden/users/{id}/accessibility` | Searchable roster of students in warden's `managed_hostel_ids`. Verifies/revokes `accessibility_verified` (Tier 0 placement) with an audit note persisted to `audit_logs`. |
| **Allotment Monitor, One-Time Hold Extension & Revoke** | `/warden/allotments` ([`AllotmentMonitorPage.jsx`](../frontend/src/pages/warden/AllotmentMonitorPage.jsx)) | `GET /admin/allotments`, `POST /admin/allotments/{id}/extend`, `POST /admin/allotments/{id}/revoke` | Polls every 30s, filters by status (`HELD`, `CONFIRMED`, etc.), displays accepted vs pending counts & deadlines. **Extend Hold** allows one manual +1–72h extension (`admin_extended: true`, reason ≥10 chars). **Revoke** frees `HELD`/`CONFIRMED` rooms for cascade, marks app `WAITLISTED` with `reinsert=True`, incurs `0` credit penalty, and notifies all members. |
| **Real-Time Occupancy Analytics** | `/warden/occupancy` ([`OccupancyPage.jsx`](../frontend/src/pages/warden/OccupancyPage.jsx)) | `GET /reports/occupancy` | Optional cycle filter. Per-hostel linear occupancy bars (Confirmed / Held / Available / Total beds) and per-floor breakdown table (`total_beds`, `occupied_beds`, `held_beds`, `available` rooms, `blocked` rooms). |

---

## 4. Admin Workflows (`ADMIN`, plus `SUPER_ADMIN`)

Admins manage the end-to-end release lifecycle, fairness parameters, allocation execution, cascades, manual overrides, and settlement for their `managed_hostel_ids` (and have access to all Warden and Auditor views).

| Feature | UI Route & Page | Backend Endpoint(s) | Behavior |
|---|---|---|---|
| **Allotment Cycle CRUD & Editor** | `/admin/cycles`, `/admin/cycles/:cycleId` ([`CycleListPage.jsx`](../frontend/src/pages/admin/CycleListPage.jsx), [`CycleEditorPage.jsx`](../frontend/src/pages/admin/CycleEditorPage.jsx)) | `GET /cycles`, `POST /admin/cycles`, `PUT /admin/cycles/{id}`, `POST /admin/cycles/{id}/open`, `/close-window`, `/extend`, `/reopen`, `/cancel`, `/settle` | Create/edit `DRAFT`/`SCHEDULED` cycles (custom `policy`, `freeze_hours`, optional `room_ids` subset). Actions enforce state machine transitions: Open (snapshots live inventory + commits seed), Close Early (snapshots credits/tiers), Extend close timestamp, Reopen (only pre-allocation), Cancel (un-lives inventory), and Settle (requires 0 `HELD` allotments, marks lingering waitlisted `UNALLOTTED`, applies clamped credit deltas + `credit_ledger` idempotently). |
| **Automated Release Scheduler** | `/admin/scheduler` ([`ReleaseSchedulerPage.jsx`](../frontend/src/pages/admin/ReleaseSchedulerPage.jsx)) | `POST /admin/cycles/{id}/schedule` | Schedules `DRAFT`/`SCHEDULED` cycle open/close datetimes (`MIN_WINDOW_MINUTES = 60` validation, not in past). Worker transitions automatically. |
| **Allocation Console (Preview → Run → Cascade)** | `/admin/allocation` ([`AllocationConsolePage.jsx`](../frontend/src/pages/admin/AllocationConsolePage.jsx)) | `POST /admin/cycles/{id}/preview-allocation`, `POST /admin/cycles/{id}/allocate` | Stepper console for `APPLICATIONS_CLOSED` cycles. **Preview** runs ephemeral-seed dry run without DB writes. **Run Allocation** transitions via `ALLOCATING` lock, executes Round-1 Weighted RSD, creates `HELD` allotments, records `allocation_runs`, reveals `seed_secret`, and logs hashes. |
| **Manual Cascade Execution** | `/admin/cascade` ([`CascadePage.jsx`](../frontend/src/pages/admin/CascadePage.jsx)) | `POST /admin/cycles/{id}/cascade` | Invokes [`run_cascade`](../backend/app/services/allotment_service.py#L496-L675) to match `AVAILABLE` rooms to `WAITLISTED` groups strictly in original Round-1 `(not reinsert, order_index)` order without re-randomization. |
| **Manual Application Assignment** | — (API supported) | `POST /admin/applications/{id}/assign` | Admin fallback to offer a specific `AVAILABLE` room to a `WAITLISTED`/`UNALLOTTED`/`SUBMITTED` application (validated against `fill_rule`, creates round-99 `HELD` allotment inside ACID txn). |
| **User Directory & Account Controls** | `/admin/users` ([`UsersPage.jsx`](../frontend/src/pages/admin/UsersPage.jsx)) | `GET /admin/users`, `PUT /admin/users/{id}/{enable,disable,unlock}` | Searchable scoped student directory + enable/disable/unlock actions. Disabling revokes tokens (`token_version += 1`). Protects last active `SUPER_ADMIN`. |
| **Fairness & Rejection Reports** | `/admin/fairness` ([`FairnessDashboardPage.jsx`](../frontend/src/pages/admin/FairnessDashboardPage.jsx)) | `GET /reports/fairness`, `GET /reports/rejections` | Recharts visualizations + KPI cards (`total_applications`, `confirmed`, `success_rate`, `jain_index`, `top_1_rate`, `average_rank`, `success_by_band`, `rank_distribution`, `demand_vs_supply`, `credit_distribution`). |

---

## 5. Auditor Workflows (`AUDITOR`, plus `ADMIN` & `SUPER_ADMIN`)

Global Auditors (`managed_hostel_ids: []`) can audit all hostels across the system; hostel-scoped Auditors are limited to `managed_hostel_ids`.

| Feature | UI Route & Page | Backend Endpoint(s) | Behavior |
|---|---|---|---|
| **Cryptographic Allocation Verifier** | `/auditor/verify` ([`VerifyAllocationPage.jsx`](../frontend/src/pages/auditor/VerifyAllocationPage.jsx)) | `GET /api/v1/cycles/{id}/audit` | Available once cycle reaches `ALLOTMENT_ACTIVE`/`CLOSED`/`SETTLED` (`409 SEED_NOT_REVEALED` earlier). Independently checks `seed_ok` (`SHA-256(seed) == seed_commitment`), `input_ok` (recomputes canonical Round-1 `input_hash` from frozen snapshot), and `output_ok` (re-executes `allocate()` and matches `output_hash`). Displays PASS/FAIL chips and full SHA-256 digests. |
| **Audit Log Explorer** | `/auditor/audit`, `/admin/audit` ([`AuditLogPage.jsx`](../frontend/src/pages/admin/AuditLogPage.jsx)) | `GET /api/v1/admin/audit-logs` | Filterable by `action`, `target_type` (or `entity_type`), and `actor_id`. Enriches actor email addresses and renders expandable JSON diff drawers (`role`, `before`, `after`, `ip`). |
| **Fairness Dashboard & Rejection Analytics** | `/auditor/fairness` | `GET /reports/fairness`, `GET /reports/rejections` | Identical read-only statistical dashboard across permitted cycles. |

---

## 6. Super Admin Workflows (`SUPER_ADMIN`)

| Feature | UI Route & Page | Backend Endpoint(s) | Behavior |
|---|---|---|---|
| **Hierarchical Role Grants & Revocation** | `/superadmin/roles` ([`RolesAndAccessPage.jsx`](../frontend/src/pages/superadmin/RolesAndAccessPage.jsx)) | `GET /admin/role-grants`, `POST /admin/role-grants`, `DELETE /admin/role-grants/{id}` | Grants `WARDEN`, `ADMIN`, `AUDITOR`, `SUPER_ADMIN`, or `STUDENT` by email. Grants for existing users apply immediately (`ACTIVE`) and bump `token_version`; grants for non-activated emails sit `PENDING` and auto-apply upon `/auth/activate`. Note: `ADMIN` can also call `POST /admin/role-grants` via API exclusively to assign `WARDEN` inside their own `managed_hostel_ids`. Self-grants are forbidden, and revoking the last active `SUPER_ADMIN` returns `409 LAST_SUPER_ADMIN`. |
| **Bulk Student CSV Import** | `/superadmin/users` (`UsersPage.jsx` import dialog) | `POST /api/v1/admin/users/import` | Accepts UTF-8 BOM-safe CSV (`roll_no,name,email,gender,year,program,hostel_code`, plus `student_id`/`full_name` aliases, pipe-delimited hostel codes `BH1\|BH2`). Upserts profiles, creates `INVITED` students with `C_INIT=3` credit accounts and 72h activation tokens, logs `IMPORT_STUDENTS_CSV`. |
| **User Hostel Scope Reassignment** | — (API supported) | `PUT /api/v1/admin/users/{id}/hostels` | Updates student `hostel_ids` and staff `managed_hostel_ids` after verifying hostel existence, immediately invalidates active sessions (`token_version += 1`), and writes audit log `UPDATE_USER_HOSTELS`. |
| **Global Hostel Creation** | `/warden/rooms` (`+ New Hostel`) | `POST /api/v1/admin/hostels` | Creates new hostels with unique uppercase `code`, `allowed_gender` (`M`, `F`, `ANY`), and `allowed_years` eligibility filter (`409 HOSTEL_CODE_EXISTS` on duplicate). |

---

## 7. Automated Worker & Operator CLI Features

| Component | Entrypoint | Capabilities |
|---|---|---|
| **Background Worker** | `python -m app.worker` ([`worker.py`](../backend/app/worker.py)) | 30-second loop performing: one-time +10m hold grace extensions, hold expiry → cascade, automatic scheduled cycle opening (`SCHEDULED → APPLICATIONS_OPEN`), automatic window closing (`APPLICATIONS_OPEN → APPLICATIONS_CLOSED`), automatic cycle closing (`ALLOTMENT_ACTIVE → CLOSED` + releasing `is_live: false`), and 10-minute invariant verification. |
| **Super Admin Bootstrap CLI** | `scripts/create_super_admin.py` | Idempotently creates or elevates `SUPER_ADMIN` with a ≥12-character password and ensures DB indexes/validators. |
| **Demo Dataset Loader CLI** | `scripts/load_demo_data.py` | Seeds 4 hostels (`BH1`, `BH2`, `GH1`, `GH2`), 5 floors each (~100 total beds), and 300 active demo students (`student1..300@college.edu` / `demo_password_123`) with initial credits. |
| **Allocation Verifier CLI** | `scripts/verify_allocation.py --cycle <id>` | Operator CLI counterpart to `/cycles/{id}/audit`; exits `0` on full cryptographic verification pass and `1` on mismatch. |
| **DB Invariant Checker CLI** | `scripts/check_invariants.py` | Verifies 6 global MongoDB invariants across active allotments, room capacity, single-live-release lock, single MAIN run per cycle, credit bounds, accepted members, and single active membership per cycle. |
| **Health Probes** | `GET /api/v1/health/live`, `/ready` ([`health.py`](../backend/app/api/routes/health.py)) | Liveness returns `200 ok`; readiness executes MongoDB `ping` and returns `503` if disconnected. |
