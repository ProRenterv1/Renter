import importlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches

import renter.urls as renter_urls
from core.settings_resolver import clear_settings_cache

OPS_HOST = "ops.example.com"

User = get_user_model()


@pytest.fixture(autouse=True)
def enable_operator_routes(settings):
    original_enable = settings.ENABLE_OPERATOR
    original_hosts = getattr(settings, "OPS_ALLOWED_HOSTS", [])
    original_allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))

    settings.ENABLE_OPERATOR = True
    settings.OPS_ALLOWED_HOSTS = [OPS_HOST]
    settings.ALLOWED_HOSTS = [OPS_HOST, "public.example.com", "testserver"]
    clear_url_caches()
    importlib.reload(renter_urls)
    yield
    settings.ENABLE_OPERATOR = original_enable
    settings.OPS_ALLOWED_HOSTS = original_hosts
    settings.ALLOWED_HOSTS = original_allowed_hosts
    clear_url_caches()
    importlib.reload(renter_urls)


@pytest.fixture(autouse=True)
def _clear_in_process_settings_cache():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def operator_admin_user():
    group, _ = Group.objects.get_or_create(name="operator_admin")
    user = User.objects.create_user(
        username="op-admin",
        email="admin@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


@pytest.fixture
def operator_support_user():
    group, _ = Group.objects.get_or_create(name="operator_support")
    user = User.objects.create_user(
        username="op-support",
        email="support@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


@pytest.fixture
def normal_user():
    return User.objects.create_user(
        username="regular-user",
        email="regular@example.com",
        password="pass123",
        is_staff=False,
    )


@pytest.fixture
def ops_client(api_client):
    api_client.defaults["HTTP_HOST"] = OPS_HOST
    return api_client


@pytest.fixture
def operator_admin_client(ops_client, operator_admin_user):
    ops_client.force_authenticate(user=operator_admin_user)
    return ops_client


@pytest.fixture
def operator_support_client(ops_client, operator_support_user):
    ops_client.force_authenticate(user=operator_support_user)
    return ops_client


@pytest.fixture
def normal_user_ops_client(ops_client, normal_user):
    ops_client.force_authenticate(user=normal_user)
    return ops_client


@pytest.fixture
def db_setting_factory():
    from operator_settings.models import DbSetting

    def _create(*, key="TEST_KEY", value_json=1, value_type="int", **kwargs):
        return DbSetting.objects.create(
            key=key,
            value_json=value_json,
            value_type=value_type,
            **kwargs,
        )

    return _create


@pytest.fixture
def feature_flag_factory():
    from operator_settings.models import FeatureFlag

    def _create(*, key="FLAG_X", enabled=False, **kwargs):
        return FeatureFlag.objects.create(key=key, enabled=enabled, **kwargs)

    return _create


@pytest.fixture
def maintenance_banner_factory():
    from operator_settings.models import MaintenanceBanner

    def _create(*, enabled=False, severity="info", message="", **kwargs):
        return MaintenanceBanner.objects.create(
            enabled=enabled,
            severity=severity,
            message=message,
            **kwargs,
        )

    return _create


@pytest.fixture
def dispute_factory():
    from disputes.models import DisputeCase

    def _create(
        *,
        booking,
        opened_by=None,
        opened_by_role=None,
        category=DisputeCase.Category.DAMAGE,
        status=DisputeCase.Status.OPEN,
        description="test dispute",
        **kwargs,
    ):
        if opened_by is None:
            opened_by = booking.renter
        if opened_by_role is None:
            opened_by_role = (
                DisputeCase.OpenedByRole.RENTER
                if getattr(opened_by, "id", None) == getattr(booking.renter, "id", None)
                else DisputeCase.OpenedByRole.OWNER
            )
        return DisputeCase.objects.create(
            booking=booking,
            opened_by=opened_by,
            opened_by_role=opened_by_role,
            category=category,
            description=description,
            status=status,
            **kwargs,
        )

    return _create
