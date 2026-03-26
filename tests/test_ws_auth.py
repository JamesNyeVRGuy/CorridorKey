"""Tests for WebSocket authentication (CRKY-13)."""

import time

import jwt


class TestWSTokenValidation:
    """Test the JWT validation function used by the WebSocket endpoint."""

    SECRET = "test-secret-key"
    ALGORITHMS = ["HS256"]

    def _make_token(self, claims: dict, secret: str | None = None) -> str:
        return jwt.encode(claims, secret or self.SECRET, algorithm="HS256")

    def test_valid_token(self, monkeypatch):
        from web.api import ws

        monkeypatch.setattr("web.api.auth.JWT_SECRET", self.SECRET)
        monkeypatch.setattr("web.api.auth.JWT_ALGORITHMS", self.ALGORITHMS)

        token = self._make_token(
            {
                "sub": "user-1",
                "email": "a@b.com",
                "aud": "authenticated",
                "exp": int(time.time()) + 3600,
                "app_metadata": {"tier": "member", "org_ids": ["org-1"]},
            }
        )
        claims = ws._validate_ws_token(token)
        assert claims is not None
        assert claims["sub"] == "user-1"
        assert claims["app_metadata"]["org_ids"] == ["org-1"]

    def test_expired_token(self, monkeypatch):
        from web.api import ws

        monkeypatch.setattr("web.api.auth.JWT_SECRET", self.SECRET)
        monkeypatch.setattr("web.api.auth.JWT_ALGORITHMS", self.ALGORITHMS)

        token = self._make_token(
            {
                "sub": "user-1",
                "aud": "authenticated",
                "exp": int(time.time()) - 3600,
            }
        )
        assert ws._validate_ws_token(token) is None

    def test_wrong_secret(self, monkeypatch):
        from web.api import ws

        monkeypatch.setattr("web.api.auth.JWT_SECRET", self.SECRET)
        monkeypatch.setattr("web.api.auth.JWT_ALGORITHMS", self.ALGORITHMS)

        token = self._make_token(
            {
                "sub": "user-1",
                "aud": "authenticated",
                "exp": int(time.time()) + 3600,
            },
            secret="wrong-secret",
        )
        assert ws._validate_ws_token(token) is None

    def test_wrong_audience(self, monkeypatch):
        from web.api import ws

        monkeypatch.setattr("web.api.auth.JWT_SECRET", self.SECRET)
        monkeypatch.setattr("web.api.auth.JWT_ALGORITHMS", self.ALGORITHMS)

        token = self._make_token(
            {
                "sub": "user-1",
                "aud": "wrong-audience",
                "exp": int(time.time()) + 3600,
            }
        )
        assert ws._validate_ws_token(token) is None

    def test_malformed_token(self, monkeypatch):
        from web.api import ws

        monkeypatch.setattr("web.api.auth.JWT_SECRET", self.SECRET)
        monkeypatch.setattr("web.api.auth.JWT_ALGORITHMS", self.ALGORITHMS)

        assert ws._validate_ws_token("not-a-jwt") is None
        assert ws._validate_ws_token("") is None


class TestAuthenticatedConnection:
    def test_defaults(self):
        from web.api.ws import AuthenticatedConnection

        conn = AuthenticatedConnection(ws=None)
        assert conn.user_id == ""
        assert conn.org_ids == []

    def test_with_user(self):
        from web.api.ws import AuthenticatedConnection

        conn = AuthenticatedConnection(ws=None, user_id="u1", org_ids=["o1", "o2"])
        assert conn.user_id == "u1"
        assert conn.org_ids == ["o1", "o2"]
