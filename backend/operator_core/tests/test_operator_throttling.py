import importlib

import pytest
from django.urls import clear_url_caches

import renter.urls as renter_urls
from operator_disputes.api import OperatorDisputeListView
from operator_promotions.api import OperatorPromotionListView
from operator_users.api import OperatorUserListView

pytestmark = pytest.mark.django_db


def test_operator_views_use_throttle_scope(settings):
    settings.ENABLE_OPERATOR = True
    settings.OPS_ALLOWED_HOSTS = ["ops.example.com"]
    settings.ALLOWED_HOSTS = ["ops.example.com", "testserver"]
    clear_url_caches()
    importlib.reload(renter_urls)

    for view in (OperatorDisputeListView, OperatorPromotionListView, OperatorUserListView):
        assert getattr(view, "throttle_scope", None) == "operator"
