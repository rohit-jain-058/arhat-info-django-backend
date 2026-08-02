import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestHealthCheck:

    def test_health_ok(self, api_client):
        url = reverse('health_check')
        res = api_client.get(url)
        assert res.status_code in (status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE)
        assert 'status'  in res.data
        assert 'checks'  in res.data
        assert 'database' in res.data['checks']
        assert 'redis'    in res.data['checks']

    def test_health_db_fail(self, api_client):
        url = reverse('health_check')
        with patch('django.db.connection.ensure_connection', side_effect=Exception('DB down')):
            res = api_client.get(url)
        assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert res.data['status'] == 'unhealthy'

    def test_health_no_auth_required(self, api_client):
        """Health check must be publicly accessible."""
        url = reverse('health_check')
        res = api_client.get(url)
        assert res.status_code != status.HTTP_401_UNAUTHORIZED
