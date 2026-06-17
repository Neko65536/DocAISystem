"""Azure Blob 存储适配器。"""
from __future__ import annotations

from dataclasses import dataclass
from io import BufferedIOBase
from pathlib import Path
from typing import Optional, BinaryIO

from config import SystemConfig, get_config

try:
    from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
    from azure.storage.blob import BlobServiceClient, ContentSettings
except Exception:  # pragma: no cover - 依赖未安装时允许导入模块
    BlobServiceClient = None
    ContentSettings = None

    class ResourceExistsError(Exception):
        pass

    class ResourceNotFoundError(Exception):
        pass


@dataclass(frozen=True)
class StoredFileResult:
    storage_key: str
    container_name: str


def build_blob_name(session_id: str, file_name: str, prefix: str = "sessions") -> str:
    safe_name = Path(file_name).name
    safe_session = str(session_id).strip().strip("/")
    safe_prefix = str(prefix).strip().strip("/") or "sessions"
    return f"{safe_prefix}/{safe_session}/{safe_name}"


class AzureBlobStorage:
    """面向项目的 Blob 存储访问封装。"""

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self._service_client = None
        self._container_client = None

    @property
    def enabled(self) -> bool:
        storage = self.config.storage
        return bool(
            storage.enabled
            and storage.provider == "azure_blob"
            and storage.azure_connection_string
            and storage.azure_container_name
        )

    def _get_container_client(self):
        if not self.enabled:
            return None
        if BlobServiceClient is None:
            raise RuntimeError("未安装 azure-storage-blob，无法启用 Azure Blob 存储")
        if self._container_client is not None:
            return self._container_client

        storage = self.config.storage
        self._service_client = BlobServiceClient.from_connection_string(storage.azure_connection_string)
        container_client = self._service_client.get_container_client(storage.azure_container_name)
        try:
            container_client.create_container()
        except ResourceExistsError:
            pass
        self._container_client = container_client
        return self._container_client

    def upload_file(self, local_path: Path, blob_name: str, content_type: Optional[str] = None) -> Optional[str]:
        if not self.enabled:
            return None

        container_client = self._get_container_client()
        settings = ContentSettings(content_type=content_type) if content_type and ContentSettings else None
        with local_path.open("rb") as handle:
            container_client.upload_blob(
                name=blob_name,
                data=handle,
                overwrite=True,
                content_settings=settings,
            )
        return blob_name

    def upload_stream(self, stream: BinaryIO, blob_name: str, content_type: Optional[str] = None) -> Optional[str]:
        if not self.enabled:
            return None

        container_client = self._get_container_client()
        settings = ContentSettings(content_type=content_type) if content_type and ContentSettings else None
        container_client.upload_blob(
            name=blob_name,
            data=stream,
            overwrite=True,
            content_settings=settings,
        )
        return blob_name

    def download_to_path(self, blob_name: str, destination: Path) -> Path:
        if not self.enabled:
            raise RuntimeError("Azure Blob 存储未启用")

        container_client = self._get_container_client()
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob_client = container_client.get_blob_client(blob_name)
        stream = blob_client.download_blob()
        with destination.open("wb") as handle:
            handle.write(stream.readall())
        return destination

    def delete_file(self, blob_name: str) -> bool:
        if not self.enabled:
            return False

        container_client = self._get_container_client()
        try:
            container_client.delete_blob(blob_name)
            return True
        except ResourceNotFoundError:
            return False


def get_storage_backend(config: Optional[SystemConfig] = None) -> AzureBlobStorage:
    return AzureBlobStorage(config=config)


def upload_file_to_storage(
    local_path: str | Path,
    config: Optional[SystemConfig] = None,
    blob_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    path_obj = Path(local_path)
    storage = get_storage_backend(config)
    if not storage.enabled:
        return None
    resolved_blob_name = blob_name or path_obj.name
    return storage.upload_file(path_obj, resolved_blob_name, content_type=content_type)


def upload_stream_to_storage(
    stream: BinaryIO,
    config: Optional[SystemConfig] = None,
    blob_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    storage = get_storage_backend(config)
    if not storage.enabled:
        return None
    if not blob_name:
        raise ValueError("blob_name 不能为空")
    return storage.upload_stream(stream, blob_name, content_type=content_type)


def download_file_to_local(
    blob_name: str,
    destination: str | Path,
    config: Optional[SystemConfig] = None,
) -> Path:
    storage = get_storage_backend(config)
    return storage.download_to_path(blob_name, Path(destination))


def delete_file_from_storage(blob_name: Optional[str], config: Optional[SystemConfig] = None) -> bool:
    if not blob_name:
        return False
    storage = get_storage_backend(config)
    return storage.delete_file(blob_name)