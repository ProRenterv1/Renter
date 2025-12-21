from __future__ import annotations

import logging
from decimal import Decimal

from django.apps import apps
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.response import Response

from disputes.models import DisputeCase, DisputeEvidence, DisputeMessage
from disputes.services.settlement import (
    capture_deposit_amount_cents,
    refund_booking_charge,
    release_deposit_hold_if_needed,
)
from listings.models import ListingPhoto
from notifications import tasks as notification_tasks
from operator_core.api_base import OperatorAPIView, OperatorThrottleMixin
from operator_core.audit import audit
from operator_core.models import OperatorAuditEvent
from operator_core.permissions import HasOperatorRole, IsOperator
from operator_disputes.filters import OperatorDisputeFilter
from operator_disputes.serializers import (
    OperatorDisputeDetailSerializer,
    OperatorDisputeListSerializer,
)
from operator_users.api import ALLOWED_OPERATOR_ROLES
from payments.stripe_api import StripePaymentError
from storage.s3 import presign_get

logger = logging.getLogger(__name__)


def _base_queryset():
    return DisputeCase.objects.select_related(
        "booking",
        "booking__listing",
        "booking__owner",
        "booking__renter",
        "opened_by",
    ).prefetch_related(
        Prefetch("booking__listing__photos", queryset=ListingPhoto.objects.order_by("id"))
    )


class OperatorDisputeListView(OperatorThrottleMixin, generics.ListAPIView):
    serializer_class = OperatorDisputeListSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorDisputeFilter
    http_method_names = ["get"]

    def get_queryset(self):
        return _base_queryset().order_by("-created_at")


class OperatorDisputeDetailView(OperatorThrottleMixin, generics.RetrieveAPIView):
    serializer_class = OperatorDisputeDetailSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    http_method_names = ["get"]
    lookup_field = "pk"

    def get_queryset(self):
        return _base_queryset().prefetch_related(*OperatorDisputeDetailSerializer.prefetches())


class OperatorDisputeActionBase(OperatorAPIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]

    def _require_reason(self, payload) -> str | None:
        reason = (payload.get("reason") or "").strip() if isinstance(payload, dict) else ""
        return reason or None

    def _request_ip_and_ua(self, request):
        ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[
            0
        ].strip() or request.META.get("REMOTE_ADDR", "")
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        return ip, user_agent

    def _audit_dispute(
        self, *, request, dispute: DisputeCase, action: str, reason: str, before, after, meta=None
    ):
        ip, ua = self._request_ip_and_ua(request)
        audit(
            actor=request.user,
            action=action,
            entity_type=OperatorAuditEvent.EntityType.DISPUTE_CASE,
            entity_id=str(dispute.id),
            reason=reason,
            before=before,
            after=after,
            meta=meta,
            ip=ip,
            user_agent=ua,
        )

    def _get_dispute(self, pk: int) -> DisputeCase | None:
        return _base_queryset().filter(pk=pk).first()

    def _finalize_booking_flags(self, dispute: DisputeCase):
        booking = getattr(dispute, "booking", None)
        if not booking:
            return
        active_statuses = {
            DisputeCase.Status.OPEN,
            DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
            DisputeCase.Status.AWAITING_REBUTTAL,
            DisputeCase.Status.UNDER_REVIEW,
        }
        other_active = (
            DisputeCase.objects.filter(booking=booking, status__in=active_statuses)
            .exclude(pk=dispute.id)
            .exists()
        )
        if other_active:
            return
        booking.is_disputed = False
        booking.deposit_locked = False
        booking.save(update_fields=["is_disputed", "deposit_locked", "updated_at"])


class OperatorDisputeStartReviewView(OperatorDisputeActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        dispute = self._get_dispute(pk)
        if not dispute:
            return Response(status=status.HTTP_404_NOT_FOUND)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        before = {
            "status": dispute.status,
            "review_started_at": (
                dispute.review_started_at.isoformat() if dispute.review_started_at else None
            ),
        }

        updated = False
        now = timezone.now()
        with transaction.atomic():
            locked = DisputeCase.objects.select_for_update().get(pk=dispute.id)
            if locked.status in {
                DisputeCase.Status.OPEN,
                DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
                DisputeCase.Status.AWAITING_REBUTTAL,
            }:
                locked.status = DisputeCase.Status.UNDER_REVIEW
                updated = True
            if not locked.review_started_at:
                locked.review_started_at = now
                updated = True
            if updated:
                locked.save(update_fields=["status", "review_started_at", "updated_at"])
            dispute = locked

        after = {
            "status": dispute.status,
            "review_started_at": (
                dispute.review_started_at.isoformat() if dispute.review_started_at else None
            ),
        }

        if updated:
            DisputeMessage.objects.create(
                dispute=dispute,
                author=request.user,
                role=(
                    DisputeMessage.Role.ADMIN
                    if request.user.is_staff
                    else DisputeMessage.Role.SYSTEM
                ),
                text="Operator started review.",
            )

        self._audit_dispute(
            request=request,
            dispute=dispute,
            action="operator.dispute.start_review",
            reason=reason,
            before=before,
            after=after,
        )

        serializer = OperatorDisputeDetailSerializer(dispute)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OperatorDisputeRequestMoreEvidenceView(OperatorDisputeActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        dispute = self._get_dispute(pk)
        if not dispute:
            return Response(status=status.HTTP_404_NOT_FOUND)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        message = (payload.get("message") or "").strip()
        if not message:
            return Response({"detail": "message is required"}, status=status.HTTP_400_BAD_REQUEST)
        if len(message) > 4000:
            return Response({"detail": "message too long"}, status=status.HTTP_400_BAD_REQUEST)

        target = (payload.get("target") or "both").strip().lower()
        if target not in {"owner", "renter", "both"}:
            return Response(
                {"detail": "target must be owner, renter, or both"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        due_raw = payload.get("due_at")
        from django.utils.dateparse import parse_datetime

        due_at = parse_datetime(due_raw) if isinstance(due_raw, str) else None
        if not due_at:
            return Response(
                {"detail": "due_at is required and must be ISO8601"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if timezone.is_naive(due_at):
            due_at = timezone.make_aware(due_at, timezone.get_current_timezone())

        before = {
            "status": dispute.status,
            "intake_evidence_due_at": (
                dispute.intake_evidence_due_at.isoformat()
                if dispute.intake_evidence_due_at
                else None
            ),
        }

        with transaction.atomic():
            locked = DisputeCase.objects.select_for_update().get(pk=dispute.id)
            locked.status = DisputeCase.Status.INTAKE_MISSING_EVIDENCE
            locked.intake_evidence_due_at = due_at
            locked.save(update_fields=["status", "intake_evidence_due_at", "updated_at"])
            dispute = locked
            DisputeMessage.objects.create(
                dispute=dispute,
                author=request.user,
                role=DisputeMessage.Role.ADMIN,
                text=message,
            )

        after = {
            "status": dispute.status,
            "intake_evidence_due_at": (
                dispute.intake_evidence_due_at.isoformat()
                if dispute.intake_evidence_due_at
                else None
            ),
        }

        meta = {"due_at": due_at.isoformat(), "target": target}
        self._audit_dispute(
            request=request,
            dispute=dispute,
            action="operator.dispute.request_more_evidence",
            reason=reason,
            before=before,
            after=after,
            meta=meta,
        )

        try:
            notification_tasks.notify_dispute_update(dispute.id, target)
        except Exception:
            # best-effort notification; do not fail the request
            pass

        serializer = OperatorDisputeDetailSerializer(dispute)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OperatorDisputeCloseDuplicateView(OperatorDisputeActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        dispute = self._get_dispute(pk)
        if not dispute:
            return Response(status=status.HTTP_404_NOT_FOUND)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        duplicate_of_id = payload.get("duplicate_of_id")
        try:
            duplicate_of_id = int(duplicate_of_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "duplicate_of_id is required and must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message_text = (payload.get("message") or "").strip() or "Closed as duplicate."

        before = {
            "status": dispute.status,
            "decision_notes": dispute.decision_notes,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }
        now = timezone.now()

        with transaction.atomic():
            locked = (
                DisputeCase.objects.select_for_update().select_related("booking").get(pk=dispute.id)
            )
            locked.status = DisputeCase.Status.CLOSED_AUTO
            locked.resolved_at = now
            note = f"duplicate_of:{duplicate_of_id}"
            locked.decision_notes = f"{note} {message_text}".strip()
            locked.save(update_fields=["status", "resolved_at", "decision_notes", "updated_at"])
            dispute = locked
            DisputeMessage.objects.create(
                dispute=dispute,
                author=request.user,
                role=DisputeMessage.Role.ADMIN,
                text=message_text,
            )
            self._finalize_booking_flags(dispute)

        after = {
            "status": dispute.status,
            "decision_notes": dispute.decision_notes,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }

        self._audit_dispute(
            request=request,
            dispute=dispute,
            action="operator.dispute.close_duplicate",
            reason=reason,
            before=before,
            after=after,
            meta={"duplicate_of_id": duplicate_of_id},
        )

        try:
            notification_tasks.notify_dispute_update(dispute.id, "both")
        except Exception:
            pass

        serializer = OperatorDisputeDetailSerializer(dispute)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OperatorDisputeCloseLateView(OperatorDisputeActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        dispute = self._get_dispute(pk)
        if not dispute:
            return Response(status=status.HTTP_404_NOT_FOUND)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        message_text = (payload.get("message") or "").strip() or "Closed as late filing."
        before = {
            "status": dispute.status,
            "decision_notes": dispute.decision_notes,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }
        now = timezone.now()

        with transaction.atomic():
            locked = (
                DisputeCase.objects.select_for_update().select_related("booking").get(pk=dispute.id)
            )
            locked.status = DisputeCase.Status.CLOSED_AUTO
            locked.resolved_at = now
            locked.decision_notes = "closed_late"
            locked.save(update_fields=["status", "resolved_at", "decision_notes", "updated_at"])
            dispute = locked
            DisputeMessage.objects.create(
                dispute=dispute,
                author=request.user,
                role=DisputeMessage.Role.ADMIN,
                text=message_text,
            )
            self._finalize_booking_flags(dispute)

        after = {
            "status": dispute.status,
            "decision_notes": dispute.decision_notes,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }

        self._audit_dispute(
            request=request,
            dispute=dispute,
            action="operator.dispute.close_late",
            reason=reason,
            before=before,
            after=after,
        )

        try:
            notification_tasks.notify_dispute_update(dispute.id, "both")
        except Exception:
            pass

        serializer = OperatorDisputeDetailSerializer(dispute)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OperatorDisputeCloseView(OperatorDisputeActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        dispute = self._get_dispute(pk)
        if not dispute:
            return Response(status=status.HTTP_404_NOT_FOUND)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        normalized_reason = reason.strip().lower()
        if normalized_reason not in {"late", "duplicate", "no_evidence"}:
            return Response(
                {"detail": "unsupported close reason"}, status=status.HTTP_400_BAD_REQUEST
            )

        duplicate_of_id = payload.get("duplicate_of_id")
        if normalized_reason == "duplicate":
            try:
                duplicate_of_id = int(duplicate_of_id) if duplicate_of_id is not None else None
            except (TypeError, ValueError):
                return Response(
                    {"detail": "duplicate_of_id must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        note_defaults = {
            "late": "Closed as late filing.",
            "duplicate": "Closed as duplicate.",
            "no_evidence": "Closed due to missing evidence.",
        }
        message_text = (
            payload.get("notes") or payload.get("message") or ""
        ).strip() or note_defaults[normalized_reason]

        before = {
            "status": dispute.status,
            "decision_notes": dispute.decision_notes,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }
        now = timezone.now()

        with transaction.atomic():
            locked = (
                DisputeCase.objects.select_for_update().select_related("booking").get(pk=dispute.id)
            )
            locked.status = DisputeCase.Status.CLOSED_AUTO
            locked.resolved_at = now
            if normalized_reason == "duplicate":
                note = "closed_duplicate"
                if duplicate_of_id:
                    note = f"duplicate_of:{duplicate_of_id}"
                locked.decision_notes = f"{note} {message_text}".strip()
            elif normalized_reason == "no_evidence":
                locked.decision_notes = "closed_no_evidence"
            else:
                locked.decision_notes = "closed_late"
            locked.save(update_fields=["status", "resolved_at", "decision_notes", "updated_at"])
            dispute = locked
            DisputeMessage.objects.create(
                dispute=dispute,
                author=request.user,
                role=DisputeMessage.Role.ADMIN,
                text=message_text,
            )
            self._finalize_booking_flags(dispute)

        after = {
            "status": dispute.status,
            "decision_notes": dispute.decision_notes,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }

        action_map = {
            "late": "operator.dispute.close_late",
            "duplicate": "operator.dispute.close_duplicate",
            "no_evidence": "operator.dispute.close_no_evidence",
        }
        meta = {"reason": normalized_reason}
        if normalized_reason == "duplicate" and duplicate_of_id:
            meta["duplicate_of_id"] = duplicate_of_id

        self._audit_dispute(
            request=request,
            dispute=dispute,
            action=action_map[normalized_reason],
            reason=reason,
            before=before,
            after=after,
            meta=meta,
        )

        try:
            notification_tasks.notify_dispute_update(dispute.id, "both")
        except Exception:
            pass

        serializer = OperatorDisputeDetailSerializer(dispute)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OperatorDisputeEvidencePresignGetView(OperatorDisputeActionBase):
    http_method_names = ["post"]
    PRESIGN_TTL_SECONDS = 600

    def post(self, request, pk: int, evidence_id: int):
        dispute = self._get_dispute(pk)
        if not dispute:
            return Response(status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        evidence = DisputeEvidence.objects.filter(pk=evidence_id, dispute_id=dispute.id).first()
        if not evidence:
            return Response(
                {"detail": "evidence not found for dispute"}, status=status.HTTP_404_NOT_FOUND
            )

        result = presign_get(evidence.s3_key, expires_in=self.PRESIGN_TTL_SECONDS)
        meta = {
            "evidence_id": evidence.id,
            "s3_key": evidence.s3_key,
            "ttl_seconds": self.PRESIGN_TTL_SECONDS,
        }
        self._audit_dispute(
            request=request,
            dispute=dispute,
            action="operator.dispute.evidence.presign_get",
            reason=reason,
            before=None,
            after=None,
            meta=meta,
        )
        return Response(result, status=status.HTTP_200_OK)


class OperatorDisputeResolveView(OperatorDisputeActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        dispute = self._get_dispute(pk)
        if not dispute:
            return Response(status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        decision = (payload.get("decision") or "").strip().lower()
        decision_map = {
            "resolved_owner": DisputeCase.Status.RESOLVED_OWNER,
            "resolved_renter": DisputeCase.Status.RESOLVED_RENTER,
            "resolved_partial": DisputeCase.Status.RESOLVED_PARTIAL,
        }
        if decision not in decision_map:
            return Response(
                {"detail": "decision must be resolved_owner, resolved_renter, or resolved_partial"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refund_amount_cents = int(payload.get("refund_amount_cents") or 0)
        except (TypeError, ValueError):
            return Response(
                {"detail": "refund_amount_cents must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            deposit_capture_amount_cents = int(payload.get("deposit_capture_amount_cents") or 0)
        except (TypeError, ValueError):
            return Response(
                {"detail": "deposit_capture_amount_cents must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if refund_amount_cents < 0 or deposit_capture_amount_cents < 0:
            return Response(
                {"detail": "amounts must be non-negative"}, status=status.HTTP_400_BAD_REQUEST
            )

        allowed_statuses = {
            DisputeCase.Status.OPEN,
            DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
            DisputeCase.Status.AWAITING_REBUTTAL,
            DisputeCase.Status.UNDER_REVIEW,
        }
        if dispute.status not in allowed_statuses:
            return Response(
                {"detail": "dispute is already resolved"}, status=status.HTTP_400_BAD_REQUEST
            )

        booking = getattr(dispute, "booking", None)
        if not booking:
            return Response(
                {"detail": "booking is required to resolve dispute"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deposit_hold_id = (getattr(booking, "deposit_hold_id", "") or "").strip()
        if deposit_capture_amount_cents > 0 and not deposit_hold_id:
            return Response(
                {"detail": "deposit_capture_amount_cents requires an active deposit hold"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Cap capture to deposit total when available
        capture_capped = False
        totals = getattr(booking, "totals", {}) or {}
        deposit_total_raw = totals.get("damage_deposit")
        deposit_total_cents: int | None = None
        try:
            if deposit_total_raw is not None:
                deposit_total_cents = int(Decimal(str(deposit_total_raw)) * 100)
        except Exception:
            deposit_total_cents = None
        if (
            deposit_total_cents
            and deposit_total_cents > 0
            and deposit_capture_amount_cents > deposit_total_cents
        ):
            deposit_capture_amount_cents = deposit_total_cents
            capture_capped = True

        if deposit_capture_amount_cents > 0 and not booking.deposit_locked:
            booking.deposit_locked = True
            booking.save(update_fields=["deposit_locked", "updated_at"])

        before = {
            "status": dispute.status,
            "refund_amount_cents": dispute.refund_amount_cents,
            "deposit_capture_amount_cents": dispute.deposit_capture_amount_cents,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }

        refund_id = None
        capture_id = None
        try:
            if refund_amount_cents > 0:
                refund_id = refund_booking_charge(booking, refund_amount_cents)
        except StripePaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if deposit_capture_amount_cents > 0:
                capture_id = capture_deposit_amount_cents(booking, deposit_capture_amount_cents)
        except StripePaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if deposit_hold_id:
            try:
                release_deposit_hold_if_needed(booking)
            except StripePaymentError as exc:
                logger.info("Failed to release deposit hold for booking %s: %s", booking.id, exc)

        now = timezone.now()
        dispute.status = decision_map[decision]
        dispute.refund_amount_cents = refund_amount_cents or None
        dispute.deposit_capture_amount_cents = deposit_capture_amount_cents or None
        notes = (payload.get("decision_notes") or "").strip()
        if capture_capped:
            notes = f"{notes} (capture capped to deposit)".strip()
        dispute.decision_notes = notes or dispute.decision_notes
        dispute.resolved_at = now
        dispute.save(
            update_fields=[
                "status",
                "refund_amount_cents",
                "deposit_capture_amount_cents",
                "decision_notes",
                "resolved_at",
                "updated_at",
            ]
        )

        # Booking event
        try:
            BookingEvent = apps.get_model("operator_bookings", "BookingEvent")
            BookingEvent.objects.create(
                booking=booking,
                actor=request.user,
                type=getattr(
                    BookingEvent.Type, "DISPUTE_RESOLVED", BookingEvent.Type.OPERATOR_ACTION
                ),
                payload={
                    "dispute_id": dispute.id,
                    "decision": dispute.status,
                    "refund_amount_cents": refund_amount_cents,
                    "deposit_capture_amount_cents": deposit_capture_amount_cents,
                },
            )
        except Exception:
            logger.exception(
                "operator_dispute: failed to log booking event for resolution",
                extra={"dispute_id": dispute.id},
            )

        self._finalize_booking_flags(dispute)

        try:
            notification_tasks.notify_dispute_resolved(dispute.id)
        except Exception:
            pass

        after = {
            "status": dispute.status,
            "refund_amount_cents": dispute.refund_amount_cents,
            "deposit_capture_amount_cents": dispute.deposit_capture_amount_cents,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        }
        meta = {
            "decision": decision,
            "refund_amount_cents": refund_amount_cents,
            "deposit_capture_amount_cents": deposit_capture_amount_cents,
            "refund_id": refund_id,
            "deposit_capture_id": capture_id,
            "capture_capped": capture_capped,
        }
        self._audit_dispute(
            request=request,
            dispute=dispute,
            action="operator.dispute.resolve",
            reason=reason,
            before=before,
            after=after,
            meta=meta,
        )

        serializer = OperatorDisputeDetailSerializer(dispute)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _finalize_booking_flags(self, dispute: DisputeCase):
        booking = getattr(dispute, "booking", None)
        if not booking:
            return
        active_statuses = {
            DisputeCase.Status.OPEN,
            DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
            DisputeCase.Status.AWAITING_REBUTTAL,
            DisputeCase.Status.UNDER_REVIEW,
        }
        other_active = (
            DisputeCase.objects.filter(booking=booking, status__in=active_statuses)
            .exclude(pk=dispute.id)
            .exists()
        )
        if other_active:
            return
        booking.is_disputed = False
        booking.deposit_locked = False
        booking.save(update_fields=["is_disputed", "deposit_locked", "updated_at"])
