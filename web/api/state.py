"""State backend abstraction for multi-instance deployment (CRKY-105).

Defines protocols for node registry and job queue state, allowing
swappable backends: InMemory (single instance) or Redis (Phase 2,
multi-instance behind a load balancer).

Backend selection:
    - No CK_REDIS_URL env var → InMemoryState (current behavior, zero config)
    - CK_REDIS_URL set → RedisState (Phase 2)
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from backend.job_queue import GPUJob, GPUJobQueue

from .nodes import NodeInfo, NodeRegistry

# ---------------------------------------------------------------------------
# Callback type aliases (mirrors backend.job_queue)
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[str, int, int], None]
WarningCallback = Callable[[str], None]
CompletionCallback = Callable[[str], None]
ErrorCallback = Callable[[str, str], None]


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class NodeState(Protocol):
    """Protocol for node registry operations."""

    def register(self, info: NodeInfo) -> None: ...
    def heartbeat(self, node_id: str, vram_free_gb: float = 0.0, status: str = "online") -> bool: ...
    def unregister(self, node_id: str, dismiss: bool = False) -> None: ...
    def update_node(self, node_id: str, info: NodeInfo) -> None: ...
    def set_busy(self, node_id: str, job_id: str) -> None: ...
    def set_idle(self, node_id: str) -> None: ...
    def get_node(self, node_id: str) -> NodeInfo | None: ...
    def list_nodes(self) -> list[NodeInfo]: ...
    def get_available_node(self, min_vram_gb: float = 0.0) -> NodeInfo | None: ...
    def is_dismissed(self, node_id: str) -> bool: ...

    @property
    def online_count(self) -> int: ...


@runtime_checkable
class JobState(Protocol):
    """Protocol for job queue operations."""

    # --- Callbacks (set by app.py lifespan) ---
    on_progress: ProgressCallback | None
    on_warning: WarningCallback | None
    on_completion: CompletionCallback | None
    on_error: ErrorCallback | None

    # --- Core operations ---
    def submit(self, job: GPUJob) -> bool: ...
    def next_job(self) -> GPUJob | None: ...
    def claim_job(
        self,
        claimer_id: str = "local",
        accepted_types: list[str] | None = None,
        org_id: str | None = None,
    ) -> GPUJob | None: ...
    def start_job(self, job: GPUJob) -> None: ...
    def complete_job(self, job: GPUJob) -> None: ...
    def fail_job(self, job: GPUJob, error: str) -> None: ...
    def move_job(self, job_id: str, position: int) -> bool: ...
    def requeue_job(self, job: GPUJob) -> None: ...
    def mark_cancelled(self, job: GPUJob) -> None: ...
    def cancel_job(self, job: GPUJob) -> None: ...
    def cancel_current(self) -> None: ...
    def cancel_all(self) -> None: ...
    def report_progress(self, clip_name: str, current: int, total: int) -> None: ...
    def report_warning(self, message: str) -> None: ...
    def find_job_by_id(self, job_id: str) -> GPUJob | None: ...

    # --- Shard operations ---
    def shard_group_progress(self, shard_group: str) -> dict[str, Any]: ...
    def shard_group_all_done(self, shard_group: str) -> bool: ...
    def cancel_shard_group(self, shard_group: str) -> int: ...
    def retry_failed_shards(self, shard_group: str) -> list[GPUJob]: ...

    # --- History ---
    def restore_history(self, jobs: list[GPUJob]) -> None: ...
    def clear_history(self) -> None: ...
    def remove_job(self, job_id: str) -> None: ...

    # --- Read-only properties ---
    @property
    def has_pending(self) -> bool: ...
    @property
    def current_job(self) -> GPUJob | None: ...
    @property
    def running_jobs(self) -> list[GPUJob]: ...
    @property
    def pending_count(self) -> int: ...
    @property
    def queue_snapshot(self) -> list[GPUJob]: ...
    @property
    def history_snapshot(self) -> list[GPUJob]: ...
    @property
    def all_jobs_snapshot(self) -> list[GPUJob]: ...


# ---------------------------------------------------------------------------
# In-memory implementations (wrapping existing classes)
# ---------------------------------------------------------------------------


class InMemoryNodeState:
    """In-memory node state backed by NodeRegistry."""

    def __init__(self) -> None:
        self._registry = NodeRegistry()

    @property
    def _inner(self) -> NodeRegistry:
        """Access the underlying NodeRegistry (for migration-period internals)."""
        return self._registry

    def register(self, info: NodeInfo) -> None:
        self._registry.register(info)

    def heartbeat(self, node_id: str, vram_free_gb: float = 0.0, status: str = "online") -> bool:
        return self._registry.heartbeat(node_id, vram_free_gb, status)

    def unregister(self, node_id: str, dismiss: bool = False) -> None:
        self._registry.unregister(node_id, dismiss)

    def update_node(self, node_id: str, info: NodeInfo) -> None:
        pass  # in-memory: mutations on the returned reference already persist

    def set_busy(self, node_id: str, job_id: str) -> None:
        self._registry.set_busy(node_id, job_id)

    def set_idle(self, node_id: str) -> None:
        self._registry.set_idle(node_id)

    def get_node(self, node_id: str) -> NodeInfo | None:
        return self._registry.get_node(node_id)

    def list_nodes(self) -> list[NodeInfo]:
        return self._registry.list_nodes()

    def get_available_node(self, min_vram_gb: float = 0.0) -> NodeInfo | None:
        return self._registry.get_available_node(min_vram_gb)

    def is_dismissed(self, node_id: str) -> bool:
        return self._registry.is_dismissed(node_id)

    @property
    def online_count(self) -> int:
        return self._registry.online_count


class InMemoryJobState:
    """In-memory job state backed by GPUJobQueue."""

    def __init__(self) -> None:
        self._queue = GPUJobQueue()

    @property
    def _inner(self) -> GPUJobQueue:
        """Access the underlying GPUJobQueue (for migration-period internals)."""
        return self._queue

    # --- Callback delegation ---

    @property
    def on_progress(self) -> ProgressCallback | None:
        return self._queue.on_progress

    @on_progress.setter
    def on_progress(self, cb: ProgressCallback | None) -> None:
        self._queue.on_progress = cb

    @property
    def on_warning(self) -> WarningCallback | None:
        return self._queue.on_warning

    @on_warning.setter
    def on_warning(self, cb: WarningCallback | None) -> None:
        self._queue.on_warning = cb

    @property
    def on_completion(self) -> CompletionCallback | None:
        return self._queue.on_completion

    @on_completion.setter
    def on_completion(self, cb: CompletionCallback | None) -> None:
        self._queue.on_completion = cb

    @property
    def on_error(self) -> ErrorCallback | None:
        return self._queue.on_error

    @on_error.setter
    def on_error(self, cb: ErrorCallback | None) -> None:
        self._queue.on_error = cb

    # --- Core operations ---

    def submit(self, job: GPUJob) -> bool:
        return self._queue.submit(job)

    def next_job(self) -> GPUJob | None:
        return self._queue.next_job()

    def claim_job(
        self,
        claimer_id: str = "local",
        accepted_types: list[str] | None = None,
        org_id: str | None = None,
    ) -> GPUJob | None:
        return self._queue.claim_job(claimer_id, accepted_types, org_id)

    def start_job(self, job: GPUJob) -> None:
        self._queue.start_job(job)

    def complete_job(self, job: GPUJob) -> None:
        self._queue.complete_job(job)

    def fail_job(self, job: GPUJob, error: str) -> None:
        self._queue.fail_job(job, error)

    def move_job(self, job_id: str, position: int) -> bool:
        return self._queue.move_job(job_id, position)

    def requeue_job(self, job: GPUJob) -> None:
        self._queue.requeue_job(job)

    def mark_cancelled(self, job: GPUJob) -> None:
        self._queue.mark_cancelled(job)

    def cancel_job(self, job: GPUJob) -> None:
        self._queue.cancel_job(job)

    def cancel_current(self) -> None:
        self._queue.cancel_current()

    def cancel_all(self) -> None:
        self._queue.cancel_all()

    def report_progress(self, clip_name: str, current: int, total: int) -> None:
        self._queue.report_progress(clip_name, current, total)

    def report_warning(self, message: str) -> None:
        self._queue.report_warning(message)

    def find_job_by_id(self, job_id: str) -> GPUJob | None:
        return self._queue.find_job_by_id(job_id)

    # --- Shard operations ---

    def shard_group_progress(self, shard_group: str) -> dict[str, Any]:
        return self._queue.shard_group_progress(shard_group)

    def shard_group_all_done(self, shard_group: str) -> bool:
        return self._queue.shard_group_all_done(shard_group)

    def cancel_shard_group(self, shard_group: str) -> int:
        return self._queue.cancel_shard_group(shard_group)

    def retry_failed_shards(self, shard_group: str) -> list[GPUJob]:
        return self._queue.retry_failed_shards(shard_group)

    # --- History ---

    def restore_history(self, jobs: list[GPUJob]) -> None:
        self._queue._history.extend(jobs)

    def clear_history(self) -> None:
        self._queue.clear_history()

    def remove_job(self, job_id: str) -> None:
        self._queue.remove_job(job_id)

    # --- Read-only properties ---

    @property
    def has_pending(self) -> bool:
        return self._queue.has_pending

    @property
    def current_job(self) -> GPUJob | None:
        return self._queue.current_job

    @property
    def running_jobs(self) -> list[GPUJob]:
        return self._queue.running_jobs

    @property
    def pending_count(self) -> int:
        return self._queue.pending_count

    @property
    def queue_snapshot(self) -> list[GPUJob]:
        return self._queue.queue_snapshot

    @property
    def history_snapshot(self) -> list[GPUJob]:
        return self._queue.history_snapshot

    @property
    def all_jobs_snapshot(self) -> list[GPUJob]:
        return self._queue.all_jobs_snapshot


# ---------------------------------------------------------------------------
# Composed backend
# ---------------------------------------------------------------------------


class StateBackend:
    """Composed state backend holding both node and job state."""

    def __init__(self, nodes: NodeState, jobs: JobState) -> None:
        self.nodes = nodes
        self.jobs = jobs


def create_in_memory_backend() -> StateBackend:
    """Create an in-memory state backend (single-instance deployment)."""
    return StateBackend(
        nodes=InMemoryNodeState(),
        jobs=InMemoryJobState(),
    )


def create_backend() -> StateBackend:
    """Create the appropriate state backend based on CK_REDIS_URL.

    If CK_REDIS_URL is set, uses Redis (multi-instance). Otherwise
    falls back to in-memory (single-instance, zero config).
    """
    from .redis_client import is_redis_configured

    if is_redis_configured():
        from .redis_state import RedisJobState, RedisNodeState

        return StateBackend(nodes=RedisNodeState(), jobs=RedisJobState())
    return create_in_memory_backend()
