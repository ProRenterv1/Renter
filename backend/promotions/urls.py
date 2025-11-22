from django.urls import path

from . import api

app_name = "promotions"

urlpatterns = [
    path("pricing/", api.promotion_pricing, name="promotion_pricing"),
    path("pay/", api.pay_for_promotion, name="promotion_pay"),
]
