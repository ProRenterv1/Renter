from __future__ import annotations

from django.db import models
from rest_framework import permissions, viewsets
from rest_framework.exceptions import MethodNotAllowed

from .models import Review
from .serializers import ReviewSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    """Allow participants to create and view booking reviews."""

    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Review.objects.none()

        qs = Review.objects.filter(models.Q(author=user) | models.Q(subject=user))

        booking_param = self.request.query_params.get("booking")
        if booking_param:
            try:
                booking_id = int(booking_param)
            except (TypeError, ValueError):
                booking_id = None
            if booking_id:
                qs = qs.filter(booking_id=booking_id)

        subject_param = self.request.query_params.get("subject")
        if subject_param:
            try:
                subject_id = int(subject_param)
            except (TypeError, ValueError):
                subject_id = None
            if subject_id:
                qs = qs.filter(subject_id=subject_id)

        role_param = self.request.query_params.get("role")
        if role_param in Review.Role.values:
            qs = qs.filter(role=role_param)

        return qs

    def update(self, *args, **kwargs):
        raise MethodNotAllowed("PUT")

    def partial_update(self, *args, **kwargs):
        raise MethodNotAllowed("PATCH")

    def destroy(self, *args, **kwargs):
        raise MethodNotAllowed("DELETE")
