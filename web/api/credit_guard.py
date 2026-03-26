"""GPU credit enforcement — blocks job submission if over ratio (CRKY-37).

Checks the requesting user's org credit balance before allowing job
submission. Projects the estimated cost of the new job into the ratio
calculation — if the job would push the org over the limit, it's rejected.

Settings:
- CK_CREDIT_RATIO: max consumed/contributed ratio (default 2.0).
  Set to 0 to disable enforcement.
  Example: 2.0 means an org can consume 2x what they've contributed.
- CK_CREDIT_GRACE: free GPU-seconds before enforcement kicks in
  (default 3600 = 1 hour). Allows new orgs to submit jobs before
  they've set up nodes.
"""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Request

from .auth import AUTH_ENABLED, get_current_user
from .gpu_credits import get_org_credits
from .orgs import get_org_store

logger = logging.getLogger(__name__)

# Configurable ratio: 0 = disabled, 2.0 = can consume 2x contributed
CREDIT_RATIO = float(os.environ.get("CK_CREDIT_RATIO", "2.0").strip())
# Grace period: free GPU-seconds before enforcement (default 1 hour)
CREDIT_GRACE = float(os.environ.get("CK_CREDIT_GRACE", "3600").strip())

# Default seconds-per-frame estimates when no history is available
_DEFAULT_SPF = {
    "inference": 1.5,
    "gvm_alpha": 2.5,
    "videomama_alpha": 1.5,
    "video_extract": 0.05,
    "video_stitch": 0.02,
}


def estimate_gpu_seconds(job_type: str, frame_count: int) -> float:
    """Estimate GPU-seconds for a job based on historical data.

    Uses median seconds-per-frame from completed jobs of the same type.
    Falls back to default estimates when no history is available.
    """
    from .deps import get_queue

    queue = get_queue()
    history = queue.history_snapshot

    completed = [
        j
        for j in history
        if j.status.value == "completed"
        and j.job_type.value == job_type
        and j.total_frames > 0
        and j.started_at > 0
        and j.completed_at > j.started_at
    ]

    if completed:
        spf_values = []
        for j in completed:
            duration = j.completed_at - j.started_at
            spf = duration / j.total_frames
            if spf < 60:
                spf_values.append(spf)
        if spf_values:
            spf_values.sort()
            return spf_values[len(spf_values) // 2] * frame_count

    return _DEFAULT_SPF.get(job_type, 1.0) * frame_count


def check_credit_balance(request: Request, estimated_seconds: float = 0) -> None:
    """Check if the user's org has sufficient GPU credits.

    Projects the estimated cost of the new job into the ratio calculation.
    If submitting this job would push the org over the ratio limit, it's
    rejected before the job even starts.

    Raises HTTP 402 (Payment Required) if the org would exceed their
    earn-to-use ratio. No-op when:
    - Auth is disabled
    - Credit enforcement is disabled (CK_CREDIT_RATIO=0)
    - User is platform_admin
    - Org hasn't exhausted the grace period
    """
    if not AUTH_ENABLED or CREDIT_RATIO <= 0:
        return

    user = get_current_user(request)
    if not user:
        return
    if user.is_admin:
        return

    # Use active org from header, fall back to first org
    active_org = request.headers.get("X-Org-Id", "").strip()
    org_store = get_org_store()
    if active_org and (user.is_admin or org_store.is_member(active_org, user.user_id)):
        org_id = active_org
    else:
        user_orgs = org_store.list_user_orgs(user.user_id)
        if not user_orgs:
            return
        org_id = user_orgs[0].org_id

    credits = get_org_credits(org_id)

    # Project the estimated cost into the balance
    projected_consumed = credits.consumed_seconds + estimated_seconds

    # Grace period: allow free usage up to CREDIT_GRACE seconds
    if projected_consumed <= CREDIT_GRACE:
        return

    # If org has never contributed, block after grace
    if credits.contributed_seconds <= 0:
        raise HTTPException(
            status_code=402,
            detail=f"Your organization has used {credits.consumed_seconds / 3600:.1f} GPU-hours "
            f"but hasn't contributed any compute. Add a node to earn credits.",
        )

    # Check projected ratio
    projected_ratio = projected_consumed / credits.contributed_seconds
    if projected_ratio > CREDIT_RATIO:
        remaining = (credits.contributed_seconds * CREDIT_RATIO) - credits.consumed_seconds
        remaining_min = max(0, remaining / 60)
        raise HTTPException(
            status_code=402,
            detail=f"This job would exceed your GPU credit limit. "
            f"Remaining budget: ~{remaining_min:.0f} GPU-minutes "
            f"(consumed {credits.consumed_seconds / 3600:.1f}h of "
            f"{credits.contributed_seconds * CREDIT_RATIO / 3600:.1f}h allowed). "
            f"Add more nodes to earn credits.",
        )


def check_credit_balance_by_org(org_id: str, estimated_seconds: float = 0) -> None:
    """Check credits for a specific org (used by pipeline chaining, no Request needed).

    Raises ValueError if over budget. No-op when enforcement is disabled.
    """
    if CREDIT_RATIO <= 0:
        return

    credits = get_org_credits(org_id)
    projected_consumed = credits.consumed_seconds + estimated_seconds

    if projected_consumed <= CREDIT_GRACE:
        return

    if credits.contributed_seconds <= 0:
        raise ValueError(f"Org {org_id} has no contributed GPU time")

    projected_ratio = projected_consumed / credits.contributed_seconds
    if projected_ratio > CREDIT_RATIO:
        raise ValueError(f"Org {org_id} would exceed credit ratio ({projected_ratio:.1f}x > {CREDIT_RATIO:.1f}x)")
