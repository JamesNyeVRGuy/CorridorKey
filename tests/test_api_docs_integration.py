"""Integration tests for API documentation endpoints (CRKY-32).

Uses FastAPI TestClient to verify docs access control, OpenAPI schema
generation, API version headers, and protected/public doc routes.
"""

import os
import time

import jwt
import pytest
from fastapi.testclient import TestClient

TEST_SECRET = "test_secret_key_at_least_32_characters_long"


def _make_token(tier: str = "member", user_id: str = "test-user") -> str:
    """Create a test JWT."""
    payload = {
        "sub": user_id,
        "email": "test@example.com",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "app_metadata": {"tier": tier},
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


@pytest.fixture
def public_docs_app(monkeypatch, tmp_path):
    """Create app with docs publicly accessible (no auth)."""
    monkeypatch.setenv("CK_AUTH_ENABLED", "false")
    monkeypatch.setenv("CK_DOCS_PUBLIC", "true")
    monkeypatch.setenv("CK_CLIPS_DIR", str(tmp_path / "clips"))
    os.makedirs(tmp_path / "clips", exist_ok=True)

    # Force reload of config modules to pick up env changes
    import importlib

    import web.api.openapi_config as oc

    importlib.reload(oc)

    import web.api.auth as auth_mod

    importlib.reload(auth_mod)

    from web.api.app import create_app

    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def protected_docs_app(monkeypatch, tmp_path):
    """Create app with docs behind auth."""
    monkeypatch.setenv("CK_AUTH_ENABLED", "true")
    monkeypatch.setenv("CK_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("CK_DOCS_PUBLIC", "false")
    monkeypatch.setenv("CK_CLIPS_DIR", str(tmp_path / "clips"))
    os.makedirs(tmp_path / "clips", exist_ok=True)

    import importlib

    import web.api.openapi_config as oc

    importlib.reload(oc)

    import web.api.auth as auth_mod

    importlib.reload(auth_mod)

    from web.api.app import create_app

    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


class TestPublicDocs:
    """Test docs when CK_DOCS_PUBLIC=true."""

    def test_swagger_ui_accessible(self, public_docs_app):
        resp = public_docs_app.get("/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()

    def test_redoc_accessible(self, public_docs_app):
        resp = public_docs_app.get("/redoc")
        assert resp.status_code == 200

    def test_openapi_json_accessible(self, public_docs_app):
        resp = public_docs_app.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema
        assert "info" in schema
        assert schema["info"]["title"] == "CorridorKey API"
        assert "1.0.0" in schema["info"]["version"]

    def test_openapi_has_tags(self, public_docs_app):
        resp = public_docs_app.get("/openapi.json")
        schema = resp.json()
        assert "tags" in schema
        tag_names = {t["name"] for t in schema["tags"]}
        assert "auth" in tag_names
        assert "clips" in tag_names
        assert "jobs" in tag_names
        assert "system" in tag_names
        assert "farm" in tag_names
        assert "nodes" in tag_names

    def test_openapi_has_description(self, public_docs_app):
        resp = public_docs_app.get("/openapi.json")
        schema = resp.json()
        desc = schema["info"]["description"]
        assert "Authentication" in desc
        assert "Rate Limits" in desc

    def test_openapi_paths_present(self, public_docs_app):
        resp = public_docs_app.get("/openapi.json")
        schema = resp.json()
        paths = schema.get("paths", {})
        # Core endpoints should be in the schema
        assert "/api/clips" in paths or "/api/clips/" in paths
        assert "/api/jobs" in paths or "/api/jobs/" in paths
        assert "/api/auth/login" in paths


class TestProtectedDocs:
    """Test docs when CK_DOCS_PUBLIC=false (auth required)."""

    def test_swagger_requires_auth(self, protected_docs_app):
        resp = protected_docs_app.get("/docs")
        assert resp.status_code == 401

    def test_redoc_requires_auth(self, protected_docs_app):
        resp = protected_docs_app.get("/redoc")
        assert resp.status_code == 401

    def test_openapi_json_requires_auth(self, protected_docs_app):
        resp = protected_docs_app.get("/openapi.json")
        assert resp.status_code == 401

    def test_swagger_accessible_with_token(self, protected_docs_app):
        token = _make_token("member")
        resp = protected_docs_app.get("/docs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_redoc_accessible_with_token(self, protected_docs_app):
        token = _make_token("member")
        resp = protected_docs_app.get("/redoc", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_openapi_json_accessible_with_token(self, protected_docs_app):
        token = _make_token("member")
        resp = protected_docs_app.get("/openapi.json", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "CorridorKey API"

    def test_pending_user_can_view_docs(self, protected_docs_app):
        """Even pending users should be able to view API docs."""
        token = _make_token("pending")
        resp = protected_docs_app.get("/docs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestAPIVersionHeader:
    """Test X-API-Version header on API responses."""

    def test_api_endpoints_have_version_header(self, public_docs_app):
        resp = public_docs_app.get("/api/health")
        assert "X-API-Version" in resp.headers
        assert "1.0.0" in resp.headers["X-API-Version"]

    def test_non_api_endpoints_no_version_header(self, public_docs_app):
        # SPA fallback routes shouldn't have the version header
        # (unless they're docs routes)
        resp = public_docs_app.get("/some-spa-page")
        # This might be a 404 or SPA fallback — either way, no version header
        assert "X-API-Version" not in resp.headers or resp.status_code == 404

    def test_docs_endpoints_have_version_header(self, public_docs_app):
        resp = public_docs_app.get("/openapi.json")
        assert "X-API-Version" in resp.headers
        assert "1.0.0" in resp.headers["X-API-Version"]


class TestHealthEndpointUnchanged:
    """Verify the health endpoint still works (regression)."""

    def test_health_no_auth(self, public_docs_app):
        resp = public_docs_app.get("/api/health")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "healthy" in data
        assert "checks" in data
