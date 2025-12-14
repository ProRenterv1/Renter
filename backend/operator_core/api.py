from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from disputes.models import DisputeCase
from listings.models import Listing
from operator_core.audit import audit
from operator_core.models import OperatorAuditEvent, OperatorNote, OperatorTag
from operator_core.permissions import HasOperatorRole, IsOperator

User = get_user_model()
ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)


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


NOTE_ENTITY_MODELS = {
    "user": User,
    "listing": Listing,
    "booking": Booking,
    "dispute": DisputeCase,
}


def _request_ip_and_ua(request):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR", ""
    )
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip, user_agent


class OperatorNotesView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    http_method_names = ["get", "post"]

    def _get_entity_model(self, entity_type: str):
        if not entity_type:
            return None
        return NOTE_ENTITY_MODELS.get(entity_type)

    def _note_entity_type(self, note: OperatorNote) -> str:
        model_class = note.content_type.model_class()
        for key, model in NOTE_ENTITY_MODELS.items():
            if model_class == model:
                return key
        return note.content_type.model

    def _serialize_note(self, note: OperatorNote):
        author = note.author
        author_data = None
        if author:
            name = (author.get_full_name() or author.username or author.email or "").strip()
            author_data = {
                "id": author.id,
                "email": author.email,
                "name": name,
            }
        return {
            "id": note.id,
            "entity_type": self._note_entity_type(note),
            "entity_id": note.object_id,
            "text": note.text,
            "tags": [tag.name for tag in note.tags.all()],
            "author": author_data,
            "created_at": note.created_at,
        }

    def get(self, request):
        entity_type = (request.query_params.get("entity_type") or "").strip()
        entity_id = (request.query_params.get("entity_id") or "").strip()
        if not entity_type or not entity_id:
            return Response(
                {"detail": "entity_type and entity_id are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model = self._get_entity_model(entity_type)
        if not model:
            return Response({"detail": "invalid entity_type"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            model.objects.get(pk=entity_id)
        except (ValueError, TypeError):
            return Response({"detail": "invalid entity_id"}, status=status.HTTP_400_BAD_REQUEST)
        except model.DoesNotExist:
            return Response({"detail": "entity not found"}, status=status.HTTP_404_NOT_FOUND)

        content_type = ContentType.objects.get_for_model(model)
        notes = (
            OperatorNote.objects.filter(content_type=content_type, object_id=str(entity_id))
            .select_related("author")
            .prefetch_related("tags")
            .order_by("-created_at")[:200]
        )
        data = [self._serialize_note(note) for note in notes]
        return Response(data)

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        entity_type = (payload.get("entity_type") or "").strip()
        raw_entity_id = payload.get("entity_id")
        text = (payload.get("text") or "").strip()
        tags = payload.get("tags") or []
        reason = (payload.get("reason") or "").strip()

        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not text:
            return Response({"detail": "text is required"}, status=status.HTTP_400_BAD_REQUEST)
        if tags and not isinstance(tags, (list, tuple)):
            return Response({"detail": "tags must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        if raw_entity_id in (None, ""):
            return Response({"detail": "entity_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        entity_id = str(raw_entity_id).strip()
        if not entity_id:
            return Response({"detail": "entity_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        model = self._get_entity_model(entity_type)
        if not model:
            return Response({"detail": "invalid entity_type"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target = model.objects.get(pk=entity_id)
        except (ValueError, TypeError):
            return Response({"detail": "invalid entity_id"}, status=status.HTTP_400_BAD_REQUEST)
        except model.DoesNotExist:
            return Response({"detail": "entity not found"}, status=status.HTTP_404_NOT_FOUND)

        content_type = ContentType.objects.get_for_model(model)
        note = OperatorNote.objects.create(
            content_type=content_type,
            object_id=str(target.pk),
            author=request.user,
            text=text,
        )

        tag_names = []
        tag_objects = []
        for raw in tags:
            name = str(raw).strip()
            if not name:
                continue
            tag_names.append(name)
            tag_obj, _ = OperatorTag.objects.get_or_create(name=name)
            tag_objects.append(tag_obj)

        if tag_objects:
            note.tags.set(tag_objects)

        ip, user_agent = _request_ip_and_ua(request)
        audit(
            actor=request.user,
            action="operator.note.create",
            entity_type=OperatorAuditEvent.EntityType.OPERATOR_NOTE,
            entity_id=str(note.id),
            reason=reason,
            before=None,
            after={
                "entity_type": entity_type,
                "entity_id": str(target.pk),
                "text": text,
                "tags": tag_names,
            },
            meta=None,
            ip=ip,
            user_agent=user_agent,
        )

        return Response(self._serialize_note(note), status=status.HTTP_201_CREATED)
