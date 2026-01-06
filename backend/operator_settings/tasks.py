from __future__ import annotations

import logging
import traceback
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from operator_settings.jobs import JOB_REGISTRY
from operator_settings.models import OperatorJobRun

logger = logging.getLogger(__name__)


def _safe_error_dict(exc: BaseException) -> dict[str, Any]:
    return {
        "type": exc.__class__.__name__,
        "message": str(exc) or exc.__class__.__name__,
        "traceback": traceback.format_exc(limit=20),
    }


@shared_task(name="operator_run_job")
def operator_run_job(job_run_id: int) -> dict[str, Any]:
    """
    Execute an OperatorJobRun by id. Updates status and persists output/error.
    """

    try:
        with transaction.atomic():
            locked = OperatorJobRun.objects.select_for_update().get(pk=job_run_id)
            if locked.status != OperatorJobRun.Status.QUEUED:
                return {"ok": False, "error": {"type": "InvalidState", "message": locked.status}}
            locked.status = OperatorJobRun.Status.RUNNING
            locked.save(update_fields=["status"])
            job_name = locked.name
            params = locked.params or {}

        job_fn = JOB_REGISTRY.get(job_name)
        if job_fn is None:
            raise RuntimeError(f"Unknown job: {job_name}")

        if not isinstance(params, dict):
            params = {}
        output = job_fn(params)
        output_json = {"ok": True, "output": output}
        final_status = OperatorJobRun.Status.SUCCEEDED
    except Exception as exc:
        logger.exception("operator_run_job: job failed", extra={"job_run_id": job_run_id})
        output_json = {"ok": False, "error": _safe_error_dict(exc)}
        final_status = OperatorJobRun.Status.FAILED

    finished_at = timezone.now()
    try:
        OperatorJobRun.objects.filter(pk=job_run_id).update(
            status=final_status,
            output_json=output_json,
            finished_at=finished_at,
        )
    except Exception:
        logger.exception(
            "operator_run_job: failed to persist output", extra={"job_run_id": job_run_id}
        )
    return output_json
