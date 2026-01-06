"""Shared pytest configuration and fixtures."""

import pytest
from rest_framework.test import APIClient

pytest_plugins = [
    "bookings.tests.conftest",
]


@pytest.fixture
def api_client():
    """DRF API client for request/response helpers."""
    return APIClient()
