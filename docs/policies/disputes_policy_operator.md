# Disputes Policy (Operator)

Canada-first operator guidance for disputes. See the [consumer overview](./disputes_policy_consumer.md) for user-facing language and the [support workflows](../runbooks/operator_support_workflows.md) for step-by-step handling.

## Decision types (maps to `DisputeCase.Status`)
- OPEN (`open`): case accepted for intake; deposit lock mirrors the booking when a `deposit_hold_id` exists.
- INTAKE_MISSING_EVIDENCE (`intake_missing_evidence`): intake minimums not met; `intake_evidence_due_at` is set; auto-closes to `closed_auto` after the deadline.
- AWAITING_REBUTTAL (`awaiting_rebuttal`): intake minimums met; counterparty rebuttal window (default 24h via `DISPUTE_REBUTTAL_WINDOW_HOURS`) running.
- UNDER_REVIEW (`under_review`): rebuttal window ended or operator pulled into review; active investigation.
- RESOLVED_OWNER (`resolved_owner`): owner favored; capture deposit/charge renter per decision.
- RESOLVED_RENTER (`resolved_renter`): renter favored; release any hold/issue refund.
- RESOLVED_PARTIAL (`resolved_partial`): split outcome; document math in `decision_notes`.
- CLOSED_AUTO (`closed_auto`): system closed (late filing, missing evidence, or similar); deposit unlocks if no other active disputes on the booking.

## Evidence handling
- Allowed kinds: `photo`, `video`, `other` (`DisputeEvidence.Kind`). Max size enforced by `S3_MAX_UPLOAD_BYTES` (default 15 MB); the value returned in presign responses must be honored.
- AV scan states (`DisputeEvidence.AVStatus`): `pending` (treat as quarantined; do not rely on it), `clean` (usable), `infected` (block and request a clean re-upload), `failed` (scanner could not determine; ask for a replacement upload or perform a manual review before relying on it).
- Intake minimums: damage-like categories require at least one clean evidence item and clean before/after booking photos; broke-during-use flow expects either 1+ video or 2+ photos.
- Retention: recommended to delete evidence objects 90 days after finalization; keep metadata (uploader, filename, size, kind, AV status, timestamps, decision notes linkage) for 24 months for audit/regulatory needs. If a hold is under investigation or subject to legal request, pause deletion and note it in `decision_notes`.

## Deposit split rules
- If the booking has a `deposit_hold_id`, the hold is locked while status is `open`/`intake_missing_evidence`/`awaiting_rebuttal`/`under_review` and until all disputes on the booking leave those states.
- “Capture” means instruct payments to collect up to `deposit_capture_amount_cents` from the hold and move funds per the decision (usually to the owner); document amounts in `decision_notes`.
- “Release remainder” means unlock any unused portion of the hold back to the renter once capture is completed (or release the full hold when `deposit_capture_amount_cents` is null/0).
- When no `deposit_hold_id` exists, deposit split is not applicable; use `refund_amount_cents`/owner payouts or a separate charge flow and still record the rationale in the decision.

## Operator actions and audit logging
- Every mutation must include a human-readable `reason` in `operator_core.audit.audit(...)`; the helper raises if `reason` is empty. Include relevant IDs, evidence references, and dollar amounts in `reason` or `meta`.
- Common actions (always log):
  - Start review: move to `under_review`, set `review_started_at`; reason like `start_review: rebuttal window ended`.
  - Request more evidence: move to `intake_missing_evidence`, set `intake_evidence_due_at`; reason like `intake_missing_evidence: missing before/after photos`.
  - Mark duplicate or late: set `closed_auto`, add `decision_notes` referencing the original dispute ID or expired window; reason like `close_duplicate: dupe_of=123` or `close_late: window_expired`.
  - Resolve: set `resolved_owner` / `resolved_renter` / `resolved_partial`, populate `deposit_capture_amount_cents` and/or `refund_amount_cents`, write `decision_notes`; reason like `decision:resolved_partial parts=handle, labor=1h`.
  - Unlock deposit after finalization: if no other active disputes, clear `booking.deposit_locked`; reason like `unlock_deposit: all disputes closed`.
- Notifications: when changing status, send the matching dispute email/SMS templates (missing evidence, rebuttal start/end, decision). Note the templates sent in `meta` for traceability.

## References
- Intake/rebuttal timers: `DISPUTE_FILING_WINDOW_HOURS`, `DISPUTE_REBUTTAL_WINDOW_HOURS`.
- Evidence upload limits: `S3_MAX_UPLOAD_BYTES`.
- Audit helper: `backend/operator_core/audit.py`.
- Damage category guidance: [Dispute damage cheatsheet](../runbooks/dispute_damage_cheatsheet.md).
