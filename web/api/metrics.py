"""Prometheus metrics endpoint for monitoring (CRKY-27).

Exports CorridorKey-specific metrics in Prometheus text format at /metrics.
Enabled via CK_METRICS_ENABLED=true (default false).

Metrics exported:
- corridorkey_uptime_seconds (counter)
- corridorkey_jobs_{running,queued,completed_total,failed_total,cancelled_total}
- corridorkey_nodes_{online,busy,offline,total}
- corridorkey_ws_connections
- corridorkey_node_cpu_percent{node="..."} (per-node)
- corridorkey_node_ram_{used,total}_gb{node="..."} (per-node)
- corridorkey_node_vram_{used,total}_gb{node="...",gpu="..."} (per-GPU)
- corridorkey_node_job_success_rate{node="..."} (per-node)
- corridorkey_gpu_credits_{contributed,consumed}_seconds{org="..."} (per-org)
- corridorkey_storage_used_bytes{org="..."} (per-org)
- corridorkey_api_requests_total (counter)
- corridorkey_disk_free_gb

No external dependencies — builds the text format manually.
"""

from __future__ import annotations

import os
import shutil
import time

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from .deps import get_queue
from .nodes import registry
from .ws import manager

METRICS_ENABLED = os.environ.get("CK_METRICS_ENABLED", "false").strip().lower() in ("true", "1", "yes")

router = APIRouter(tags=["metrics"])

_start_time = time.time()

# Simple request counter incremented by middleware
_request_count = 0


def increment_request_count() -> None:
    """Called by middleware to count API requests."""
    global _request_count
    _request_count += 1


def _metric(name: str, value: float | int, help_text: str, metric_type: str = "gauge", labels: str = "") -> str:
    """Format a single Prometheus metric."""
    label_str = f"{{{labels}}}" if labels else ""
    return f"# HELP {name} {help_text}\n# TYPE {name} {metric_type}\n{name}{label_str} {value}\n"


def _labeled_metric(name: str, value: float | int, labels: str) -> str:
    """Format a metric line with labels (no HELP/TYPE header — share with first)."""
    return f"{name}{{{labels}}} {value}\n"


# Optional bearer token for metrics endpoint security.
# Set CK_METRICS_TOKEN to require authentication on /metrics.
# Prometheus scrape config: authorization: {type: Bearer, credentials: <token>}
_METRICS_TOKEN = os.environ.get("CK_METRICS_TOKEN", "").strip()


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics(request: Request):
    """Export metrics in Prometheus text exposition format."""
    if not METRICS_ENABLED:
        return PlainTextResponse("# Metrics disabled. Set CK_METRICS_ENABLED=true\n", status_code=200)

    # Token auth for metrics (optional — set CK_METRICS_TOKEN to enable)
    if _METRICS_TOKEN:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {_METRICS_TOKEN}":
            return PlainTextResponse("Unauthorized\n", status_code=401)

    lines: list[str] = []

    # Uptime
    uptime = time.time() - _start_time
    lines.append(_metric("corridorkey_uptime_seconds", uptime, "Server uptime in seconds", "counter"))

    # Request counter
    lines.append(_metric("corridorkey_api_requests_total", _request_count, "Total API requests", "counter"))

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

    # Job throughput — completed in last hour
    cutoff_1h = time.time() - 3600
    recent_completed = sum(
        1 for j in history if j.status.value == "completed" and j.completed_at and j.completed_at > cutoff_1h
    )
    lines.append(_metric("corridorkey_jobs_completed_last_hour", recent_completed, "Jobs completed in last hour"))

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

    # Per-node metrics (CPU, RAM, VRAM, GPU utilization, job success rate)
    lines.append("# HELP corridorkey_node_cpu_percent Node CPU usage percent\n")
    lines.append("# TYPE corridorkey_node_cpu_percent gauge\n")
    lines.append("# HELP corridorkey_node_ram_used_gb Node RAM used in GB\n")
    lines.append("# TYPE corridorkey_node_ram_used_gb gauge\n")
    lines.append("# HELP corridorkey_node_ram_total_gb Node RAM total in GB\n")
    lines.append("# TYPE corridorkey_node_ram_total_gb gauge\n")

    for node in nodes:
        labels = f'node="{node.name}"'
        if node.cpu_stats:
            cpu = node.cpu_stats.get("cpu_percent", 0)
            ram_used = node.cpu_stats.get("ram_used_gb", 0)
            ram_total = node.cpu_stats.get("ram_total_gb", 0)
            lines.append(_labeled_metric("corridorkey_node_cpu_percent", cpu, labels))
            lines.append(_labeled_metric("corridorkey_node_ram_used_gb", ram_used, labels))
            lines.append(_labeled_metric("corridorkey_node_ram_total_gb", ram_total, labels))

        # Per-GPU VRAM metrics
        if node.gpus:
            for gpu in node.gpus:
                gpu_labels = f'node="{node.name}",gpu="{gpu.name}",gpu_index="{gpu.index}"'
                lines.append(_labeled_metric("corridorkey_node_vram_total_gb", gpu.vram_total_gb, gpu_labels))
                vram_used = gpu.vram_total_gb - gpu.vram_free_gb
                lines.append(_labeled_metric("corridorkey_node_vram_used_gb", vram_used, gpu_labels))
        elif node.vram_total_gb > 0:
            gpu_labels = f'node="{node.name}",gpu="{node.gpu_name}",gpu_index="0"'
            lines.append(_labeled_metric("corridorkey_node_vram_total_gb", node.vram_total_gb, gpu_labels))
            lines.append(
                _labeled_metric("corridorkey_node_vram_used_gb", node.vram_total_gb - node.vram_free_gb, gpu_labels)
            )

    # Per-node job success rate (from reputation system)
    try:
        from .node_reputation import get_all_reputations

        reps = get_all_reputations()
        if reps:
            lines.append("# HELP corridorkey_node_success_rate Node job success rate 0-1\n")
            lines.append("# TYPE corridorkey_node_success_rate gauge\n")
            lines.append("# HELP corridorkey_node_reputation Node reputation score 0-100\n")
            lines.append("# TYPE corridorkey_node_reputation gauge\n")
            for rep in reps:
                node = registry.get_node(rep.node_id)
                name = node.name if node else rep.node_id
                labels = f'node="{name}"'
                rate = rep.success_rate if rep.total_jobs > 0 else 1.0
                lines.append(_labeled_metric("corridorkey_node_success_rate", round(rate, 3), labels))
                lines.append(_labeled_metric("corridorkey_node_reputation", rep.score, labels))
    except Exception:
        pass

    # Per-org GPU credits
    try:
        from .gpu_credits import get_all_credits
        from .orgs import get_org_store

        org_store = get_org_store()
        credits = get_all_credits()
        if credits:
            lines.append("# HELP corridorkey_gpu_credits_contributed_seconds GPU seconds contributed\n")
            lines.append("# TYPE corridorkey_gpu_credits_contributed_seconds counter\n")
            lines.append("# HELP corridorkey_gpu_credits_consumed_seconds GPU seconds consumed\n")
            lines.append("# TYPE corridorkey_gpu_credits_consumed_seconds counter\n")
            for c in credits:
                org = org_store.get_org(c.org_id)
                name = org.name if org else c.org_id[:8]
                labels = f'org="{name}",org_id="{c.org_id}"'
                lines.append(
                    _labeled_metric("corridorkey_gpu_credits_contributed_seconds", c.contributed_seconds, labels)
                )
                lines.append(_labeled_metric("corridorkey_gpu_credits_consumed_seconds", c.consumed_seconds, labels))
    except Exception:
        pass

    # Disk space
    try:
        from backend.project import projects_root

        clips_dir = os.environ.get("CK_CLIPS_DIR", "").strip() or projects_root()
        if os.path.isdir(clips_dir):
            usage = shutil.disk_usage(clips_dir)
            free_gb = round(usage.free / (1024**3), 2)
            total_gb = round(usage.total / (1024**3), 2)
            lines.append(_metric("corridorkey_disk_free_gb", free_gb, "Free disk space in GB"))
            lines.append(_metric("corridorkey_disk_total_gb", total_gb, "Total disk space in GB"))
    except Exception:
        pass

    return PlainTextResponse("".join(lines))
