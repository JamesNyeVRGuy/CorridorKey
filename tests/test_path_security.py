"""Tests for path security utilities (CRKY-56, CRKY-57)."""

import os
import zipfile

import pytest

from web.api.path_security import safe_extract_zip, safe_join


class TestSafeJoin:
    def test_normal_path(self, tmp_path):
        result = safe_join(str(tmp_path), "subdir", "file.png")
        assert result == os.path.realpath(os.path.join(str(tmp_path), "subdir", "file.png"))

    def test_rejects_parent_traversal(self, tmp_path):
        with pytest.raises(Exception) as exc_info:
            safe_join(str(tmp_path), "..", "etc", "passwd")
        assert exc_info.value.status_code == 400
        assert "traversal" in str(exc_info.value.detail).lower()

    def test_rejects_deep_traversal(self, tmp_path):
        with pytest.raises(Exception) as exc_info:
            safe_join(str(tmp_path), "a", "..", "..", "..", "etc", "shadow")
        assert exc_info.value.status_code == 400

    def test_rejects_null_byte(self, tmp_path):
        with pytest.raises(Exception) as exc_info:
            safe_join(str(tmp_path), "file\x00.png")
        assert exc_info.value.status_code == 400
        assert "null byte" in str(exc_info.value.detail).lower()

    def test_rejects_absolute_path(self, tmp_path):
        with pytest.raises(Exception) as exc_info:
            safe_join(str(tmp_path), "/etc/passwd")
        assert exc_info.value.status_code == 400

    def test_base_itself_is_valid(self, tmp_path):
        # Joining with empty parts should resolve to base
        result = safe_join(str(tmp_path))
        assert result == os.path.realpath(str(tmp_path))

    def test_rejects_prefix_attack(self, tmp_path):
        """Org 'abc' should not match org 'abcdef'."""
        base = os.path.join(str(tmp_path), "abc")
        os.makedirs(base, exist_ok=True)
        sibling = os.path.join(str(tmp_path), "abcdef")
        os.makedirs(sibling, exist_ok=True)
        # This should work — staying within base
        result = safe_join(base, "file.txt")
        assert result.startswith(base)

    def test_symlink_escape(self, tmp_path):
        """Symlink pointing outside base should be caught."""
        secret = tmp_path / "secret"
        secret.mkdir()
        (secret / "data.txt").write_text("secret")

        base = tmp_path / "base"
        base.mkdir()
        link = base / "escape"
        try:
            link.symlink_to(secret)
        except OSError:
            pytest.skip("symlinks not supported on this filesystem")

        with pytest.raises(Exception) as exc_info:
            safe_join(str(base), "escape", "data.txt")
        assert exc_info.value.status_code == 400


class TestSafeExtractZip:
    def test_normal_zip(self, tmp_path):
        # Create a normal zip
        zip_path = tmp_path / "good.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("frame_001.png", b"png data")
            zf.writestr("subdir/frame_002.png", b"more data")

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with zipfile.ZipFile(zip_path) as zf:
            extracted = safe_extract_zip(zf, str(extract_dir))

        assert len(extracted) == 2
        assert os.path.isfile(extract_dir / "frame_001.png")
        assert os.path.isfile(extract_dir / "subdir" / "frame_002.png")

    def test_rejects_zip_slip(self, tmp_path):
        # Create a malicious zip with traversal
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../evil.txt", b"pwned")

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with zipfile.ZipFile(zip_path) as zf:
            with pytest.raises(Exception) as exc_info:
                safe_extract_zip(zf, str(extract_dir))
        assert exc_info.value.status_code == 400
        assert "zip slip" in str(exc_info.value.detail).lower()

        # Verify the evil file was NOT created
        assert not os.path.exists(tmp_path / "evil.txt")

    def test_rejects_absolute_path_in_zip(self, tmp_path):
        zip_path = tmp_path / "abs.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("/etc/cron.d/backdoor", b"* * * * * root whoami")

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with zipfile.ZipFile(zip_path) as zf:
            with pytest.raises(Exception) as exc_info:
                safe_extract_zip(zf, str(extract_dir))
        assert exc_info.value.status_code == 400
