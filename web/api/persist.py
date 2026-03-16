"""Settings persistence — saves server state to a JSON file.

Stores settings, node configurations, and job history so they
survive server restarts. The file is written to the clips directory
(which is volume-mounted in Docker).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_STATE_FILE = "corridorkey_server_state.json"
_lock = threading.Lock()
_state_path: str = ""


def init(clips_dir: str) -> None:
    """Set the directory where state is stored."""
    global _state_path
    _state_path = os.path.join(clips_dir, _STATE_FILE)


def _read() -> dict[str, Any]:
    if not _state_path or not os.path.isfile(_state_path):
        return {}
    try:
        with open(_state_path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read state file: {e}")
        return {}


def _write(data: dict[str, Any]) -> None:
    if not _state_path:
        return
    try:
        with open(_state_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write state file: {e}")


def save_key(key: str, value: Any) -> None:
    """Save a single key to the state file."""
    with _lock:
        data = _read()
        data[key] = value
        _write(data)


def load_key(key: str, default: Any = None) -> Any:
    """Load a single key from the state file."""
    with _lock:
        data = _read()
        return data.get(key, default)


def save_settings(settings: dict[str, Any]) -> None:
    """Save multiple settings at once."""
    with _lock:
        data = _read()
        data.update(settings)
        _write(data)


def load_all() -> dict[str, Any]:
    """Load the entire state file."""
    with _lock:
        return _read()
