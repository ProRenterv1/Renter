"""REST API endpoints for starting and checking Stripe Identity verification."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from identity.models import is_user_identity_verified
from payments.models import OwnerPayoutAccount


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def identity_start(request):
    return Response(
        {
            "detail": "Identity verification is now handled via Stripe Connect onboarding.",
            "already_verified": is_user_identity_verified(request.user),
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def identity_status(request):
    """Return the latest identity verification status for the current user."""
    user = request.user
    verified = is_user_identity_verified(user)
    payout_account = None
    try:
        payout_account = OwnerPayoutAccount.objects.get(user=user)
    except OwnerPayoutAccount.DoesNotExist:
        payout_account = None

    latest_payload: dict[str, Any] | None = None
    if payout_account:
        status_str = "verified" if verified else "pending"
        latest_payload = {
            "status": status_str,
            "session_id": payout_account.stripe_account_id,
            "verified_at": (
                payout_account.last_synced_at.isoformat()
                if verified and payout_account.last_synced_at
                else None
            ),
        }

    return Response(
        {
            "verified": verified,
            "latest": latest_payload,
        }
    )
