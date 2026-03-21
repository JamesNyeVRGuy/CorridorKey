"""Server version information.

BUILD_COMMIT is set at Docker build time via a build arg, or detected
from git at runtime for development. Falls back to "dev" if neither
is available.
"""

from __future__ import annotations

import os
import subprocess

API_VERSION = "1.0.0"

# Build-time commit hash (set via Docker build arg or env var)
BUILD_COMMIT = os.environ.get("CK_BUILD_COMMIT", "").strip()

if not BUILD_COMMIT:
    # Try to detect from git at runtime (dev mode)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        if result.returncode == 0:
            BUILD_COMMIT = result.stdout.strip()
    except Exception:
        pass

BUILD_COMMIT = BUILD_COMMIT or "dev"

VERSION_STRING = f"{API_VERSION}+{BUILD_COMMIT}"
