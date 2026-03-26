"""GPU credit tracking — contributed vs consumed per org (CRKY-6).

Tracks GPU-seconds contributed by nodes and consumed by jobs per org.
Used by the credit enforcement system (CRKY-37) to ensure fair
resource sharing.

Credits are stored in ck.gpu_credits (org_id keyed). When Postgres is
not available, falls back to the JSON storage backend.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Starter credits granted to new orgs on user approval (GPU-seconds).
# Default 3600 = 1 hour. Set to 0 to disable.
STARTER_CREDITS = float(os.environ.get("CK_STARTER_CREDITS", "3600").strip())


@dataclass
class OrgCredits:
    """Credit balance for an org."""

    org_id: str
    contributed_seconds: float = 0.0
    consumed_seconds: float = 0.0

    @property
    def balance(self) -> float:
        """Net balance: contributed - consumed. Positive = surplus."""
        return self.contributed_seconds - self.consumed_seconds

    @property
    def ratio(self) -> float:
        """Consumption ratio: consumed / contributed. <1.0 = surplus."""
        if self.contributed_seconds <= 0:
            return float("inf") if self.consumed_seconds > 0 else 0.0
        return self.consumed_seconds / self.contributed_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "contributed_seconds": round(self.contributed_seconds, 1),
            "consumed_seconds": round(self.consumed_seconds, 1),
            "balance_seconds": round(self.balance, 1),
            "contributed_hours": round(self.contributed_seconds / 3600, 2),
            "consumed_hours": round(self.consumed_seconds / 3600, 2),
            "ratio": round(self.ratio, 3) if self.ratio != float("inf") else None,
        }


def get_org_credits(org_id: str) -> OrgCredits:
    """Get the credit balance for an org."""
    from .database import get_pg_conn

    with get_pg_conn() as conn:
        if conn is not None:
            cur = conn.cursor()
            cur.execute(
                "SELECT contributed_seconds, consumed_seconds FROM ck.gpu_credits WHERE org_id = %s",
                (org_id,),
            )
            row = cur.fetchone()
            cur.close()
            if row:
                return OrgCredits(org_id=org_id, contributed_seconds=row[0], consumed_seconds=row[1])

    # Fallback: JSON storage
    from .database import get_storage

    storage = get_storage()
    credits = storage.get_setting("gpu_credits", {})
    data = credits.get(org_id, {})
    return OrgCredits(
        org_id=org_id,
        contributed_seconds=data.get("contributed_seconds", 0.0),
        consumed_seconds=data.get("consumed_seconds", 0.0),
    )


def add_contributed(org_id: str, seconds: float) -> None:
    """Add contributed GPU-seconds for an org (from node processing)."""
    if seconds <= 0 or not org_id:
        return

    from .database import get_pg_conn

    with get_pg_conn() as conn:
        if conn is not None:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ck.gpu_credits (org_id, contributed_seconds, updated_at)
                   VALUES (%s, %s, NOW())
                   ON CONFLICT (org_id) DO UPDATE
                   SET contributed_seconds = ck.gpu_credits.contributed_seconds + %s,
                       updated_at = NOW()""",
                (org_id, seconds, seconds),
            )
            cur.close()
            return

    # Fallback: JSON storage
    from .database import get_storage

    storage = get_storage()
    credits = storage.get_setting("gpu_credits", {})
    if org_id not in credits:
        credits[org_id] = {"contributed_seconds": 0.0, "consumed_seconds": 0.0}
    credits[org_id]["contributed_seconds"] += seconds
    storage.set_setting("gpu_credits", credits)


def add_consumed(org_id: str, seconds: float) -> None:
    """Add consumed GPU-seconds for an org (from job completion)."""
    if seconds <= 0 or not org_id:
        return

    from .database import get_pg_conn

    with get_pg_conn() as conn:
        if conn is not None:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ck.gpu_credits (org_id, consumed_seconds, updated_at)
                   VALUES (%s, %s, NOW())
                   ON CONFLICT (org_id) DO UPDATE
                   SET consumed_seconds = ck.gpu_credits.consumed_seconds + %s,
                       updated_at = NOW()""",
                (org_id, seconds, seconds),
            )
            cur.close()
            return

    # Fallback: JSON storage
    from .database import get_storage

    storage = get_storage()
    credits = storage.get_setting("gpu_credits", {})
    if org_id not in credits:
        credits[org_id] = {"contributed_seconds": 0.0, "consumed_seconds": 0.0}
    credits[org_id]["consumed_seconds"] += seconds
    storage.set_setting("gpu_credits", credits)


def get_all_credits() -> list[OrgCredits]:
    """Get credits for all orgs (admin view)."""
    from .database import get_pg_conn

    with get_pg_conn() as conn:
        if conn is not None:
            cur = conn.cursor()
            cur.execute("SELECT org_id, contributed_seconds, consumed_seconds FROM ck.gpu_credits")
            result = [
                OrgCredits(org_id=row[0], contributed_seconds=row[1], consumed_seconds=row[2]) for row in cur.fetchall()
            ]
            cur.close()
            return result

    # Fallback: JSON storage
    from .database import get_storage

    storage = get_storage()
    credits = storage.get_setting("gpu_credits", {})
    return [
        OrgCredits(
            org_id=oid,
            contributed_seconds=data.get("contributed_seconds", 0.0),
            consumed_seconds=data.get("consumed_seconds", 0.0),
        )
        for oid, data in credits.items()
    ]
