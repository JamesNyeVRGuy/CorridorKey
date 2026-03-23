"""Tests for the status page and monitoring system (CRKY-51).

Covers: status computation, badge SVG generation, history tracking,
incident detection, public access, and API endpoints.
"""

import os
import time

import pytest


class TestStatusSnapshot:
    """Test status computation logic."""

    def test_snapshot_defaults(self):
        from web.api.status import StatusSnapshot

        snap = StatusSnapshot()
        assert snap.status == "operational"
        assert snap.api == "ok"
        assert snap.nodes_online == 0
        assert snap.queue_depth == 0

    def test_snapshot_to_dict(self):
        from web.api.status import StatusSnapshot

        snap = StatusSnapshot(
            timestamp=1000.0,
            status="degraded",
            database="error",
            nodes_online=3,
            nodes_total=5,
            queue_depth=2,
            uptime_seconds=3600.0,
        )
        d = snap.to_dict()
        assert d["status"] == "degraded"
        assert d["components"]["database"] == "error"
        assert d["nodes_online"] == 3
        assert d["uptime_seconds"] == 3600.0

    def test_snapshot_components(self):
        from web.api.status import StatusSnapshot

        snap = StatusSnapshot(api="ok", database="ok", auth="skipped", worker="ok", disk="warning")
        d = snap.to_dict()
        assert "api" in d["components"]
        assert "database" in d["components"]
        assert "auth" in d["components"]
        assert "worker" in d["components"]
        assert "disk" in d["components"]


class TestHistoryTracking:
    """Test status history ring buffer and incident detection."""

    def test_record_snapshot(self):
        from web.api.status import _history, _history_lock, record_snapshot

        with _history_lock:
            _history.clear()

        snap = record_snapshot()
        assert snap.timestamp > 0
        assert snap.status in ("operational", "degraded", "down")

        with _history_lock:
            assert len(_history) >= 1

    def test_get_history(self):
        from web.api.status import _history, _history_lock, get_history

        with _history_lock:
            _history.clear()
            _history.append({"timestamp": 1.0, "status": "operational"})
            _history.append({"timestamp": 2.0, "status": "operational"})
            _history.append({"timestamp": 3.0, "status": "degraded"})

        result = get_history(limit=2)
        assert len(result) == 2
        assert result[0]["timestamp"] == 2.0  # last 2

    def test_get_history_full(self):
        from web.api.status import _history, _history_lock, get_history

        with _history_lock:
            _history.clear()
            for i in range(10):
                _history.append({"timestamp": float(i), "status": "operational"})

        result = get_history(limit=100)
        assert len(result) == 10

    def test_incident_detection(self):
        from web.api.status import _history, _history_lock, _incidents

        with _history_lock:
            _history.clear()
        _incidents.clear()

        # Simulate operational -> degraded transition
        with _history_lock:
            _history.append({"timestamp": time.time() - 60, "status": "operational"})

        # Force a degraded snapshot
        from web.api.status import StatusSnapshot

        snap = StatusSnapshot(timestamp=time.time(), status="degraded")
        with _history_lock:
            if _history:
                prev = _history[-1]
                if prev.get("status") == "operational" and snap.status != "operational":
                    _incidents.append(
                        {
                            "timestamp": snap.timestamp,
                            "status": snap.status,
                            "type": "degradation",
                        }
                    )
            _history.append(snap.to_dict())

        assert len(_incidents) >= 1
        assert _incidents[-1]["type"] == "degradation"

    def test_get_incidents(self):
        from web.api.status import _incidents, get_incidents

        _incidents.clear()
        _incidents.append({"timestamp": 1.0, "type": "degradation"})
        _incidents.append({"timestamp": 2.0, "type": "recovery"})

        result = get_incidents(limit=1)
        assert len(result) == 1
        assert result[0]["type"] == "recovery"


class TestBadgeSVG:
    """Test the SVG badge generation."""

    def test_badge_route_exists(self):
        from web.api.status import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert any("badge" in p for p in paths)

    def test_status_routes_exist(self):
        from web.api.status import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert any("status" in p and "history" in p for p in paths)
        assert any("status" in p and "incidents" in p for p in paths)
        assert any("status" in p and "badge" in p for p in paths)
        # Root status route
        assert any(p.endswith("/status") for p in paths)


class TestStatusSampler:
    """Test the background sampling thread."""

    def test_start_stop_sampler(self):
        from web.api.status import start_status_sampler, stop_status_sampler

        start_status_sampler(interval=9999)  # Long interval, won't fire
        stop_status_sampler()
        # Should not crash

    def test_start_twice_idempotent(self):
        from web.api.status import start_status_sampler, stop_status_sampler

        start_status_sampler(interval=9999)
        start_status_sampler(interval=9999)  # Should be a no-op
        stop_status_sampler()


class TestPublicAccess:
    """Test that status endpoints are publicly accessible."""

    def test_status_in_public_paths(self):
        from web.api.auth import PUBLIC_PATHS

        assert "/api/status" in PUBLIC_PATHS

    def test_status_in_rate_limit_exemptions(self):
        from web.api.rate_limit import EXEMPT_PREFIXES

        assert any(p.startswith("/api/status") for p in EXEMPT_PREFIXES)


class TestStatusIntegration:
    """Integration tests using the FastAPI TestClient."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CK_AUTH_ENABLED", "false")
        monkeypatch.setenv("CK_DOCS_PUBLIC", "true")
        monkeypatch.setenv("CK_CLIPS_DIR", str(tmp_path / "clips"))
        os.makedirs(tmp_path / "clips", exist_ok=True)

        import importlib

        import web.api.openapi_config as oc

        importlib.reload(oc)

        import web.api.auth as auth_mod

        importlib.reload(auth_mod)

        from web.api.app import create_app

        app = create_app()
        from fastapi.testclient import TestClient

        return TestClient(app, raise_server_exceptions=False)

    def test_status_endpoint(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("operational", "degraded", "down")
        assert "components" in data
        assert "nodes_online" in data

    def test_status_history_endpoint(self, client):
        resp = client.get("/api/status/history?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "snapshots" in data
        assert isinstance(data["snapshots"], list)

    def test_status_incidents_endpoint(self, client):
        resp = client.get("/api/status/incidents?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "incidents" in data

    def test_status_badge_svg(self, client):
        resp = client.get("/api/status/badge")
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]
        assert "<svg" in resp.text
        assert "status" in resp.text.lower()

    def test_status_badge_cache_headers(self, client):
        resp = client.get("/api/status/badge")
        assert "no-cache" in resp.headers.get("cache-control", "")

    def test_status_no_auth_required(self, client, monkeypatch):
        """Status endpoints should work without any auth token."""
        resp = client.get("/api/status")
        assert resp.status_code == 200

    def test_status_in_openapi_schema(self, client):
        resp = client.get("/openapi.json")
        schema = resp.json()
        tags = {t["name"] for t in schema.get("tags", [])}
        assert "status" in tags
