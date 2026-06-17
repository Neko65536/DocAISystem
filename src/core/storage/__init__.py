"""文件存储适配层。"""

from .azure_blob_storage import (
    AzureBlobStorage,
    build_blob_name,
    delete_file_from_storage,
    download_file_to_local,
    get_storage_backend,
    upload_file_to_storage,
    upload_stream_to_storage,
)

__all__ = [
    "AzureBlobStorage",
    "build_blob_name",
    "delete_file_from_storage",
    "download_file_to_local",
    "get_storage_backend",
    "upload_file_to_storage",
    "upload_stream_to_storage",
]