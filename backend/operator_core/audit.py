from operator_core.models import OperatorAuditEvent


def audit(
    *,
    actor,
    action,
    entity_type,
    entity_id,
    reason,
    before=None,
    after=None,
    meta=None,
    ip=None,
    user_agent=None,
):
    """
    Persist an operator audit event. Raises ValueError if reason is missing.
    """

    if not reason:
        raise ValueError("reason is required for audit events")

    return OperatorAuditEvent.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        reason=reason,
        before_json=before,
        after_json=after,
        meta_json=meta,
        ip=ip or "",
        user_agent=user_agent or "",
    )
