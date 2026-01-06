from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView


class OperatorThrottleMixin:
    throttle_scope = "operator"
    throttle_classes = [ScopedRateThrottle]


class OperatorAPIView(OperatorThrottleMixin, APIView):
    """Base API view for operator endpoints with scoped throttling."""

    pass
