from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from operator_core.audit import audit
from operator_core.permissions import HasOperatorRole, IsOperator

User = get_user_model()


class OperatorMeView(APIView):
    permission_classes = [IsOperator]

    def get(self, request):
        user: User = request.user
        name = (user.get_full_name() or user.username or user.email or "").strip()
        roles = list(user.groups.values_list("name", flat=True))

        return Response(
            {
                "id": user.id,
                "email": user.email,
                "name": name,
                "is_staff": user.is_staff,
                "roles": roles,
            }
        )


class OperatorAuditTestMutation(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(["operator_admin"])]

    def post(self, request):
        reason = request.data.get("reason") if isinstance(request.data, dict) else None
        reason_text = (str(reason).strip()) if reason is not None else ""

        if not reason_text:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[
            0
        ].strip() or request.META.get("REMOTE_ADDR", "")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        event = audit(
            actor=request.user,
            action="operator.audit_test",
            entity_type="dispute_case",
            entity_id="0",
            reason=reason_text,
            before=None,
            after=None,
            meta=None,
            ip=ip,
            user_agent=user_agent,
        )

        return Response(
            {"ok": True, "audit_event_id": event.id},
            status=status.HTTP_201_CREATED,
        )
