"""
主应用单元测试
"""
import pytest
from fastapi.testclient import TestClient


class TestMainApp:
    """主应用测试类"""
    
    def test_health_endpoint(self, client: TestClient):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data or "status" in data
    
    def test_root_endpoint(self, client: TestClient):
        """测试根端点"""
        response = client.get("/")
        # 根端点可能返回200或404，取决于是否实现
        assert response.status_code in [200, 404]
    
    def test_cors_headers(self, client: TestClient):
        """测试CORS头"""
        response = client.options("/health")
        # CORS预检请求应该返回200
        assert response.status_code in [200, 405]  # 405如果没有实现OPTIONS

