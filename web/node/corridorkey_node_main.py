"""PyInstaller entry point for the CorridorKey node agent.

This wrapper launches web.node as a package (python -m web.node),
avoiding the relative import issue in frozen executables.
"""

import multiprocessing
import runpy
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Run as if `python -m web.node` was called
    sys.argv[0] = "web.node"
    runpy.run_module("web.node", run_name="__main__", alter_sys=True)

