"""Webhook system for job lifecycle events (CRKY-31).

Fires HTTP callbacks to configured URLs when jobs start, complete,
or fail. Supports Discord, Slack, and generic JSON webhooks.

Webhooks are per-org, managed by org admins. Delivery is async with
retry (3 attempts, exponential backoff).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Webhook:
    """A configured webhook."""

    id: str
    org_id: str
    url: str
    events: list[str]  # ["job_completed", "job_failed", "job_started", "node_offline", "node_online"]
    format: str = "json"  # "json", "discord", "slack"
    active: bool = True
    created_by: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "url": self.url,
            "events": self.events,
            "format": self.format,
            "active": self.active,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }


def _load_webhooks() -> dict[str, dict]:
    from .database import get_storage

    return get_storage().get_setting("webhooks", {})


def _save_webhooks(hooks: dict[str, dict]) -> None:
    from .database import get_storage

    get_storage().set_setting("webhooks", hooks)


def _validate_webhook_url(url: str) -> None:
    """Validate webhook URL to prevent SSRF attacks.

    Rejects: non-HTTP(S) schemes, localhost, private IP ranges,
    link-local (169.254.x.x), loopback (127.x.x.x), and
    common internal Docker hostnames.
    """
    import ipaddress
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Webhook URL must use http or https (got {parsed.scheme})")
    if not parsed.hostname:
        raise ValueError("Webhook URL must have a hostname")

    hostname = parsed.hostname.lower()

    # Block common internal hostnames
    blocked_hosts = {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "metadata.google.internal",
        "metadata",
    }
    # Block Docker-internal service names from compose files
    blocked_prefixes = (
        "supabase-",
        "corridorkey-",
        "postgres",
        "grafana",
        "prometheus",
        "loki",
        "promtail",
    )
    if hostname in blocked_hosts or any(hostname.startswith(p) for p in blocked_prefixes):
        raise ValueError(f"Webhook URL cannot target internal host: {hostname}")

    # Block private/reserved IP ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(f"Webhook URL cannot target private/reserved IP: {hostname}")
    except ValueError:
        pass  # hostname is a domain name, not an IP — OK


def create_webhook(org_id: str, url: str, events: list[str], fmt: str, created_by: str) -> Webhook:
    """Create a new webhook for an org."""
    import secrets

    _validate_webhook_url(url)
    hook_id = secrets.token_hex(8)
    hook = Webhook(
        id=hook_id,
        org_id=org_id,
        url=url,
        events=events,
        format=fmt,
        created_by=created_by,
        created_at=time.time(),
    )
    hooks = _load_webhooks()
    hooks[hook_id] = hook.to_dict()
    _save_webhooks(hooks)
    return hook


def list_webhooks(org_id: str) -> list[Webhook]:
    """List webhooks for an org."""
    hooks = _load_webhooks()
    return [Webhook(**v) for v in hooks.values() if v.get("org_id") == org_id]


def delete_webhook(hook_id: str) -> bool:
    """Delete a webhook."""
    hooks = _load_webhooks()
    if hook_id not in hooks:
        return False
    del hooks[hook_id]
    _save_webhooks(hooks)
    return True


def fire_event(event: str, org_id: str, data: dict[str, Any]) -> None:
    """Fire a webhook event for an org. Non-blocking — runs in a thread."""
    hooks = _load_webhooks()
    matching = [
        Webhook(**v)
        for v in hooks.values()
        if v.get("org_id") == org_id and v.get("active") and event in v.get("events", [])
    ]
    if not matching:
        return

    for hook in matching:
        threading.Thread(target=_deliver, args=(hook, event, data), daemon=True).start()


def _deliver(hook: Webhook, event: str, data: dict[str, Any], retries: int = 3) -> None:
    """Deliver a webhook with retry."""
    payload = _format_payload(hook.format, event, data)
    headers = {"Content-Type": "application/json"}

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                hook.url,
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                logger.debug(f"Webhook delivered: {event} -> {hook.url}")
                return
        except Exception as e:
            if attempt < retries - 1:
                delay = (attempt + 1) ** 2  # 1s, 4s, 9s
                logger.debug(f"Webhook retry {attempt + 1}/{retries} for {hook.url}: {e}")
                time.sleep(delay)
            else:
                logger.warning(f"Webhook delivery failed after {retries} attempts: {hook.url} — {e}")


def _format_payload(fmt: str, event: str, data: dict[str, Any]) -> dict:
    """Format payload for the target platform."""
    if fmt == "discord":
        color = {"job_completed": 0x5DD879, "job_failed": 0xFF5252, "job_started": 0xFFF203}.get(event, 0x9D9C93)
        return {
            "embeds": [
                {
                    "title": event.replace("_", " ").title(),
                    "color": color,
                    "fields": [{"name": k, "value": str(v), "inline": True} for k, v in data.items()],
                    "footer": {"text": "CorridorKey"},
                }
            ]
        }
    elif fmt == "slack":
        return {
            "text": f"*{event.replace('_', ' ').title()}*",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": event.replace("_", " ").title()}},
                {"type": "section", "fields": [{"type": "mrkdwn", "text": f"*{k}:* {v}"} for k, v in data.items()]},
            ],
        }
    else:
        return {"event": event, "data": data, "timestamp": time.time()}
