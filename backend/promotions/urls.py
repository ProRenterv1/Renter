from django.urls import path

from . import api

app_name = "promotions"

urlpatterns = [
    path("pricing/", api.promotion_pricing, name="promotion_pricing"),
    path("availability/", api.promotion_availability, name="promotion_availability"),
    path("pay/", api.pay_for_promotion, name="promotion_pay"),
]
