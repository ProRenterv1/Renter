# Operator Support Workflows

Playbooks for staff actions; pair with the [operator dispute policy](../policies/disputes_policy_operator.md) and [damage cheatsheet](./dispute_damage_cheatsheet.md).

## Quick reference
- Always review: `DisputeCase.status`, `damage_flow_kind`, `damage_assessment_category`, `filed_at`, `intake_evidence_due_at`, `rebuttal_due_at`, `auto_rebuttal_timeout`, `decision_notes`, `refund_amount_cents`, `deposit_capture_amount_cents`.
- Booking context: `booking.deposit_hold_id`, `booking.deposit_locked`, `booking.dispute_window_expires_at`, before/after booking photos (clean only), and whether other disputes on the booking remain active.
- “Broke during use” mapping to `damage_assessment_category`: A_internal = wear/consumable failure; B_external = accessory/cosmetic break; C_safety = hazard/structural or misuse with safety risk. Use the cheatsheet for examples before deciding.
- Audit every change with `operator_core.audit.audit` and note which notifications were sent.

## Playbooks
### Start review
1) Preconditions: status is `awaiting_rebuttal` with due time passed, or intake complete and escalation requested. Confirm AV-clean evidence only.
2) Set `status=under_review`, `review_started_at=now`, and add a short summary in `decision_notes` (e.g., key evidence, deadlines observed).
3) Keep `booking.deposit_locked=True` when a `deposit_hold_id` exists. If no deposit, note “no hold to split” in `decision_notes`.
4) Notify both parties that the case is under review (use rebuttal-ended or custom review-start messaging); capture that in audit `meta`.
5) Audit reason example: `start_review: rebuttal_window_elapsed`.

### Request more evidence
1) Trigger when intake minimums are not met (e.g., missing clean before/after photos or video for broke-during-use).
2) Set `status=intake_missing_evidence`, calculate/confirm `intake_evidence_due_at` per `DISPUTE_FILING_WINDOW_HOURS`, and keep `rebuttal_due_at` aligned with policy.
3) Send missing-evidence email/SMS with a precise ask (before/after photos, close-ups, receipt/quote). Note the deadline in the message.
4) Audit reason example: `intake_missing_evidence: need after photos + close-up of crack`.

### Close as duplicate
1) Check for another active dispute on the same booking (statuses open/intake_missing_evidence/awaiting_rebuttal/under_review).
2) Set `status=closed_auto`, copy the canonical dispute ID into `decision_notes`, and keep `deposit_locked=True` if another active dispute exists; otherwise allow unlock.
3) Message both parties pointing to the active dispute thread and confirm no new evidence is needed here.
4) Audit reason example: `close_duplicate: dupe_of=123`.

### Close as late
1) Verify `booking.dispute_window_expires_at` and filing time; confirm no safety/fraud exemption and, if no deposit hold, that late filing cannot proceed.
2) Set `status=closed_auto`, add `resolved_at=now`, and note “Filed after dispute window (expires <date/time>)” in `decision_notes`.
3) If no other active disputes, clear `booking.deposit_locked` and confirm the hold (if any) can release.
4) Notify filer with the late-window rationale. Audit reason example: `close_late: window_expired no_deposit_hold`.

### Resolve with deposit split
1) Choose `damage_assessment_category` per the cheatsheet and confirm evidence suffices. Ensure `deposit_hold_id` exists if planning a capture; if not, plan refund/charge flows separately.
2) Select outcome: `resolved_owner` (capture for owner), `resolved_renter` (release to renter), or `resolved_partial` (split). Populate `deposit_capture_amount_cents` and/or `refund_amount_cents` and document math in `decision_notes`.
3) Coordinate payment execution: capture the hold amount, then release remainder; if no hold, create/refund charges through payments/finance and reference the transaction IDs in `decision_notes`.
4) Send decision notifications to both parties including amounts and reasoning; mention any listing suspension if set.
5) Audit reason example: `decision:resolved_partial capture=15000 refund=0 category=B_external evidence=photos 123/124`.
