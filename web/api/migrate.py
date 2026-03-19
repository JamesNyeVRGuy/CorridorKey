"""Database migration runner (CRKY-49).

Runs Alembic migrations against the ck schema. Can be called:
- From app startup (auto_migrate=True)
- From CLI: CK_DATABASE_URL=... uv run python -m web.api.migrate
- From Alembic directly: CK_DATABASE_URL=... uv run alembic upgrade head
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def run_migrations() -> bool:
    """Run pending Alembic migrations. Returns True if successful."""
    database_url = os.environ.get("CK_DATABASE_URL", "")
    if not database_url:
        logger.debug("No CK_DATABASE_URL — skipping migrations")
        return False

    try:
        from alembic import command
        from alembic.config import Config

        # Find alembic.ini relative to the project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ini_path = os.path.join(project_root, "alembic.ini")

        if not os.path.isfile(ini_path):
            logger.warning(f"alembic.ini not found at {ini_path}")
            return False

        config = Config(ini_path)
        command.upgrade(config, "head")
        logger.info("Database migrations completed successfully")
        return True
    except ImportError:
        logger.debug("alembic not installed — skipping migrations")
        return False
    except Exception as e:
        logger.warning(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migrations()
    raise SystemExit(0 if success else 1)
