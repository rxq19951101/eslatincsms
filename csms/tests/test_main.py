"""主应用运行时契约测试。"""

from fastapi.testclient import TestClient


class TestMainApp:
    """主应用测试类"""
    
    def test_health_endpoint(self, client: TestClient):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data or "status" in data
    
    def test_cors_preflight_returns_configured_headers(self, client: TestClient):
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "GET" in response.headers["access-control-allow-methods"]
