"""Subprocess utilities that suppress console window flash on Windows.

In PyInstaller windowed builds (console=False), every subprocess.run() or
Popen() call to a console program (nvidia-smi, pip, ffmpeg, etc.) will
flash a console window. These wrappers add CREATE_NO_WINDOW on Windows.

Use run_silent() and popen_silent() everywhere instead of subprocess.run()
and subprocess.Popen() directly.
"""

from __future__ import annotations

import subprocess
import sys

# Windows-only: suppress console window for child processes
_NO_CONSOLE: dict = {}
if sys.platform == "win32":
    _NO_CONSOLE["creationflags"] = subprocess.CREATE_NO_WINDOW


def run_silent(*args, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run() that never flashes a console window."""
    merged = {**_NO_CONSOLE, **kwargs}
    return subprocess.run(*args, **merged)


def popen_silent(*args, **kwargs) -> subprocess.Popen:
    """subprocess.Popen() that never flashes a console window."""
    merged = {**_NO_CONSOLE, **kwargs}
    return subprocess.Popen(*args, **merged)
