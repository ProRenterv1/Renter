import pytest

from operator_core.models import OperatorAuditEvent
from operator_settings import api as operator_settings_api
from operator_settings.jobs import JOB_REGISTRY
from operator_settings.models import OperatorJobRun

pytestmark = pytest.mark.django_db


def test_support_can_list_jobs_but_cannot_run(operator_support_client):
    resp = operator_support_client.get("/api/operator/jobs/")
    assert resp.status_code == 200, resp.data

    resp = operator_support_client.post(
        "/api/operator/jobs/run/",
        {"name": "scan_disputes_stuck_in_stage", "params": {}, "reason": "test"},
        format="json",
    )
    assert resp.status_code == 403, resp.data


def test_admin_run_job_validates_name(operator_admin_client):
    resp = operator_admin_client.post(
        "/api/operator/jobs/run/",
        {"name": "does_not_exist", "params": {}, "reason": "test"},
        format="json",
    )
    assert resp.status_code == 400


def test_admin_can_run_job_creates_run_and_audit(
    operator_admin_client, operator_admin_user, monkeypatch
):
    enqueued = []

    def _fake_delay(job_run_id):
        enqueued.append(job_run_id)
        return None

    monkeypatch.setattr(operator_settings_api.operator_run_job, "delay", _fake_delay)

    job_name = "scan_disputes_stuck_in_stage"
    assert job_name in JOB_REGISTRY

    resp = operator_admin_client.post(
        "/api/operator/jobs/run/",
        {"name": job_name, "params": {"stale_hours": 48}, "reason": "scan"},
        format="json",
    )
    assert resp.status_code == 202, resp.data
    job_run_id = resp.data["job_run_id"]
    assert enqueued == [job_run_id]

    run = OperatorJobRun.objects.get(pk=job_run_id)
    assert run.name == job_name
    assert run.requested_by == operator_admin_user
    assert run.status == OperatorJobRun.Status.QUEUED
    assert run.finished_at is None

    event = OperatorAuditEvent.objects.filter(action="operator.jobs.run").latest("created_at")
    assert event.entity_id == str(job_run_id)
    assert event.reason == "scan"
