import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _test_s3_endpoint(settings):
    # Moto works best with the default AWS endpoints.
    settings.AWS_S3_ENDPOINT_URL = None
