"""In-memory log ring buffer for admin remote log viewing.

Captures log output into a bounded deque so admins can view recent
logs via the API without SSH access. No sensitive data filtering is
applied here — the admin endpoint requires platform_admin tier.

Installed automatically by logging_config.configure_logging().
"""

from __future__ import annotations

import logging
import threading
from collections import deque

_MAX_LINES = 2000
_buffer: deque[str] = deque(maxlen=_MAX_LINES)
_lock = threading.Lock()


class BufferHandler(logging.Handler):
    """Logging handler that appends formatted lines to the ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            with _lock:
                _buffer.append(line)
        except Exception:
            pass


def get_recent_logs(count: int = 200) -> list[str]:
    """Return the most recent log lines."""
    with _lock:
        items = list(_buffer)
    return items[-count:]


def install() -> None:
    """Add the buffer handler to the root logger."""
    handler = BufferHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.root.addHandler(handler)
