"""Structured JSON logging configuration (CRKY-50).

When CK_LOG_FORMAT=json, configures Python logging to emit structured
JSON lines suitable for Loki/Promtail/FluentBit ingestion. Each log
line includes: timestamp, level, logger name, message, and optional
structured fields (job_id, node_id, org_id, clip_name, user_id).

Default (CK_LOG_FORMAT=text or unset): standard human-readable format.
"""

from __future__ import annotations

import json
import logging
import os
import time

LOG_FORMAT = os.environ.get("CK_LOG_FORMAT", "text").lower()


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects.

    Structured fields can be attached via the `extra` dict when logging:
        logger.info("Job started", extra={"job_id": "abc", "clip_name": "shot_01"})
    """

    # Fields to extract from the log record's extra dict
    EXTRA_FIELDS = ("job_id", "node_id", "org_id", "clip_name", "user_id", "request_id")

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Include exception info
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc"] = self.formatException(record.exc_info)

        # Extract structured fields from extra
        for field in self.EXTRA_FIELDS:
            val = getattr(record, field, None)
            if val is not None:
                entry[field] = val

        return json.dumps(entry, default=str)


def configure_logging() -> None:
    """Configure root logger based on CK_LOG_FORMAT environment variable.

    Call this early in app startup (before other loggers are created).
    """
    level = logging.INFO

    if LOG_FORMAT == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logging.root.handlers.clear()
        logging.root.addHandler(handler)
        logging.root.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )
