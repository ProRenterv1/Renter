# Promotions Policy (Operator)

Operator rules for owner-paid listing promotions in Canada. Changes must be auditable via `operator_core.audit.audit` (reason required).

## Refunds and cancellations
- Pre-start cancellations (slot `starts_at` in future, `active=True`): allowed on owner request. Set the slot inactive, trigger/coordinate payment reversal (Stripe refund or earnings return), and log reason referencing the slot ID and booking/listing context.
- In-flight or completed slots: non-refundable by default. Exceptions require support lead + finance approval and should only cover platform failure (promotion never served), fraud, or duplicate purchase. The system does not prorate; any approved refund must be processed manually and recorded in `decision_notes`/audit meta.
- Earnings-funded promotions: only refund when the earnings balance can be re-credited; finance must confirm the ledger reversal before marking the slot inactive.

## Comped promotions
- Who can grant: support leads or finance only. Create a zero-charge slot or process a refund after purchase; do not issue ad-hoc discounts without approval.
- When to grant: service outages, bad inventory data, or retention saves with a clear business justification. Avoid repeated comps for the same listing without a remediation plan.
- Audit: include requester, listing ID, date range, and business reason in the audit `reason`; attach the ticket link in audit `meta`.

## Cancel-early rules
- To stop a promotion early (e.g., listing suspended, safety issue, owner request with cause), set the `PromotedSlot.active` flag to `False` and notify the owner that visibility ends immediately.
- Credits/refunds for early stops follow the refund rules above; there is no automatic proration. If no refund is approved, clearly state that the slot was delivered through the stop date.
- Document all actions (deactivation, notifications, refund decision) in the audit trail with a single reason string.
