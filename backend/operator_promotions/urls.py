from django.urls import path

from operator_promotions.api import (
    OperatorPromotionCancelEarlyView,
    OperatorPromotionGrantCompedView,
    OperatorPromotionListView,
)

urlpatterns = [
    path("", OperatorPromotionListView.as_view(), name="operator_promotion_list"),
    path(
        "grant-comped/",
        OperatorPromotionGrantCompedView.as_view(),
        name="operator_promotion_grant_comped",
    ),
    path(
        "<int:pk>/cancel-early/",
        OperatorPromotionCancelEarlyView.as_view(),
        name="operator_promotion_cancel_early",
    ),
]
