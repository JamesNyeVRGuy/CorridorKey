"""Ring buffer logging handler — captures recent log lines for the server."""

from __future__ import annotations

import logging
import threading
from collections import deque


class LogBuffer(logging.Handler):
    """Logging handler that stores the last N formatted log lines."""

    def __init__(self, capacity: int = 200):
        super().__init__()
        self._buffer: deque[str] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._cursor = 0  # tracks what's been sent

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._lock:
                self._buffer.append(msg)
        except Exception:
            self.handleError(record)

    def get_new_lines(self) -> list[str]:
        """Return log lines added since last call, then advance cursor."""
        with self._lock:
            total = len(self._buffer)
            if self._cursor >= total:
                return []
            lines = list(self._buffer)[self._cursor :]
            self._cursor = total
            return lines

    def get_all(self) -> list[str]:
        """Return all buffered log lines."""
        with self._lock:
            return list(self._buffer)


# Global instance
buffer = LogBuffer()


def install(level: int = logging.INFO) -> None:
    """Attach the buffer handler to the root logger."""
    buffer.setLevel(level)
    buffer.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(buffer)
