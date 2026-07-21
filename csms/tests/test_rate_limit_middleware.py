"""Rate-limit behavior that protects App/Admin from shared-NAT request storms."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import RateLimitMiddleware


def _client(limit: int) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_minute=limit)

    @app.get('/api/v1/dashboard/summary')
    def dashboard():
        return {'ok': True}

    @app.get('/api/v1/sites')
    def sites():
        return {'ok': True}

    return TestClient(app)


def test_options_does_not_consume_rate_limit_quota():
    with _client(2) as client:
        headers = {'Authorization': 'Bearer admin-a'}
        assert client.get('/api/v1/dashboard/summary', headers=headers).status_code == 200
        client.options('/api/v1/dashboard/summary', headers=headers)
        assert client.get('/api/v1/dashboard/summary', headers=headers).status_code == 200
        limited = client.get('/api/v1/dashboard/summary', headers=headers)

    assert limited.status_code == 429
    assert int(limited.headers['retry-after']) >= 1


def test_authenticated_clients_and_route_categories_have_separate_buckets():
    with _client(1) as client:
        admin_a = {'Authorization': 'Bearer admin-a'}
        admin_b = {'Authorization': 'Bearer admin-b'}

        assert client.get('/api/v1/dashboard/summary', headers=admin_a).status_code == 200
        assert client.get('/api/v1/sites', headers=admin_a).status_code == 200
        assert client.get('/api/v1/dashboard/summary', headers=admin_b).status_code == 200
        assert client.get('/api/v1/dashboard/summary', headers=admin_a).status_code == 429
