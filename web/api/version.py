"""Server version information.

BUILD_COMMIT is set at Docker build time via a build arg, or detected
from git at runtime for development. Falls back to "dev" if neither
is available.

BUILD_NUMBER is a Unix timestamp set at build time. Used for version
ordering — higher number = newer build. Commit hashes can't be ordered
without git history, but timestamps always can.
"""

from __future__ import annotations

import os
import subprocess

API_VERSION = "1.0.0"

# Build-time commit hash (set via Docker build arg or env var)
BUILD_COMMIT = os.environ.get("CK_BUILD_COMMIT", "").strip()

# Build number — Unix timestamp, set at Docker build time
# Used for version comparison (higher = newer)
BUILD_NUMBER = int(os.environ.get("CK_BUILD_NUMBER", "0").strip() or "0")

if not BUILD_COMMIT:
    # Try to detect from git at runtime (dev mode)
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_repo_root,
        )
        if result.returncode == 0:
            BUILD_COMMIT = result.stdout.strip()
    except Exception:
        pass

    # In dev mode, use the git commit timestamp as build number
    if not BUILD_NUMBER:
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ct"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=_repo_root,
            )
            if result.returncode == 0:
                BUILD_NUMBER = int(result.stdout.strip())
        except Exception:
            pass

BUILD_COMMIT = BUILD_COMMIT or "dev"

VERSION_STRING = f"{API_VERSION}+{BUILD_COMMIT}"

# Minimum node build number required to accept jobs.
# Set this to the BUILD_NUMBER of the oldest acceptable node image.
# Nodes older than this are flagged as outdated and blocked from job dispatch.
# Update this when a node-side fix is critical (e.g., file transfer changes).
# 0 = no minimum enforced.
MIN_NODE_BUILD = int(os.environ.get("CK_MIN_NODE_BUILD", str(BUILD_NUMBER)).strip() or "0")
