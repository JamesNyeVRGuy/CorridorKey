"""Tests for structured JSON logging (CRKY-50).

Covers: JSONFormatter output, extra field extraction, configure_logging
with text and JSON modes, and config file existence.
"""

import json
import logging
import os


class TestJSONFormatter:
    """Test the JSON log formatter."""

    def test_basic_format(self):
        from web.api.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello world",
            args=None,
            exc_info=None,
        )
        result = fmt.format(record)
        parsed = json.loads(result)
        assert parsed["level"] == "info"
        assert parsed["logger"] == "test.logger"
        assert parsed["msg"] == "Hello world"
        assert "ts" in parsed

    def test_extra_fields(self):
        from web.api.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Job started",
            args=None,
            exc_info=None,
        )
        record.job_id = "abc123"
        record.node_id = "node-1"
        record.clip_name = "shot_01"
        result = fmt.format(record)
        parsed = json.loads(result)
        assert parsed["job_id"] == "abc123"
        assert parsed["node_id"] == "node-1"
        assert parsed["clip_name"] == "shot_01"

    def test_missing_extra_fields_omitted(self):
        from web.api.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Just a warning",
            args=None,
            exc_info=None,
        )
        result = fmt.format(record)
        parsed = json.loads(result)
        assert "job_id" not in parsed
        assert "node_id" not in parsed
        assert parsed["level"] == "warning"

    def test_exception_info(self):
        from web.api.logging_config import JSONFormatter

        fmt = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Something failed",
            args=None,
            exc_info=exc_info,
        )
        result = fmt.format(record)
        parsed = json.loads(result)
        assert "exc" in parsed
        assert "ValueError" in parsed["exc"]

    def test_output_is_single_line(self):
        from web.api.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Multi\nline\nmessage",
            args=None,
            exc_info=None,
        )
        result = fmt.format(record)
        # JSON output should be a single line (newlines escaped)
        assert "\n" not in result


class TestConfigureLogging:
    """Test the configure_logging function."""

    def test_text_mode(self, monkeypatch):
        import web.api.logging_config as lc

        monkeypatch.setattr(lc, "LOG_FORMAT", "text")
        lc.configure_logging()
        # Should not crash and root logger should have handlers
        assert len(logging.root.handlers) > 0

    def test_json_mode(self, monkeypatch):
        import web.api.logging_config as lc

        monkeypatch.setattr(lc, "LOG_FORMAT", "json")
        lc.configure_logging()
        # Root logger should have a handler with JSONFormatter
        assert any(isinstance(h.formatter, lc.JSONFormatter) for h in logging.root.handlers)


class TestLokiConfig:
    """Test that Loki/Promtail config files exist."""

    def test_loki_config_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "deploy", "monitoring", "loki", "loki-config.yml")
        assert os.path.isfile(path)

    def test_promtail_config_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "deploy", "monitoring", "promtail", "promtail-config.yml")
        assert os.path.isfile(path)

    def test_log_explorer_dashboard_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "deploy", "monitoring", "grafana", "dashboards", "log-explorer.json"
        )
        assert os.path.isfile(path)

    def test_grafana_datasource_has_loki(self):
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "deploy",
            "monitoring",
            "grafana",
            "provisioning",
            "datasources",
            "prometheus.yml",
        )
        with open(path) as f:
            content = f.read()
        assert "Loki" in content or "loki" in content
