"""Basic tests for Gobber storage service."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Set API_KEY BEFORE importing the app module
os.environ["API_KEY"] = "test-key"

from gobber.api import app


@pytest.fixture(autouse=True)
def temp_db():
    """Use a temporary database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DB_PATH"] = db_path
    # Reinitialize storage with temp DB
    from gobber.storage import Storage

    app.storage = Storage(db_path=db_path)
    yield
    # Clean up tables before removing DB
    try:
        import sqlite3

        conn = sqlite3.connect(db_path)
        for table in [
            "webhooks",
            "feature_flags",
            "cache_entries",
            "roles",
            "role_permissions",
        ]:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()
    except Exception:
        pass
    try:
        os.unlink(db_path)
    except OSError:
        pass


client = TestClient(app)
HEADERS = {"Authorization": "Bearer test-key"}


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
            json={
                "name": "test",
                "url": "https://example.com",
                "events": ["test.event"],
            },
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test"
        assert "id" in data

    def test_list_webhooks(self):
        response = client.get("/api/webhooks", headers=HEADERS)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_webhook_not_found(self):
        response = client.get("/api/webhooks/nonexistent", headers=HEADERS)
        assert response.status_code == 404


class TestFeatureFlags:
    def test_create_flag(self):
        import uuid

        flag_name = f"dark-mode-{uuid.uuid4().hex[:6]}"
        response = client.post(
            "/api/flags",
            json={
                "name": flag_name,
                "is_enabled": True,
                "description": "Enable dark mode",
            },
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == flag_name
        assert data["is_enabled"] is True

    def test_list_flags(self):
        response = client.get("/api/flags", headers=HEADERS)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestCache:
    def test_set_and_get_cache(self):
        # Set
        response = client.post(
            "/api/cache",
            json={
                "key": "test-key-cache",
                "value": {"hello": "world"},
                "ttl_seconds": 300,
            },
            headers=HEADERS,
        )
        assert response.status_code == 200

        # Get
        response = client.get("/api/cache/test-key-cache", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["value"]["hello"] == "world"


class TestRBAC:
    def test_create_role(self):
        import uuid

        role_name = f"admin-{uuid.uuid4().hex[:6]}"
        response = client.post(
            "/api/roles",
            json={
                "name": role_name,
                "permissions": ["read", "write"],
                "description": "Admin role",
            },
            headers=HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == role_name

    def test_list_roles(self):
        response = client.get("/api/roles", headers=HEADERS)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestAuth:
    def test_invalid_api_key(self):
        response = client.get("/api/webhooks", headers={"Authorization": "***"})
        assert response.status_code == 401

    def test_missing_auth(self):
        response = client.get("/api/webhooks")
        assert response.status_code == 401

    def test_query_param_rejected(self):
        response = client.get("/api/webhooks", params={"x_key": "test-key"})
        assert response.status_code == 401
