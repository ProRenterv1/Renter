"""REST API endpoints for starting and checking Stripe Identity verification."""

from __future__ import annotations

import logging
from typing import Any

import stripe
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from identity.models import IdentityVerification, is_user_identity_verified
from payments.stripe_api import StripeConfigurationError, _get_stripe_api_key

logger = logging.getLogger(__name__)


def _session_value(session: Any, field: str, default: Any = None) -> Any:
    """Return a field off of a Stripe session object or dict."""
    if isinstance(session, dict):
        return session.get(field, default)
    return getattr(session, field, default)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def identity_start(request):
    """Create a new Stripe Identity verification session for the current user."""
    try:
        stripe.api_key = _get_stripe_api_key()
    except StripeConfigurationError:
        return Response(
            {"detail": "Identity verification is temporarily unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return_url = ""
    if getattr(settings, "FRONTEND_ORIGIN", ""):
        origin = settings.FRONTEND_ORIGIN.rstrip("/")
        return_url = f"{origin}/profile?tab=personal"

    session_payload: dict[str, Any] = {
        "type": "document",
        "metadata": {"user_id": str(request.user.id)},
        "options": {
            "document": {
                "allowed_types": ["driving_license", "passport", "id_card"],
                "require_id_number": True,
                "require_live_capture": True,
                "require_matching_selfie": False,
            }
        },
    }
    if return_url:
        session_payload["return_url"] = return_url

    try:
        session = stripe.identity.VerificationSession.create(**session_payload)
    except stripe.error.StripeError:
        logger.exception("Stripe Identity session creation failed")
        return Response(
            {"detail": "Unable to start identity verification right now."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    session_id = _session_value(session, "id")
    if not session_id:
        logger.error("Stripe Identity session missing id")
        return Response(
            {"detail": "Unable to start identity verification right now."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    IdentityVerification.objects.update_or_create(
        user=request.user,
        session_id=session_id,
        defaults={
            "status": IdentityVerification.Status.PENDING,
            "verified_at": None,
            "last_error_code": "",
            "last_error_reason": "",
        },
    )

    already_verified = is_user_identity_verified(request.user)
    return Response(
        {
            "session_id": session_id,
            "client_secret": _session_value(session, "client_secret"),
            "status": _session_value(session, "status"),
            "already_verified": already_verified,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def identity_status(request):
    """Return the latest identity verification status for the current user."""
    latest = IdentityVerification.objects.filter(user=request.user).order_by("-created_at").first()
    latest_payload: dict[str, Any] | None = None
    if latest:
        latest_payload = {
            "status": latest.status,
            "session_id": latest.session_id,
            "verified_at": latest.verified_at.isoformat() if latest.verified_at else None,
        }

    return Response(
        {
            "verified": bool(latest and latest.is_verified),
            "latest": latest_payload,
        }
    )
