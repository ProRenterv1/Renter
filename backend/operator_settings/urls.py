from django.urls import path

from operator_settings.api import (
    OperatorFeatureFlagsView,
    OperatorJobRunsView,
    OperatorMaintenanceView,
    OperatorRunJobView,
    OperatorSettingsCurrentView,
    OperatorSettingsView,
)

app_name = "operator_settings"

urlpatterns = [
    path("settings/", OperatorSettingsView.as_view(), name="operator_settings"),
    path(
        "settings/current/", OperatorSettingsCurrentView.as_view(), name="operator_settings_current"
    ),
    path("feature-flags/", OperatorFeatureFlagsView.as_view(), name="operator_feature_flags"),
    path("maintenance/", OperatorMaintenanceView.as_view(), name="operator_maintenance"),
    path("jobs/", OperatorJobRunsView.as_view(), name="operator_jobs"),
    path("jobs/run/", OperatorRunJobView.as_view(), name="operator_jobs_run"),
]
