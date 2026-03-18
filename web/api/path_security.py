"""Path security utilities (CRKY-56, CRKY-57).

Prevents path traversal, zip slip, and other filesystem attacks.
Use safe_join() anywhere a user-supplied filename is combined with
a trusted base directory.
"""

from __future__ import annotations

import os
import zipfile

from fastapi import HTTPException


def safe_join(base: str, *parts: str) -> str:
    """Join path components and verify the result stays within base.

    Raises HTTP 400 if the resolved path escapes the base directory.
    Handles .., encoded traversals, null bytes, and symlinks.
    """
    # Reject null bytes (can truncate paths in C-backed libs)
    for part in parts:
        if "\x00" in part:
            raise HTTPException(status_code=400, detail="Invalid filename: null byte")

    joined = os.path.join(base, *parts)
    resolved = os.path.realpath(joined)
    base_resolved = os.path.realpath(base)

    # Ensure resolved path is within base (with trailing sep to prevent prefix attacks)
    if not (resolved == base_resolved or resolved.startswith(base_resolved + os.sep)):
        raise HTTPException(status_code=400, detail="Invalid path: directory traversal detected")

    return resolved


def safe_extract_zip(zf: zipfile.ZipFile, target_dir: str) -> list[str]:
    """Extract a zip file safely, preventing zip slip.

    Validates each member's resolved path stays within target_dir.
    Returns the list of extracted file paths.
    """
    target_resolved = os.path.realpath(target_dir)
    extracted = []

    for member in zf.infolist():
        # Skip directories
        if member.is_dir():
            member_dir = os.path.join(target_dir, member.filename)
            resolved = os.path.realpath(member_dir)
            if not (resolved == target_resolved or resolved.startswith(target_resolved + os.sep)):
                raise HTTPException(status_code=400, detail=f"Zip slip detected: {member.filename}")
            os.makedirs(resolved, exist_ok=True)
            continue

        # Validate file path
        member_path = os.path.join(target_dir, member.filename)
        resolved = os.path.realpath(member_path)
        if not resolved.startswith(target_resolved + os.sep):
            raise HTTPException(status_code=400, detail=f"Zip slip detected: {member.filename}")

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(resolved), exist_ok=True)

        # Extract single member
        with zf.open(member) as src, open(resolved, "wb") as dst:
            while True:
                chunk = src.read(8 * 1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)

        extracted.append(resolved)

    return extracted
