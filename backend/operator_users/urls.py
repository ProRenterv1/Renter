from django.urls import path

from operator_users.api import OperatorUserDetailView, OperatorUserListView

urlpatterns = [
    path("", OperatorUserListView.as_view(), name="operator_user_list"),
    path("<int:pk>/", OperatorUserDetailView.as_view(), name="operator_user_detail"),
]
