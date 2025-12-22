# Dispute Damage Cheatsheet

Quick guide for assigning `damage_assessment_category` and setting default outcomes. See the [operator policy](../policies/disputes_policy_operator.md) and [support workflows](./operator_support_workflows.md) for process steps.

## Categories and defaults
- **A_internal** — Wear/consumable or internal failure consistent with normal use or age. Examples: dull blade, worn brushes/belts, battery losing charge, gasket failure without impact, electronics dying with no external damage. Default: set `damage_assessment_category=A_internal` and resolve in favor of the renter (`resolved_renter`, release hold) unless evidence shows misuse; add maintenance note in `decision_notes`.
- **B_external** — Cosmetic or external/attachment damage or loss, no safety risk. Examples: cracked plastic housing, bent handle, missing accessory, paint scuffs, lost case. Default: `damage_assessment_category=B_external`; use `resolved_partial` with a capture equal to documented replacement/repair cost (parts + shipping, no padding). If evidence exonerates the renter, choose `resolved_renter` and release the hold.
- **C_safety** — Safety-critical or structural issues, tampering, or hazardous misuse. Examples: guard removed, exposed wiring, fuel/oil leak, battery fire/swelling, structural crack that could injure, chemical contamination. Default: `damage_assessment_category=C_safety`; set `requires_listing_suspend=True`, favor the owner (`resolved_owner`) and capture up to the documented cost; if capture exceeds deposit, note follow-up billing path. Notify safety/ops and the owner about listing suspension.
- **unknown** — Evidence insufficient to classify. Stay in `under_review`, request more evidence, and do not capture funds until reclassified.

## Broke-during-use guidance
- If the item failed during normal use with no external damage, start at **A_internal** (wear) and look for maintenance gaps.
- If the item broke because of handling/impact, move to **B_external**; if the break introduces a safety risk, upgrade to **C_safety**.
- Always cite the category and key evidence in `decision_notes` and the audit reason when resolving.
