"""Object storage adapters for uploaded knowledge documents."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    uri: str
    local_path: Path
    size: int
    backend: str


@dataclass(frozen=True)
class DeletedObject:
    key: str
    uri: str
    local_path: Path
    deleted_local: bool
    deleted_remote: bool
    backend: str


class ObjectStoragePort(Protocol):
    backend: str

    def put_bytes(self, key: str, content: bytes) -> StoredObject: ...

    def delete(self, key: str) -> DeletedObject: ...

    def local_path_for(self, key: str) -> Path: ...

    def get_bytes(self, key: str) -> bytes: ...

    def cleanup_local_cache(self, key: str) -> None: ...


class LocalObjectStorageAdapter:
    """Store uploaded objects on local disk."""

    backend = "local"

    def __init__(self, *, root: Path) -> None:
        self._root = root

    def put_bytes(self, key: str, content: bytes) -> StoredObject:
        path = self.local_path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return StoredObject(
            key=key,
            uri=path.as_posix(),
            local_path=path,
            size=len(content),
            backend=self.backend,
        )

    def delete(self, key: str) -> DeletedObject:
        path = self.local_path_for(key)
        deleted = False
        if path.exists():
            if not path.is_file():
                raise ValueError("object_path_is_not_a_file")
            path.unlink()
            deleted = True
        return DeletedObject(
            key=key,
            uri=path.as_posix(),
            local_path=path,
            deleted_local=deleted,
            deleted_remote=False,
            backend=self.backend,
        )

    def local_path_for(self, key: str) -> Path:
        return _safe_local_path(self._root, key)

    def get_bytes(self, key: str) -> bytes:
        path = self.local_path_for(key)
        if not path.exists():
            raise FileNotFoundError(f"object_not_found: {key}")
        return path.read_bytes()

    def cleanup_local_cache(self, key: str) -> None:
        path = self.local_path_for(key)
        if path.exists():
            path.unlink()


class MinioObjectStorageAdapter:
    """Store uploaded objects in MinIO and keep a local cache for indexing."""

    backend = "minio"

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool,
        local_cache_root: Path,
    ) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._secure = secure
        self._local_cache_root = local_cache_root
        self._client = None

    def put_bytes(self, key: str, content: bytes) -> StoredObject:
        path = self.local_path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

        client = self._get_client()
        if not client.bucket_exists(self._bucket):
            client.make_bucket(self._bucket)
        client.put_object(
            self._bucket,
            key,
            BytesIO(content),
            length=len(content),
            content_type=_content_type_for_key(key),
        )
        return StoredObject(
            key=key,
            uri=f"minio://{self._bucket}/{key}",
            local_path=path,
            size=len(content),
            backend=self.backend,
        )

    def delete(self, key: str) -> DeletedObject:
        path = self.local_path_for(key)
        deleted_local = False
        if path.exists():
            if not path.is_file():
                raise ValueError("object_path_is_not_a_file")
            path.unlink()
            deleted_local = True

        deleted_remote = False
        client = self._get_client()
        try:
            client.remove_object(self._bucket, key)
            deleted_remote = True
        except Exception as exc:
            if "NoSuchKey" not in str(exc) and "not found" not in str(exc).lower():
                raise

        return DeletedObject(
            key=key,
            uri=f"minio://{self._bucket}/{key}",
            local_path=path,
            deleted_local=deleted_local,
            deleted_remote=deleted_remote,
            backend=self.backend,
        )

    def local_path_for(self, key: str) -> Path:
        return _safe_local_path(self._local_cache_root, key)

    def get_bytes(self, key: str) -> bytes:
        client = self._get_client()
        response = client.get_object(self._bucket, key)
        try:
            data: bytes = response.read()
            return data
        finally:
            response.close()
            response.release_conn()

    def cleanup_local_cache(self, key: str) -> None:
        path = self.local_path_for(key)
        if path.exists():
            path.unlink()

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError(
                "MinIO object storage backend requires the optional 'minio' package"
            ) from exc
        self._client = Minio(
            self._endpoint,
            access_key=self._access_key,
            secret_key=self._secret_key,
            secure=self._secure,
        )
        return self._client


def _safe_local_path(root: Path, key: str) -> Path:
    normalized_key = key.replace("\\", "/").lstrip("/")
    candidate = (root / normalized_key).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError("invalid_object_key")
    return candidate


def _content_type_for_key(key: str) -> str:
    suffix = Path(key).suffix.lower()
    if suffix == ".md":
        return "text/markdown; charset=utf-8"
    if suffix == ".txt":
        return "text/plain; charset=utf-8"
    return "application/octet-stream"
