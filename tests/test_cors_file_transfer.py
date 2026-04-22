"""CORS origin resolution including CKWEB_FILE_BASE split-host integration.

Covers _resolve_cors_origins() in web.api.app, which is called at app creation
time to build the allow_origins list handed to CORSMiddleware. The important
guarantees:

- CK_CORS_ORIGINS is an explicit override; if set, it wins outright.
- Otherwise the list is derived from CK_SITE_URL / SITE_URL so self-hosters
  on a custom domain are not forced to also configure CK_CORS_ORIGINS.
- CKWEB_FILE_BASE contributes a cross-origin entry for the file-transfer host,
  with https:// assumed when the value is a bare hostname.
- Duplicates are dropped, and leading/trailing whitespace is tolerated.
"""

from __future__ import annotations

import pytest

from web.api.app import _resolve_cors_origins


@pytest.fixture(autouse=True)
def _clear_cors_env(monkeypatch):
    """Every test starts with a clean env so nothing leaks between cases."""
    for var in ("CK_CORS_ORIGINS", "CK_SITE_URL", "SITE_URL", "CKWEB_FILE_BASE"):
        monkeypatch.delenv(var, raising=False)


class TestDefaults:
    def test_default_when_nothing_set(self):
        assert _resolve_cors_origins() == [
            "https://corridorkey.cloud",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]


class TestExplicitOverride:
    def test_ck_cors_origins_fully_overrides(self, monkeypatch):
        monkeypatch.setenv("CK_CORS_ORIGINS", "https://a.example,https://b.example")
        monkeypatch.setenv("CK_SITE_URL", "https://ignored.example")
        assert _resolve_cors_origins() == ["https://a.example", "https://b.example"]

    def test_whitespace_and_empty_entries_are_stripped(self, monkeypatch):
        monkeypatch.setenv("CK_CORS_ORIGINS", " https://a.com , https://b.com ,, ")
        assert _resolve_cors_origins() == ["https://a.com", "https://b.com"]

    def test_override_still_appends_file_base(self, monkeypatch):
        monkeypatch.setenv("CK_CORS_ORIGINS", "https://a.example")
        monkeypatch.setenv("CKWEB_FILE_BASE", "files.a.example")
        assert _resolve_cors_origins() == [
            "https://a.example",
            "https://files.a.example",
        ]


class TestSiteUrlDerivation:
    def test_ck_site_url_becomes_first_origin(self, monkeypatch):
        monkeypatch.setenv("CK_SITE_URL", "https://custom.example")
        origins = _resolve_cors_origins()
        assert origins[0] == "https://custom.example"
        assert "http://localhost:3000" in origins
        assert "http://127.0.0.1:3000" in origins

    def test_falls_back_to_legacy_site_url_when_ck_site_url_empty(self, monkeypatch):
        monkeypatch.setenv("CK_SITE_URL", "")
        monkeypatch.setenv("SITE_URL", "https://legacy.example")
        assert _resolve_cors_origins()[0] == "https://legacy.example"

    def test_trailing_slash_is_stripped(self, monkeypatch):
        monkeypatch.setenv("CK_SITE_URL", "https://custom.example/")
        assert "https://custom.example" in _resolve_cors_origins()
        assert "https://custom.example/" not in _resolve_cors_origins()


class TestFileBaseOrigin:
    def test_bare_hostname_gets_https_scheme(self, monkeypatch):
        monkeypatch.setenv("CKWEB_FILE_BASE", "files.corridorkey.cloud")
        assert "https://files.corridorkey.cloud" in _resolve_cors_origins()

    def test_explicit_http_scheme_is_preserved(self, monkeypatch):
        monkeypatch.setenv("CKWEB_FILE_BASE", "http://files.local:8080")
        origins = _resolve_cors_origins()
        assert "http://files.local:8080" in origins
        assert "https://http://files.local:8080" not in origins

    def test_explicit_https_scheme_is_preserved(self, monkeypatch):
        monkeypatch.setenv("CKWEB_FILE_BASE", "https://files.example")
        origins = _resolve_cors_origins()
        assert "https://files.example" in origins
        assert "https://https://files.example" not in origins

    def test_trailing_slash_on_file_base_is_stripped(self, monkeypatch):
        monkeypatch.setenv("CKWEB_FILE_BASE", "files.example/")
        origins = _resolve_cors_origins()
        assert "https://files.example" in origins
        assert "https://files.example/" not in origins

    def test_empty_file_base_is_ignored(self, monkeypatch):
        monkeypatch.setenv("CKWEB_FILE_BASE", "")
        origins = _resolve_cors_origins()
        assert all("files." not in o for o in origins)

    def test_whitespace_only_file_base_is_ignored(self, monkeypatch):
        monkeypatch.setenv("CKWEB_FILE_BASE", "   ")
        origins = _resolve_cors_origins()
        assert all("files." not in o for o in origins)


class TestDeduplication:
    def test_site_url_equal_to_localhost_does_not_duplicate(self, monkeypatch):
        monkeypatch.setenv("CK_SITE_URL", "http://localhost:3000")
        origins = _resolve_cors_origins()
        assert origins.count("http://localhost:3000") == 1
        assert origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_file_base_already_in_ck_cors_origins_does_not_duplicate(self, monkeypatch):
        monkeypatch.setenv(
            "CK_CORS_ORIGINS",
            "https://corridorkey.cloud,https://files.corridorkey.cloud",
        )
        monkeypatch.setenv("CKWEB_FILE_BASE", "files.corridorkey.cloud")
        origins = _resolve_cors_origins()
        assert origins.count("https://files.corridorkey.cloud") == 1

    def test_duplicate_in_explicit_override_is_collapsed(self, monkeypatch):
        monkeypatch.setenv(
            "CK_CORS_ORIGINS",
            "https://a.com,https://a.com,https://b.com",
        )
        assert _resolve_cors_origins() == ["https://a.com", "https://b.com"]


class TestEndToEnd:
    def test_typical_split_host_production_config(self, monkeypatch):
        """Mirrors the shape of a real deployment: custom domain + file split."""
        monkeypatch.setenv("CK_SITE_URL", "https://corridorkey.cloud")
        monkeypatch.setenv("CKWEB_FILE_BASE", "files.corridorkey.cloud")
        assert _resolve_cors_origins() == [
            "https://corridorkey.cloud",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://files.corridorkey.cloud",
        ]

    def test_self_hoster_custom_domain_without_split(self, monkeypatch):
        monkeypatch.setenv("CK_SITE_URL", "https://vfx.mystudio.com")
        assert _resolve_cors_origins() == [
            "https://vfx.mystudio.com",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
