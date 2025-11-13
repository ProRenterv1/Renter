from unittest import mock

import pytest
from django.core.cache import cache

from users.geo import get_location_for_ip


def test_private_ip_returns_label(settings):
    settings.IP_GEO_PRIVATE_LABEL = "Local network"
    settings.IP_GEO_LOOKUP_ENABLED = True  # should still short-circuit
    assert get_location_for_ip("127.0.0.1") == "Local network"


@pytest.mark.django_db
@mock.patch("users.geo.requests.get")
def test_public_ip_uses_lookup_and_caches(mock_get, settings):
    settings.IP_GEO_LOOKUP_ENABLED = True
    settings.IP_GEO_LOOKUP_TIMEOUT = 1
    settings.IP_GEO_CACHE_TTL = 60
    settings.IP_GEO_LOOKUP_URL = "https://example.com/{ip}"

    mock_response = mock.Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "city": "Calgary",
        "region": "Alberta",
        "country_name": "Canada",
    }
    mock_get.return_value = mock_response

    ip = "8.8.8.8"
    cache.delete(f"ip_geo:{ip}")
    assert get_location_for_ip(ip) == "Calgary, Alberta, Canada"
    # Second call should be served from cache without another HTTP request.
    assert get_location_for_ip(ip) == "Calgary, Alberta, Canada"
    assert mock_get.call_count == 1
    cache.delete(f"ip_geo:{ip}")
