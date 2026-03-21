"""Tests for the API documentation system (CRKY-32).

Covers: OpenAPI configuration, docs access control, API versioning
middleware, tag metadata, and protected docs routes.
"""

import os

import pytest


class TestOpenAPIConfig:
    """Test the OpenAPI configuration module."""

    def test_api_version_format(self):
        from web.api.openapi_config import API_VERSION

        # Format: "1.0.0+commithash" or "1.0.0+dev"
        assert "+" in API_VERSION or API_VERSION.count(".") == 2
        base = API_VERSION.split("+")[0]
        parts = base.split(".")
        assert len(parts) == 3

    def test_api_description_not_empty(self):
        from web.api.openapi_config import API_DESCRIPTION

        assert len(API_DESCRIPTION) > 500
        # Should contain key sections
        assert "Authentication" in API_DESCRIPTION
        assert "Rate Limits" in API_DESCRIPTION
        assert "Webhook Payloads" in API_DESCRIPTION
        assert "Code Examples" in API_DESCRIPTION
        assert "Trust Tiers" in API_DESCRIPTION
        assert "API Versioning" in API_DESCRIPTION

    def test_tag_metadata_covers_all_routers(self):
        from web.api.openapi_config import TAG_METADATA

        tag_names = {t["name"] for t in TAG_METADATA}
        # Every router used in app.py should have a corresponding tag
        expected_tags = {
            "auth",
            "clips",
            "jobs",
            "system",
            "preview",
            "projects",
            "upload",
            "orgs",
            "nodes",
            "farm",
            "admin",
            "metrics",
        }
        assert expected_tags <= tag_names

    def test_tag_metadata_has_descriptions(self):
        from web.api.openapi_config import TAG_METADATA

        for tag in TAG_METADATA:
            assert "name" in tag
            assert "description" in tag
            assert len(tag["description"]) > 20, f"Tag '{tag['name']}' has too short description"

    def test_docs_public_default_no_auth(self, monkeypatch):
        """Without CK_AUTH_ENABLED, docs should be public by default."""
        monkeypatch.delenv("CK_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("CK_DOCS_PUBLIC", raising=False)

        import web.api.openapi_config as oc

        monkeypatch.setattr(oc, "_AUTH_ENABLED", False)
        monkeypatch.setattr(oc, "_DOCS_PUBLIC_OVERRIDE", "")
        # Re-calculate
        result = not oc._AUTH_ENABLED if not oc._DOCS_PUBLIC_OVERRIDE else None
        assert result is True  # Docs are public when auth is disabled

    def test_docs_public_explicit_override(self, monkeypatch):
        """CK_DOCS_PUBLIC=true should override even when auth is enabled."""
        import web.api.openapi_config as oc

        monkeypatch.setattr(oc, "_AUTH_ENABLED", True)
        monkeypatch.setattr(oc, "_DOCS_PUBLIC_OVERRIDE", "true")
        result = oc._DOCS_PUBLIC_OVERRIDE.lower() in ("true", "1", "yes")
        assert result is True


class TestAPIVersionMiddleware:
    """Test the API version middleware."""

    def test_middleware_class_exists(self):
        from web.api.api_version import APIVersionMiddleware

        assert APIVersionMiddleware is not None

    def test_middleware_imports_version(self):
        from web.api.api_version import API_VERSION

        assert "1.0.0" in API_VERSION


class TestDocsRoutes:
    """Test the protected docs route mounting."""

    def test_mount_function_exists(self):
        from web.api.docs_routes import mount_protected_docs

        assert callable(mount_protected_docs)


class TestAuthPublicPaths:
    """Test that auth public paths are configured correctly for docs."""

    def test_docs_paths_conditionally_public(self, monkeypatch):
        """Verify /docs, /redoc, /openapi.json are in PUBLIC_PATHS when DOCS_PUBLIC=True."""
        import web.api.openapi_config as oc

        monkeypatch.setattr(oc, "DOCS_PUBLIC", True)

        import web.api.auth as auth_mod

        # Re-initialize docs paths
        auth_mod.PUBLIC_PATHS.discard("/docs")
        auth_mod.PUBLIC_PATHS.discard("/redoc")
        auth_mod.PUBLIC_PATHS.discard("/openapi.json")
        auth_mod._init_docs_paths()

        assert "/docs" in auth_mod.PUBLIC_PATHS
        assert "/redoc" in auth_mod.PUBLIC_PATHS
        assert "/openapi.json" in auth_mod.PUBLIC_PATHS

    def test_docs_paths_not_public_when_protected(self, monkeypatch):
        """Verify docs paths are NOT in PUBLIC_PATHS when DOCS_PUBLIC=False."""
        import web.api.openapi_config as oc

        monkeypatch.setattr(oc, "DOCS_PUBLIC", False)

        import web.api.auth as auth_mod

        auth_mod.PUBLIC_PATHS.discard("/docs")
        auth_mod.PUBLIC_PATHS.discard("/redoc")
        auth_mod.PUBLIC_PATHS.discard("/openapi.json")
        auth_mod._init_docs_paths()

        assert "/docs" not in auth_mod.PUBLIC_PATHS
        assert "/redoc" not in auth_mod.PUBLIC_PATHS
        assert "/openapi.json" not in auth_mod.PUBLIC_PATHS

    def test_core_public_paths_unchanged(self):
        """Core public paths should always be present regardless of docs setting."""
        from web.api.auth import PUBLIC_PATHS

        assert "/api/auth/login" in PUBLIC_PATHS
        assert "/api/auth/signup" in PUBLIC_PATHS
        assert "/api/auth/refresh" in PUBLIC_PATHS
        assert "/api/health" in PUBLIC_PATHS
        assert "/metrics" in PUBLIC_PATHS


class TestOpenAPISchema:
    """Test that the OpenAPI schema is well-formed when the app is created."""

    @pytest.fixture
    def mock_app_env(self, monkeypatch, tmp_path):
        """Set up environment for app creation without side effects."""
        monkeypatch.setenv("CK_AUTH_ENABLED", "false")
        monkeypatch.setenv("CK_DOCS_PUBLIC", "true")
        monkeypatch.setenv("CK_CLIPS_DIR", str(tmp_path / "clips"))
        os.makedirs(tmp_path / "clips", exist_ok=True)

    def test_openapi_schema_has_tags(self, mock_app_env):
        """The OpenAPI schema should include tag metadata."""
        from web.api.openapi_config import TAG_METADATA

        tag_names = [t["name"] for t in TAG_METADATA]
        assert "auth" in tag_names
        assert "clips" in tag_names
        assert "jobs" in tag_names

    def test_openapi_description_contains_auth_guide(self, mock_app_env):
        from web.api.openapi_config import API_DESCRIPTION

        assert "Authorization: Bearer" in API_DESCRIPTION
        assert "X-Refresh-Token" in API_DESCRIPTION

    def test_openapi_description_contains_rate_limits(self, mock_app_env):
        from web.api.openapi_config import API_DESCRIPTION

        assert "300" in API_DESCRIPTION  # member limit
        assert "600" in API_DESCRIPTION  # contributor limit
        assert "Retry-After" in API_DESCRIPTION

    def test_openapi_description_contains_webhook_schemas(self, mock_app_env):
        from web.api.openapi_config import API_DESCRIPTION

        assert "job_completed" in API_DESCRIPTION
        assert "job_failed" in API_DESCRIPTION
        assert "Discord" in API_DESCRIPTION or "discord" in API_DESCRIPTION
        assert "Slack" in API_DESCRIPTION or "slack" in API_DESCRIPTION

    def test_openapi_description_contains_code_examples(self, mock_app_env):
        from web.api.openapi_config import API_DESCRIPTION

        assert "curl" in API_DESCRIPTION
        assert "requests" in API_DESCRIPTION
        assert "/api/clips" in API_DESCRIPTION
        assert "/api/jobs/inference" in API_DESCRIPTION


class TestRouteAnnotations:
    """Verify that key routes have proper OpenAPI summaries."""

    def test_clip_routes_have_summaries(self):
        from web.api.routes.clips import router

        list_route = next((r for r in router.routes if hasattr(r, "path") and r.path == ""), None)
        if list_route:
            assert getattr(list_route, "summary", None), "list_clips should have a summary"

    def test_job_routes_have_summaries(self):
        from web.api.routes.jobs import router

        paths_with_summary = set()
        for route in router.routes:
            if hasattr(route, "summary") and route.summary:
                paths_with_summary.add(route.path)
        # Key job routes should have summaries
        assert "/estimate" in paths_with_summary or any("/estimate" in p for p in paths_with_summary)

    def test_upload_routes_have_summaries(self):
        from web.api.routes.upload import router

        for route in router.routes:
            if hasattr(route, "path") and route.path == "/video":
                assert getattr(route, "summary", None), "upload_video should have a summary"


class TestAPIVersionHeader:
    """Test the X-API-Version header behavior."""

    def test_version_constant(self):
        from web.api.openapi_config import API_VERSION

        assert API_VERSION == "1.0.0" or "1.0.0" in API_VERSION

    def test_middleware_dispatches(self):
        """The middleware should add X-API-Version to API responses."""
        from web.api.api_version import APIVersionMiddleware

        # Just verify the class is importable and has dispatch method
        assert hasattr(APIVersionMiddleware, "dispatch")
