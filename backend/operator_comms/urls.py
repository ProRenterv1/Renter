from django.urls import path

from operator_comms.api import OperatorConversationDetailView, OperatorConversationListView

app_name = "operator_comms"

urlpatterns = [
    path("", OperatorConversationListView.as_view(), name="operator_comms_list"),
    path("<int:pk>/", OperatorConversationDetailView.as_view(), name="operator_comms_detail"),
]
