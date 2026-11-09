# REST API Reference (`/api/v1`)

All FairNest HTTP endpoints are mounted under the `/api/v1` prefix (except Nginx's `/health` check alias or direct `/api/v1/health/*` routes). Every error follows a unified JSON envelope with request tracing:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable explanation",
    "request_id": "uuid-v4"
  }
}
```

> [!IMPORTANT]
> **Zero-Payment Booking Flow:** No `/pay` or billing endpoints exist. Room offers transition purely via `/allotments/{allotment_id}/accept`, `/decline`, `/cancel`, or staff `/revoke` & `/extend`.

---

## Common Headers & Cookies

| Header / Cookie | Endpoints | Purpose |
|---|---|---|
| `Authorization: Bearer <jwt>` | All authenticated routes | 15-minute HS256 access token carrying `sub`, `role`, `tv`, `jti`, `iat`, `exp`. |
| `Cookie: refresh_token=<opaque>` | `POST /auth/refresh`, `/auth/logout` | `HttpOnly; SameSite=Strict; path=/api/v1/auth` 7-day rotated opaque token. |
| `Idempotency-Key: <string>` | `/invites/{id}/accept`, `/invites/{id}/decline`, `/groups/{id}/application/{submit,withdraw}`, `/allotments/{id}/{accept,decline,cancel}` | Optional replay key (24h TTL per user). Same key + mismatched body → `409 IDEMPOTENCY_CONFLICT`. |
| `If-Match: <int>` | `PUT /groups/{group_id}/application` | Optimistic lock against application `version` (also accepted via JSON body `version`). Mismatch → `409 VERSION_CONFLICT`. |
| `X-Request-ID: <string>` | All routes | Propagated or auto-generated UUIDv4 returned in response header and `error.request_id`. |

---

## 1. Health Probes (`health.py`)

| Method & Path | Auth | Success Response | Behavior |
|---|---|---|---|
| `GET /api/v1/health/live` | Public | `200 {"status": "ok"}` | Liveness probe. |
| `GET /api/v1/health/ready` | Public | `200 {"status": "ok", "db": "connected"}` | Runs MongoDB `ping`; returns `503 {"status": "error", "detail": "..."}` on failure. |

---

## 2. Authentication, Sessions, Profile & Fairness (`auth.py`)

| Method & Path | Auth / Rate Limit | Request Body / Params | Response / Side Effects |
|---|---|---|---|
| `POST /api/v1/auth/login` | Public (`10/min/IP`, `5/min/id`) | `{identifier, password}` (`email` or `roll_no`) | Sets `refresh_token` cookie; returns `{access_token, token_type, user_id, role, name}`. 5 failures → 15m `LOCKED`. |
| `POST /api/v1/auth/activate` | Public (`5/min/IP`) | `{token, password}` | Activates `INVITED` account, validates password (≥10 chars), applies pending role grant, initializes credits (`C_INIT=3`). |
| `POST /api/v1/auth/refresh` | Cookie + Origin CSRF | None | Rotates refresh token family; replaying a revoked token revokes whole family & returns `401 TOKEN_REUSE`. Returns `{access_token, token_type}`. |
| `POST /api/v1/auth/logout` | Cookie + Origin CSRF | None | Revokes token family and clears `refresh_token` cookie. |
| `POST /api/v1/auth/logout-all` | Bearer | None | Bumps `token_version += 1`, revokes all user refresh tokens, clears cookie. |
| `GET /api/v1/auth/sessions` | Bearer | None | Lists active sessions (`family_id, ip, user_agent, created_at, expires_at`). |
| `DELETE /api/v1/auth/sessions/{family_id}` | Bearer | Path `family_id` | Revokes a single device session family (`404` if missing). |
| `POST /api/v1/auth/forgot` | Public (`5/min/IP`) | `{email}` | Always `200` (enumeration-safe). Stores SHA-256 30m reset token & queues `outbox` `PASSWORD_RESET`. |
| `POST /api/v1/auth/reset` | Public (`5/min/IP`) | `{token, new_password}` | Verifies reset token, updates Argon2id hash, triggers `logout_all`. |
| `POST /api/v1/auth/change-password` | Bearer | `{old_password, new_password}` | Verifies current password, updates hash, triggers `logout_all`. |
| `GET /api/v1/me` | Bearer | None | Profile (`id, roll_no, email, name, role, hostel_ids, managed_hostel_ids, status, gender, year, program, accessibility_verified, credits, last_login_at`). |
| `GET /api/v1/me/credits` | Bearer | `?skip=0&limit=50` | `{credits, ledger: [...]}` descending chronologically. |
| `GET /api/v1/me/fairness` | Bearer | `?cycle_id=...` | Personalized fairness explanation: `credits, policy, cycle, application, allotment, expected_credit_delta, expected_event_type, choice_explanations`. |
| `GET /api/v1/me/notifications` | Bearer | `?unread_only=false&unread=false&limit=50` | Returns user notification list (supports both `unread_only` & `unread`). |
| `GET /api/v1/me/notifications/unread-count` | Bearer | None | `{"unread_count": int}`. |
| `POST /api/v1/me/notifications/{notification_id}/read` | Bearer | Path `notification_id` | Marks notification `read: true`. |

---

## 3. Catalogue, Hostels, Floors & Rooms (`catalogue.py`)

| Method & Path | Role & Scope | Params / Body | Response / Error Codes |
|---|---|---|---|
| `GET /api/v1/hostels` | Any Bearer (`filter_hostel_ids_for_user`) | None | List of permitted active hostels. |
| `GET /api/v1/hostels/{hostel_id}` | Any Bearer (`assert_user_hostel_scope`) | Path `hostel_id` | Hostel doc (`404` if student outside hostel, `403 HOSTEL_SCOPE_DENIED` if staff). |
| `GET /api/v1/hostels/{hostel_id}/floors` | Any Bearer (`assert_user_hostel_scope`) | Path `hostel_id` | Floors ordered by `floor_no`. |
| `GET /api/v1/hostels/{hostel_id}/rooms` | `WARDEN+` (`assert_staff_scope`) | `?floor_id=&floor_no=&status=` | Natural-sorted physical rooms (`(floor_no, _room_sort_key(room_no))`). |
| `GET /api/v1/cycles/{cycle_id}/floors`<br>`GET /api/v1/cycles/{cycle_id}/hostels/{hostel_id}/floors` | Any Bearer (`assert_user_hostel_scope`) | Path `cycle_id`, optional `hostel_id` | Floors enriched with `total_rooms`, `available_rooms`, `capacities` in release. |
| `GET /api/v1/cycles/{cycle_id}/rooms` | Any Bearer (`assert_user_hostel_scope`) | `?hostel_id=&floor_no=&capacity=&status=` | Natural-sorted cycle inventory joined with room metadata (`room_id, room_no, floor_no, capacity, status, features`). |
| `GET /api/v1/cycles/{cycle_id}/availability-summary` | Any Bearer (`assert_user_hostel_scope`) | Path `cycle_id` | Status counts map (`{AVAILABLE, HELD, CONFIRMED, BLOCKED}`). |
| `POST /api/v1/admin/hostels` | `ADMIN` / `SUPER_ADMIN` | `{name, code, allowed_gender?, allowed_years?}` | Creates hostel (`409 HOSTEL_CODE_EXISTS`). |
| `POST /api/v1/admin/hostels/{hostel_id}/floors` | `WARDEN+` (`assert_staff_scope`) | `{floor_no, label?}` | Creates floor (`409 FLOOR_ALREADY_EXISTS`). |
| `POST /api/v1/admin/floors/{floor_id}/rooms/from-list` | `WARDEN+` (`assert_staff_scope`) | `?dry_run=false`<br>`{room_numbers, capacity=2, features=[], dry_run?, skip_existing?}` | Parses ≤200 tokens (`101, 102:3, A-10`). Dry-run returns `{to_create, duplicates_in_input, already_exist, invalid}`; commit inserts in ACID txn (`409 ROOMS_ALREADY_EXIST`). |
| `POST /api/v1/admin/floors/{floor_id}/rooms/bulk` | `WARDEN+` (`assert_staff_scope`) | `{from_no, to_no, capacity=2, features=[]}` | Numeric range batch insert (max 200). |
| `PATCH /api/v1/admin/rooms/{room_id}` | `WARDEN+` (`assert_staff_scope`) | `{status?, capacity?, features?, room_no?}` | Toggles `ACTIVE`/`MAINTENANCE` & syncs live inventory (`BLOCKED`/`AVAILABLE`). Rejects `MAINTENANCE` if room is `HELD`/`CONFIRMED` (`409 ROOM_BUSY`). |

---

## 4. Cycles, Allocation & Cryptographic Audit (`cycles.py`)

| Method & Path | Role & Scope | Params / Body | Response / Error Codes |
|---|---|---|---|
| `GET /api/v1/cycles` | Any Bearer (`filter_hostel_ids_for_user`) | `?status=&hostel_id=` | List of redacted cycles + `room_counts` + `stats`. |
| `GET /api/v1/cycles/{cycle_id}` | Any Bearer (Student `404` / Staff `403` scope) | Path `cycle_id` | Cycle detail (`seed_secret` omitted until `ALLOTMENT_ACTIVE`/`CLOSED`/`SETTLED`). |
| `POST /api/v1/admin/cycles` | `ADMIN+` (`assert_staff_scope`) | `{name, hostel_id, academic_year?, apply_open_at?, apply_close_at?, final_deadline_at?, freeze_hours?, policy?, room_ids?}` | Creates `DRAFT` cycle (`{"id", "_id"}`). |
| `PUT /api/v1/admin/cycles/{cycle_id}` | `ADMIN+` (`assert_staff_scope`) | Mutable `DRAFT`/`SCHEDULED` fields | Updates cycle config. |
| `POST /api/v1/admin/cycles/{cycle_id}/schedule` | `ADMIN+` (`assert_staff_scope`) | `{apply_open_at, apply_close_at}` | Validates `MIN_WINDOW_MINUTES` (60m) and transitions to `SCHEDULED`. |
| `POST /api/v1/admin/cycles/{cycle_id}/open` | `ADMIN+` (`assert_staff_scope`) | None | Opens `DRAFT`/`SCHEDULED` cycle atomically (`APPLICATIONS_OPEN`), locks live rooms (`409 ROOM_IN_LIVE_RELEASE`), commits SHA-256 seed hash. |
| `POST /api/v1/admin/cycles/{cycle_id}/close-window` | `ADMIN+` (`assert_staff_scope`) | None | Closes window (`APPLICATIONS_CLOSED`), locks groups, snapshots credits + Tier-0 accessibility (`409 WINDOW_NOT_OPEN`). |
| `POST /api/v1/admin/cycles/{cycle_id}/extend` | `ADMIN+` (`assert_staff_scope`) | `{new_close_at, reason?}` | Extends close time on open cycle (`409 WINDOW_EXTEND_INVALID`). |
| `POST /api/v1/admin/cycles/{cycle_id}/reopen` | `ADMIN+` (`assert_staff_scope`) | `{apply_close_at\|new_close_at, reason?}` | Reopens `APPLICATIONS_CLOSED` cycle prior to allocation (`409 REOPEN_NOT_ALLOWED`). |
| `POST /api/v1/admin/cycles/{cycle_id}/cancel` | `ADMIN+` (`assert_staff_scope`) | `{reason?}` | Cancels pre-allocation cycle (`DRAFT`–`APPLICATIONS_CLOSED`) & clears live locks. |
| `POST /api/v1/admin/cycles/{cycle_id}/preview-allocation` | `ADMIN+` (`assert_staff_scope`) | None | Dry-run Round-1 allocation summary with ephemeral seed (zero DB writes). |
| `POST /api/v1/admin/cycles/{cycle_id}/allocate` | `ADMIN+` (`assert_staff_scope`) | None | Acquires `ALLOCATING` CAS lock, executes Round-1 Weighted RSD, persists `MAIN` run + hashes + `HELD` allotments, reveals `seed_secret` (`ALLOTMENT_ACTIVE`), rolls back on error (`409 ALLOCATION_ALREADY_RUN`). |
| `POST /api/v1/admin/cycles/{cycle_id}/settle` | `ADMIN+` (`assert_staff_scope`) | None | Requires `CLOSED` (or `ALLOTMENT_ACTIVE` with 0 `HELD`). Idempotently settles credits (`cl_settlement_unique`), clears `is_live`, marks `SETTLED`. |
| `GET /api/v1/cycles/{cycle_id}/audit` | `AUDITOR+` (`assert_staff_scope`) | Path `cycle_id` | Recomputes commit–reveal commitment, `input_hash`, and `output_hash`. Requires revealed seed (`409 SEED_NOT_REVEALED`). |

---

## 5. Student Groups, Invites & Applications (`groups.py`)

| Method & Path | Role | Headers / Body | Behavior & Key Errors |
|---|---|---|---|
| `POST /api/v1/cycles/{cycle_id}/groups` | Bearer (eligible student) | `{name?, solo=false}` | Creates group (`FORMING` or `READY` if solo) & leader membership (`409 ALREADY_IN_GROUP`, `404` if hostel ineligible). |
| `GET /api/v1/cycles/{cycle_id}/groups/mine` | Bearer | Path `cycle_id` | Enriched active group (`members` with credits/accessibility + `application`), or `null`. |
| `GET /api/v1/cycles/{cycle_id}/invites/mine` | Bearer | Path `cycle_id` | Lists pending `INVITED` memberships with group/leader details. |
| `POST /api/v1/groups/{group_id}/invites` | Bearer (Leader) | `{roll_no \| email \| identifier}` | Invites active eligible student (max 4 members/invites → `GROUP_FULL`, `ALREADY_IN_GROUP`, `NOT_ELIGIBLE`, `INVITE_ALREADY_PENDING`). |
| `POST /api/v1/invites/{membership_id}/accept` | Bearer (Invitee) | Optional `Idempotency-Key` | Accepts invite, auto-declines competing invites in cycle, moves group to `READY` when no pending invites remain. |
| `POST /api/v1/invites/{membership_id}/decline` | Bearer (Invitee) | Optional `Idempotency-Key` | Sets `DECLINED`; transitions group to `READY` if no other pending invites remain. |
| `DELETE /api/v1/groups/{group_id}/members/{target_user_id}` | Bearer (Leader or Self) | Path params | Removes member or lets non-leader leave (`409 LEADER_CANNOT_LEAVE` for leader). |
| `DELETE /api/v1/groups/{group_id}` | Bearer (Leader) | Path `group_id` | Disbands open group, marks memberships `LEFT`, withdraws draft/submitted app (`409 GROUP_LOCKED`). |
| `PUT /api/v1/groups/{group_id}/application` | Bearer (Leader) | Optional `If-Match`<br>`{cycle_id?, ranked_choices, fallback, version?}` | Saves draft or edits submitted preferences (max 10 choices, `ROOM`/`FLOOR`, duplicate/capacity checks → `409 ROOM_NOT_ELIGIBLE`, `409 VERSION_CONFLICT`). |
| `POST /api/v1/groups/{group_id}/application/submit` | Bearer (Leader) | Optional `Idempotency-Key`<br>`{cycle_id?, ranked_choices?, fallback?}` | Validates zero pending invites (`409 GROUP_NOT_READY`), ≥1 choice, computes credit snapshot & Tier, sets `SUBMITTED`. |
| `POST /api/v1/groups/{group_id}/application/withdraw` | Bearer (Leader) | Optional `Idempotency-Key`<br>`{cycle_id?}` | Marks app `WITHDRAWN` & reverts group to `READY` while open. |
| `GET /api/v1/groups/{group_id}/application` | Bearer | `?cycle_id=` | Accepted member read of application (`404` otherwise for students). |

---

## 6. Allotments, Cascades & Holds (`allotments.py`)

| Method & Path | Role & Scope | Headers / Params / Body | Behavior & Key Errors |
|---|---|---|---|
| `GET /api/v1/cycles/{cycle_id}/allotments/mine` | Bearer | Path `cycle_id` | Active or most recent historical allotment for caller's group in cycle (`null` if none). |
| `GET /api/v1/allotments/mine`<br>`GET /api/v1/allotments/me` | Bearer | Optional `?cycle_id=` | Latest active/recent allotment across cycles (or scoped to `cycle_id`). |
| `GET /api/v1/admin/allotments` | `WARDEN+` (`assert_staff_scope`) | `?cycle_id=&status=&skip=0&limit=100` | Scoped list of enriched allotments sorted by `created_at desc`. |
| `POST /api/v1/allotments/{allotment_id}/accept` | Bearer (Member) | Optional `Idempotency-Key` | Atomic member consent (`PENDING → ACCEPTED`). Final accepting member confirms room & app (`HELD → CONFIRMED`). Rejects expired holds (`409 HOLD_EXPIRED`). |
| `POST /api/v1/allotments/{allotment_id}/decline` | Bearer (Member) | Optional `Idempotency-Key` | Member declines `HELD` offer → `DECLINED`, frees room (`AVAILABLE`), forfeits app (`FORFEITED`), runs `run_cascade`. |
| `POST /api/v1/allotments/{allotment_id}/cancel` | Bearer (Member) | Optional `Idempotency-Key` | Cancels `CONFIRMED` booking before `final_deadline_at` & cycle close → `CANCELLED`, frees room, marks `FORFEITED`, triggers `run_cascade` (`409 CANCEL_CUTOFF_PASSED`). |
| `POST /api/v1/admin/allotments/{allotment_id}/extend` | `WARDEN+` (`assert_staff_scope`) | `{reason, extra_hours=24}` | One-time staff extension (`reason` ≥10 chars, `extra_hours` clamped `1..72`). |
| `POST /api/v1/admin/allotments/{allotment_id}/revoke` | `WARDEN+` (`assert_staff_scope`) | `{reason}` | Revokes `HELD`/`CONFIRMED` (`reason` ≥10 chars), frees room, sets app `WAITLISTED` with `reinsert=True` (`0` penalty), runs `run_cascade`. |
| `POST /api/v1/admin/cycles/{cycle_id}/cascade` | `ADMIN+` (`assert_staff_scope`) | Path `cycle_id` | Triggers deterministic `assign_in_order` cascade (`{cascade_allotted, allotted, round_no, remaining_waitlisted}`). |
| `POST /api/v1/admin/applications/{application_id}/assign` | `ADMIN+` (`assert_staff_scope`) | `{cycle_id, room_id}` | Manual override offering an `AVAILABLE` fitting room (`round_no=99`, `HELD`). |

---

## 7. Admin, User Governance, Reports & Audit (`admin.py`)

| Method & Path | Role & Scope | Params / Body | Response / Error Codes |
|---|---|---|---|
| `GET /api/v1/admin/users` | `ADMIN+` (`filter_hostel_ids_for_user` for students) | `?role=&status=&search=&skip=0&limit=50` | Redacted user list (`password_hash`/tokens stripped). |
| `GET /api/v1/warden/users` | `WARDEN+` (`filter_hostel_ids_for_user`) | `?search=&accessibility_verified=&skip=0&limit=100` | Scoped `STUDENT` directory for accessibility queue. |
| `POST /api/v1/admin/users/import` | `SUPER_ADMIN` | Multipart CSV `file` | Imports/upserts students, initializes credits, returns `{created, updated, errors, details, activation_tokens}`. |
| `POST /api/v1/admin/role-grants` | `ADMIN+` | `{email, role, hostel_ids}` | `ADMIN` may only grant `WARDEN` scoped to their own `managed_hostel_ids`; `SUPER_ADMIN` may grant any role. |
| `GET /api/v1/admin/role-grants` | `ADMIN+` | `?status=&email=` | Lists role grants. |
| `DELETE /api/v1/admin/role-grants/{grant_id}` | `SUPER_ADMIN` | Path `grant_id` | Revokes grant, demotes user to `STUDENT`, bumps `token_version` (`409 LAST_SUPER_ADMIN` protection). |
| `PUT /api/v1/admin/users/{user_id}/hostels` | `SUPER_ADMIN` | `{hostel_ids?, managed_hostel_ids?}` | Validates hostel existence, updates scope, bumps `token_version`, audits `UPDATE_USER_HOSTELS`. |
| `PUT /api/v1/admin/users/{user_id}/enable` | `ADMIN+` | Path `user_id` | Re-enables user (`status = ACTIVE`). |
| `PUT /api/v1/admin/users/{user_id}/disable` | `ADMIN+` | Path `user_id` | Sets `DISABLED`, bumps `token_version` (`409 LAST_SUPER_ADMIN`, `ADMIN` cannot disable `SUPER_ADMIN`). |
| `PUT /api/v1/admin/users/{user_id}/unlock` | `ADMIN+` | Path `user_id` | Clears `LOCKED` state, `locked_until`, and `failed_logins`. |
| `PUT /api/v1/warden/users/{user_id}/accessibility` | `WARDEN+` (student hostel intersection check) | `{verified, note?}` | Sets `accessibility_verified` & audits `VERIFY_ACCESSIBILITY` (`403 HOSTEL_SCOPE_DENIED`). |
| `GET /api/v1/reports/occupancy` | `WARDEN+` (`filter_hostel_ids_for_user`) | Optional `?cycle_id=` | `{total, total_beds, occupied_beds, held_beds, by_floor, by_hostel}`. |
| `GET /api/v1/reports/fairness` | `AUDITOR+` (`filter_hostel_ids_for_user`) | Optional `?cycle_id=` | Full KPI payload (`jain_index, success_rate, average_rank, top_1_rate, top_3_rate, success_by_band, group_vs_solo, rank_distribution, demand_vs_supply, credit_distribution`). |
| `GET /api/v1/reports/rejections` | `AUDITOR+` (`filter_hostel_ids_for_user`) | Optional `?cycle_id=` | `{total_released, by_status: {DECLINED, EXPIRED, CANCELLED, REVOKED}}`. |
| `GET /api/v1/admin/audit-logs` | `AUDITOR+` | `?actor_id=&target_type=&entity_type=&action=&skip=0&limit=50` | Enriched with `actor_email`, ordered by `ts desc`. |

---

## 8. Backend Error Code Reference

[`core/errors.py`](../backend/app/core/errors.py) plus domain services emit deterministic codes:

| HTTP Status | Codes |
|---|---|
| `401` | `UNAUTHORIZED`, `INVALID_CREDENTIALS`, `TOKEN_EXPIRED`, `TOKEN_INVALID`, `TOKEN_REUSE`, `ACCOUNT_LOCKED`, `ACCOUNT_NOT_ACTIVATED` |
| `403` | `FORBIDDEN`, `HOSTEL_SCOPE_DENIED`, `CSRF_ORIGIN_MISMATCH`, `NOT_LEADER` |
| `404` | `NOT_FOUND` (also returned deliberately to mask cross-hostel student IDOR probes) |
| `409` | `CONFLICT`, `IDEMPOTENCY_CONFLICT`, `VERSION_CONFLICT`, `HOSTEL_CODE_EXISTS`, `FLOOR_ALREADY_EXISTS`, `ROOMS_ALREADY_EXIST`, `ROOM_BUSY`, `ROOM_IN_LIVE_RELEASE`, `ROOM_TAKEN`, `ROOM_NOT_ELIGIBLE`, `ALREADY_IN_GROUP`, `GROUP_FULL`, `NOT_ELIGIBLE`, `INVITE_ALREADY_PENDING`, `ALREADY_ANSWERED`, `GROUP_DISBANDED`, `LEADER_CANNOT_LEAVE`, `GROUP_LOCKED`, `GROUP_NOT_READY`, `WINDOW_NOT_OPEN`, `WINDOW_EXTEND_INVALID`, `REOPEN_NOT_ALLOWED`, `ALLOCATION_ALREADY_RUN`, `SEED_NOT_REVEALED`, `HOLD_EXPIRED`, `CANCEL_CUTOFF_PASSED`, `LAST_SUPER_ADMIN`, `VALIDATION_ERROR` |
| `422` | `VALIDATION_ERROR` (Pydantic DTO & semantic validation) |
| `429` | `RATE_LIMITED` |

---

**Related:** [Features & Workflows](features.md) · [Data Model & Invariants](data-model-and-invariants.md) · [Non-Functional Requirements](non-functional-requirements.md)
