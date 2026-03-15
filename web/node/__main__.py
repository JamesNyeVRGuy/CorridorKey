"""Entry point for the CorridorKey node agent.

Usage:
    CK_MAIN_URL=http://192.168.1.100:3000 python -m web.node
    CK_MAIN_URL=http://192.168.1.100:3000 uv run python -m web.node
"""

from __future__ import annotations

import logging
import signal
import sys

from . import config
from .agent import NodeAgent


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if config.MAIN_URL == "http://localhost:3000":
        logging.getLogger(__name__).warning(
            "CK_MAIN_URL not set — defaulting to http://localhost:3000. Set CK_MAIN_URL to the main machine's address."
        )

    agent = NodeAgent()

    def shutdown(signum, frame):
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    agent.run()


if __name__ == "__main__":
    main()
