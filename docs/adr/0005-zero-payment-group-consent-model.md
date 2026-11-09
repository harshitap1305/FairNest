# ADR-0005: Zero-Payment Unanimous Group Consent Confirmation Model

- **Status:** Accepted
- **Date:** 2026-11-09
- **Components:** [`allotments.py`](../../backend/app/api/routes/allotments.py), [`allotment_service.py`](../../backend/app/services/allotment_service.py), [`core_repos.py`](../../backend/app/repositories/core_repos.py), [`worker.py`](../../backend/app/worker.py), [`behaviour.py`](../../simulator/simulator/behaviour.py)

---

## Context

Institutional hostel housing typically processes room fee billing separately through university ERP/finance offices rather than consumer card gateways inside a room-choice portal. Earlier design drafts included payment webhook/checkout concepts (`PAID` states, `/allotments/{id}/pay`), which introduced unnecessary third-party payment coupling, partial-payment edge cases for multi-member roommate groups, and security scope bloat.

Meanwhile, roommate groups still require explicit accountability: one group leader should not silently trap reluctant roommates into a binding room without their consent, nor should holds sit abandoned indefinitely blocking waitlisted applicants.

## Decision

1. **Remove Payment Entirely:** Exclude billing, payment statuses, webhooks, and `/pay` routes from the entire backend, database schema, frontend SPA, and simulator.
2. **Adopt `HELD` → Unanimous `accept` → `CONFIRMED`:**
   - Every offered room enters `HELD` with `expires_at = now + cycle.freeze_hours` (default `48h`) and per-member consent subdocuments initialized to `accept_status: "PENDING"`.
   - Each member accepts independently via `POST /api/v1/allotments/{id}/accept` using atomic positional CAS (`accept_member`) + `Idempotency-Key`.
   - Promotion to `CONFIRMED` (updating `room_inventory`, `allotments`, `applications`) triggers transactionally **only when 100% of members reach `ACCEPTED`**.
3. **Group Accountability on Decline/Expiry & Cancellation:**
   - Any single `decline` or hold expiration forfeits the entire group's allotment (`DECLINED` / `EXPIRED` → `FORFEITED`, `forfeit_delta = -2`), returns the room (`AVAILABLE`), and synchronously runs `run_cascade` (zero re-randomization).
   - Confirmed bookings can still self-cancel prior to `final_deadline_at` via `POST /allotments/{id}/cancel` (`CANCELLED`, releasing the room to cascade with `late_cancel_delta = -1` at settlement).
4. **Grace Safeguards:** Provide an automatic one-time `+10m` worker extension (`try_extend_grace`) for expired holds still awaiting `PENDING` responses, plus a logged staff `extend_hold` (`1–72h`) escape hatch.

## Consequences

- **Positive:** Zero payment reconciliation bugs or PCI scope; clean transactional room release and deterministic waitlist refill; transparent roommate consent UI ([`HoldPanel.jsx`](../../frontend/src/components/allotment/HoldPanel.jsx)).
- **Trade-off:** Requires every group member to log in and explicitly accept within `freeze_hours` to lock a room.

---

**Related:** [Unique Design Aspects & Algorithms](../uniqueness-and-algorithms.md) · [REST API Reference](../api-reference.md)
