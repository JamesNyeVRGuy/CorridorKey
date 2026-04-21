"""Tests for write_node_env (CRKY-194).

The settings GUI save button used to silently fail when it couldn't write
the config file — bare open() with no error handling, status label stayed
blank, user assumed the button was broken. Now the save goes through a
pure function that returns (ok, message). These tests cover the happy
path and the failure modes that used to be invisible.
"""

from __future__ import annotations

import os
import sys

import pytest

# gui.py imports tkinter which may not be available on CI. Skip these tests
# if tkinter is missing rather than failing the whole suite.
tk_spec = None
try:
    import tkinter  # noqa: F401

    tk_spec = tkinter
except Exception:
    pass

pytestmark = pytest.mark.skipif(tk_spec is None, reason="tkinter not installed on this runner")

if tk_spec is not None:
    from web.node.gui import write_node_env


class TestWriteNodeEnv:
    def test_happy_path_writes_file(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_file = cfg_dir / "node.env"
        ok, msg = write_node_env(str(cfg_dir), str(cfg_file), "https://x.y", "tok", "my-node")
        assert ok is True
        assert "Saved" in msg
        contents = cfg_file.read_text()
        assert "CK_MAIN_URL=https://x.y" in contents
        assert "CK_AUTH_TOKEN=tok" in contents
        assert "CK_NODE_NAME=my-node" in contents
        assert "CK_NODE_GPUS=auto" in contents
        assert "CK_NODE_PREWARM=true" in contents

    def test_returns_error_when_dir_creation_fails(self, tmp_path, monkeypatch):
        def _raise(*a, **kw):
            raise PermissionError("fake permission denied")

        monkeypatch.setattr("os.makedirs", _raise)
        cfg_dir = tmp_path / "cfg"
        cfg_file = cfg_dir / "node.env"
        ok, msg = write_node_env(str(cfg_dir), str(cfg_file), "x", "y", "z")
        assert ok is False
        assert "Could not create" in msg
        assert "fake permission denied" in msg

    def test_returns_error_when_write_fails(self, tmp_path, monkeypatch):
        # Create the dir successfully, but blow up on open()
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "node.env"
        real_open = open

        def _fake_open(p, *a, **kw):
            if str(p).endswith(".tmp"):
                raise OSError("disk full")
            return real_open(p, *a, **kw)

        monkeypatch.setattr("builtins.open", _fake_open)
        ok, msg = write_node_env(str(cfg_dir), str(cfg_file), "x", "y", "z")
        assert ok is False
        assert "Save failed" in msg
        assert "disk full" in msg

    def test_atomic_write_leaves_old_file_intact_on_failure(self, tmp_path, monkeypatch):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "node.env"
        # Prime with old content
        cfg_file.write_text("CK_MAIN_URL=old\n")

        # Make os.replace fail (temp file was written but can't be moved into place)
        real_replace = os.replace

        def _fake_replace(src, dst):
            if str(dst) == str(cfg_file):
                raise OSError("rename blocked")
            return real_replace(src, dst)

        monkeypatch.setattr("os.replace", _fake_replace)
        ok, _msg = write_node_env(str(cfg_dir), str(cfg_file), "new", "t", "n")
        assert ok is False
        # Old file must still be intact — atomic write contract
        assert cfg_file.read_text() == "CK_MAIN_URL=old\n"

    def test_overwrites_existing_file(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_file = cfg_dir / "node.env"
        # Write once
        write_node_env(str(cfg_dir), str(cfg_file), "first", "a", "one")
        # Write again
        ok, _ = write_node_env(str(cfg_dir), str(cfg_file), "second", "b", "two")
        assert ok
        assert "CK_MAIN_URL=second" in cfg_file.read_text()
        assert "CK_NODE_NAME=two" in cfg_file.read_text()

    def test_handles_unicode_in_values(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_file = cfg_dir / "node.env"
        ok, _ = write_node_env(str(cfg_dir), str(cfg_file), "https://x", "t", "node-émoji-🚀")
        assert ok
        assert "node-émoji-🚀" in cfg_file.read_text(encoding="utf-8")


# Ensure ruff doesn't complain about unused imports:
assert sys is sys
