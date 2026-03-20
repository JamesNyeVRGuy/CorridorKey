"""Abstract file storage backend for clip data (CRKY-35).

Two implementations:
- LocalStorage: wraps the current disk-based file I/O (default)
- S3Storage: any S3-compatible service (AWS S3, MinIO, Backblaze B2, R2)

Configured via CK_STORAGE_BACKEND=local|s3 plus S3 credentials.

Usage:
    from web.api.file_storage import get_file_storage
    storage = get_file_storage()
    storage.write_file("org_id/clip/Output/FG/frame_0001.exr", data)
    data = storage.read_file("org_id/clip/Output/FG/frame_0001.exr")
"""

from __future__ import annotations

import io
import logging
import os
import shutil
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class FileStorage(ABC):
    """Abstract file storage interface for clip data."""

    @abstractmethod
    def read_file(self, key: str) -> bytes:
        """Read a file by key. Raises FileNotFoundError if missing."""

    @abstractmethod
    def write_file(self, key: str, data: bytes) -> None:
        """Write data to a file at the given key."""

    @abstractmethod
    def delete_file(self, key: str) -> bool:
        """Delete a single file. Returns True if it existed."""

    @abstractmethod
    def list_files(self, prefix: str) -> list[str]:
        """List file keys under a prefix."""

    @abstractmethod
    def file_exists(self, key: str) -> bool:
        """Check if a file exists."""

    @abstractmethod
    def get_file_size(self, key: str) -> int:
        """Get file size in bytes. Returns 0 if missing."""

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """Delete all files under a prefix. Returns count deleted."""

    @abstractmethod
    def get_total_size(self, prefix: str) -> int:
        """Get total size of all files under a prefix in bytes."""

    @abstractmethod
    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Generate a presigned download URL. Returns None if not supported."""

    @abstractmethod
    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Generate a presigned upload URL. Returns None if not supported."""

    @property
    @abstractmethod
    def backend_type(self) -> str:
        """Return 'local' or 's3'."""


class LocalStorage(FileStorage):
    """File storage backed by the local filesystem.

    Keys are relative paths resolved against the base directory.
    This is the default implementation matching the existing behavior.
    """

    def __init__(self, base_dir: str):
        self._base = os.path.realpath(base_dir)

    def _resolve(self, key: str) -> str:
        """Resolve a key to an absolute path, preventing traversal and symlink escape."""
        path = os.path.realpath(os.path.join(self._base, key))
        if path != self._base and not path.startswith(self._base + os.sep):
            raise ValueError(f"Path traversal detected: {key}")
        return path

    def read_file(self, key: str) -> bytes:
        path = self._resolve(key)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {key}")
        with open(path, "rb") as f:
            return f.read()

    def write_file(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def delete_file(self, key: str) -> bool:
        path = self._resolve(key)
        if os.path.isfile(path):
            os.unlink(path)
            return True
        return False

    def list_files(self, prefix: str) -> list[str]:
        path = self._resolve(prefix)
        if not os.path.isdir(path):
            return []
        result = []
        for dirpath, _, filenames in os.walk(path):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(fpath, self._base)
                result.append(rel)
        return sorted(result)

    def file_exists(self, key: str) -> bool:
        return os.path.isfile(self._resolve(key))

    def get_file_size(self, key: str) -> int:
        path = self._resolve(key)
        if os.path.isfile(path):
            return os.path.getsize(path)
        return 0

    def delete_prefix(self, prefix: str) -> int:
        path = self._resolve(prefix)
        if not os.path.isdir(path):
            return 0
        files = self.list_files(prefix)
        shutil.rmtree(path)
        return len(files)

    def get_total_size(self, prefix: str) -> int:
        path = self._resolve(prefix)
        if not os.path.isdir(path):
            return 0
        total = 0
        for dirpath, _, filenames in os.walk(path):
            for fname in filenames:
                total += os.path.getsize(os.path.join(dirpath, fname))
        return total

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        return None  # Local storage doesn't support presigned URLs

    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str | None:
        return None

    @property
    def backend_type(self) -> str:
        return "local"


class S3Storage(FileStorage):
    """File storage backed by any S3-compatible service.

    Requires boto3. Configure via environment variables:
    - CK_S3_BUCKET: bucket name (required)
    - CK_S3_PREFIX: key prefix within the bucket (default: "")
    - CK_S3_ENDPOINT_URL: custom endpoint (for MinIO, B2, R2)
    - CK_S3_REGION: AWS region (default: us-east-1)
    - CK_S3_ACCESS_KEY_ID: access key
    - CK_S3_SECRET_ACCESS_KEY: secret key

    When running on AWS with IAM roles, access key env vars are optional.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        try:
            import boto3
        except ImportError as e:
            raise RuntimeError("boto3 is required for S3 storage. Install with: uv sync --extra s3") from e

        self._bucket = bucket
        self._prefix = prefix.strip("/")

        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key_id and secret_access_key:
            kwargs["aws_access_key_id"] = access_key_id
            kwargs["aws_secret_access_key"] = secret_access_key

        self._client = boto3.client("s3", **kwargs)
        self._resource = boto3.resource("s3", **kwargs)
        self._bucket_obj = self._resource.Bucket(bucket)
        logger.info(f"S3 storage initialized: s3://{bucket}/{prefix}")

    def _key(self, key: str) -> str:
        """Build the full S3 object key with prefix."""
        if self._prefix:
            return f"{self._prefix}/{key}"
        return key

    def read_file(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=self._key(key))
            return response["Body"].read()
        except self._client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"S3 key not found: {key}") from None
        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                raise FileNotFoundError(f"S3 key not found: {key}") from e
            raise

    def write_file(self, key: str, data: bytes) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key(key),
            Body=io.BytesIO(data),
        )

    def delete_file(self, key: str) -> bool:
        full_key = self._key(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=full_key)
        except Exception:
            return False
        self._client.delete_object(Bucket=self._bucket, Key=full_key)
        return True

    def list_files(self, prefix: str) -> list[str]:
        full_prefix = self._key(prefix)
        if not full_prefix.endswith("/"):
            full_prefix += "/"
        result = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                # Strip the configured prefix to return relative keys
                key = obj["Key"]
                if self._prefix and key.startswith(self._prefix + "/"):
                    key = key[len(self._prefix) + 1 :]
                result.append(key)
        return sorted(result)

    def file_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key(key))
            return True
        except Exception:
            return False

    def get_file_size(self, key: str) -> int:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=self._key(key))
            return response.get("ContentLength", 0)
        except Exception:
            return 0

    def delete_prefix(self, prefix: str) -> int:
        objects = self.list_files(prefix)
        if not objects:
            return 0
        # S3 delete_objects accepts up to 1000 keys per call
        full_keys = [{"Key": self._key(k)} for k in objects]
        for i in range(0, len(full_keys), 1000):
            batch = full_keys[i : i + 1000]
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": batch, "Quiet": True},
            )
        return len(objects)

    def get_total_size(self, prefix: str) -> int:
        full_prefix = self._key(prefix)
        if not full_prefix.endswith("/"):
            full_prefix += "/"
        total = 0
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                total += obj.get("Size", 0)
        return total

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": self._key(key)},
                ExpiresIn=expires_in,
            )
        except Exception:
            return None

    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str | None:
        try:
            return self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": self._key(key)},
                ExpiresIn=expires_in,
            )
        except Exception:
            return None

    @property
    def backend_type(self) -> str:
        return "s3"


# --- Singleton ---

_storage: FileStorage | None = None


def get_file_storage() -> FileStorage:
    """Get the configured file storage backend singleton."""
    global _storage
    if _storage is not None:
        return _storage

    backend = os.environ.get("CK_STORAGE_BACKEND", "local").lower()

    if backend == "s3":
        bucket = os.environ.get("CK_S3_BUCKET", "")
        if not bucket:
            raise RuntimeError("CK_S3_BUCKET is required when CK_STORAGE_BACKEND=s3")
        _storage = S3Storage(
            bucket=bucket,
            prefix=os.environ.get("CK_S3_PREFIX", ""),
            endpoint_url=os.environ.get("CK_S3_ENDPOINT_URL"),
            region=os.environ.get("CK_S3_REGION", "us-east-1"),
            access_key_id=os.environ.get("CK_S3_ACCESS_KEY_ID"),
            secret_access_key=os.environ.get("CK_S3_SECRET_ACCESS_KEY"),
        )
    else:
        from backend.project import projects_root

        base = os.environ.get("CK_CLIPS_DIR", "") or projects_root()
        _storage = LocalStorage(base)

    logger.info(f"File storage backend: {_storage.backend_type}")
    return _storage


def reset_file_storage() -> None:
    """Reset the singleton (for testing)."""
    global _storage
    _storage = None
