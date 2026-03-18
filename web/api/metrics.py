"""Prometheus metrics endpoint for monitoring.

Exports CorridorKey-specific metrics in Prometheus text format at /metrics.
Enabled via CK_METRICS_ENABLED=true (default false).

No external dependencies — builds the text format manually.
"""

from __future__ import annotations

import os
import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from .deps import get_queue
from .nodes import registry
from .ws import manager

METRICS_ENABLED = os.environ.get("CK_METRICS_ENABLED", "false").lower() in ("true", "1", "yes")

router = APIRouter(tags=["metrics"])

_start_time = time.time()


def _metric(name: str, value: float | int, help_text: str, metric_type: str = "gauge", labels: str = "") -> str:
    """Format a single Prometheus metric."""
    label_str = f"{{{labels}}}" if labels else ""
    return f"# HELP {name} {help_text}\n# TYPE {name} {metric_type}\n{name}{label_str} {value}\n"


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    """Export metrics in Prometheus text exposition format."""
    if not METRICS_ENABLED:
        return PlainTextResponse("# Metrics disabled. Set CK_METRICS_ENABLED=true\n", status_code=200)

    lines: list[str] = []

    # Uptime
    uptime = time.time() - _start_time
    lines.append(_metric("corridorkey_uptime_seconds", uptime, "Server uptime in seconds", "counter"))

    # Job queue
    queue = get_queue()
    running = queue.running_jobs
    queued = queue.queue_snapshot
    history = queue.history_snapshot

    completed = sum(1 for j in history if j.status.value == "completed")
    failed = sum(1 for j in history if j.status.value == "failed")
    cancelled = sum(1 for j in history if j.status.value == "cancelled")

    lines.append(_metric("corridorkey_jobs_running", len(running), "Running jobs"))
    lines.append(_metric("corridorkey_jobs_queued", len(queued), "Queued jobs"))
    lines.append(_metric("corridorkey_jobs_completed_total", completed, "Total completed", "counter"))
    lines.append(_metric("corridorkey_jobs_failed_total", failed, "Total failed", "counter"))
    lines.append(_metric("corridorkey_jobs_cancelled_total", cancelled, "Total cancelled", "counter"))

    # Nodes
    nodes = registry.list_nodes()
    online = sum(1 for n in nodes if n.is_alive and n.status == "online")
    busy = sum(1 for n in nodes if n.is_alive and n.status == "busy")
    offline = sum(1 for n in nodes if not n.is_alive)

    lines.append(_metric("corridorkey_nodes_online", online, "Online nodes"))
    lines.append(_metric("corridorkey_nodes_busy", busy, "Busy nodes"))
    lines.append(_metric("corridorkey_nodes_offline", offline, "Offline nodes"))
    lines.append(_metric("corridorkey_nodes_total", len(nodes), "Total nodes"))

    # WebSocket connections
    ws_count = len(manager._connections)
    lines.append(_metric("corridorkey_ws_connections", ws_count, "WebSocket connections"))

    # Per-node GPU metrics
    for node in nodes:
        if node.cpu_stats:
            labels = f'node="{node.name}"'
            cpu = node.cpu_stats.get("cpu_percent", 0)
            ram_used = node.cpu_stats.get("ram_used_gb", 0)
            ram_total = node.cpu_stats.get("ram_total_gb", 0)
            lines.append(f"corridorkey_node_cpu_percent{{{labels}}} {cpu}\n")
            lines.append(f"corridorkey_node_ram_used_gb{{{labels}}} {ram_used}\n")
            lines.append(f"corridorkey_node_ram_total_gb{{{labels}}} {ram_total}\n")

    return PlainTextResponse("".join(lines))
