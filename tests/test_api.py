"""Basic tests for Gobber storage service."""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gobber.api import app, storage


@pytest.fixture(autouse=True)
def temp_db():
    """Use a temporary database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DB_PATH"] = db_path
    os.environ["API_KEY"] = "test-key"
    # Reinitialize storage with temp DB
    from gobber.storage import Storage
    app.storage = Storage(db_path=db_path)
    yield
    os.unlink(db_path)


client = TestClient(app)


class TestHealth:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "Gobber"


class TestWebhooks:
    def test_create_webhook(self):
        response = client.post(
            "/api/webhooks",
            json={"name": "test", "url": "https://example.com", "events": ["test.event"]},
            params={"x_key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test"
        assert "id" in data

    def test_list_webhooks(self):
        response = client.get("/api/webhooks", params={"x_key": "test-key"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_webhook_not_found(self):
        response = client.get("/api/webhooks/nonexistent", params={"x_key": "test-key"})
        assert response.status_code == 404


class TestFeatureFlags:
    def test_create_flag(self):
        response = client.post(
            "/api/flags",
            json={"name": "dark-mode", "is_enabled": True, "description": "Enable dark mode"},
            params={"x_key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "dark-mode"
        assert data["is_enabled"] is True

    def test_list_flags(self):
        response = client.get("/api/flags", params={"x_key": "test-key"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestCache:
    def test_set_and_get_cache(self):
        # Set
        response = client.post(
            "/api/cache",
            json={"key": "test-key-cache", "value": {"hello": "world"}, "ttl_seconds": 300},
            params={"x_key": "test-key"},
        )
        assert response.status_code == 200

        # Get
        response = client.get("/api/cache/test-key-cache", params={"x_key": "test-key"})
        assert response.status_code == 200
        data = response.json()
        assert data["value"]["hello"] == "world"


class TestRBAC:
    def test_create_role(self):
        response = client.post(
            "/api/roles",
            json={"name": "admin", "permissions": ["read", "write"], "description": "Admin role"},
            params={"x_key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "admin"

    def test_list_roles(self):
        response = client.get("/api/roles", params={"x_key": "test-key"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestAuth:
    def test_invalid_api_key(self):
        response = client.get("/api/webhooks", params={"x_key": "wrong-key"})
        assert response.status_code == 401
