"""File transfer utilities for nodes without shared storage.

Downloads input frames from the main machine and uploads results back.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class FileTransfer:
    """Handles file downloads/uploads between node and main machine."""

    def __init__(self, main_url: str, node_id: str, timeout: float = 300):
        self.main_url = main_url.rstrip("/")
        self.node_id = node_id
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.main_url}/api/nodes/{self.node_id}/files/{path}"

    def list_files(self, clip_name: str, pass_name: str) -> list[str]:
        """List files available for a clip pass."""
        with httpx.Client(timeout=30) as client:
            r = client.get(self._url(f"{clip_name}/{pass_name}"))
            r.raise_for_status()
            return r.json().get("files", [])

    def download_pass(self, clip_name: str, pass_name: str, dest_dir: str) -> int:
        """Download all files for a clip pass to a local directory.

        Returns the number of files downloaded.
        """
        files = self.list_files(clip_name, pass_name)
        if not files:
            return 0

        os.makedirs(dest_dir, exist_ok=True)
        count = 0

        with httpx.Client(timeout=self.timeout) as client:
            for fname in files:
                dest_path = os.path.join(dest_dir, fname)
                if os.path.isfile(dest_path):
                    count += 1
                    continue  # skip already downloaded

                url = self._url(f"{clip_name}/{pass_name}/{fname}")
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    with open(dest_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8 * 1024 * 1024):
                            f.write(chunk)
                count += 1

        logger.info(f"Downloaded {count} files for {clip_name}/{pass_name}")
        return count

    def upload_file(self, clip_name: str, pass_name: str, file_path: str) -> None:
        """Upload a single result file to the main machine."""
        fname = Path(file_path).name
        url = self._url(f"{clip_name}/{pass_name}/{fname}")

        with httpx.Client(timeout=self.timeout) as client:
            with open(file_path, "rb") as f:
                r = client.post(url, files={"file": (fname, f)})
                r.raise_for_status()

    def upload_directory(self, clip_name: str, pass_name: str, src_dir: str) -> int:
        """Upload all files in a directory as results.

        Returns the number of files uploaded.
        """
        if not os.path.isdir(src_dir):
            return 0

        files = sorted(os.listdir(src_dir))
        count = 0

        for fname in files:
            fpath = os.path.join(src_dir, fname)
            if os.path.isfile(fpath):
                self.upload_file(clip_name, pass_name, fpath)
                count += 1

        logger.info(f"Uploaded {count} files for {clip_name}/{pass_name}")
        return count
