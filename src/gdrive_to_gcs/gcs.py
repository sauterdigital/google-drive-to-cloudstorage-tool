from __future__ import annotations

from typing import IO, Optional

from google.auth.credentials import Credentials
from google.cloud import storage

from gdrive_to_gcs.exceptions import GCSUploadError


def build_gcs_client(
    credentials: Credentials,
    project: Optional[str] = None,
) -> storage.Client:
    """Build and return a GCS client."""
    return storage.Client(credentials=credentials, project=project)


def list_buckets(client: storage.Client) -> list[str]:
    """Return list of bucket names accessible to the authenticated user."""
    return [bucket.name for bucket in client.list_buckets()]


def upload_from_stream(
    client: storage.Client,
    bucket_name: str,
    blob_path: str,
    stream: IO[bytes],
    content_type: Optional[str] = None,
    size: Optional[int] = None,
) -> None:
    """Upload a file-like object to GCS.

    For files >5MB the client library automatically uses resumable uploads.
    """
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_file(
            stream,
            size=size,
            content_type=content_type or "application/octet-stream",
        )
    except Exception as exc:
        raise GCSUploadError(
            f"Failed to upload '{blob_path}' to bucket '{bucket_name}': {exc}"
        ) from exc


def blob_exists(
    client: storage.Client,
    bucket_name: str,
    blob_path: str,
) -> bool:
    """Check if a blob already exists in GCS."""
    bucket = client.bucket(bucket_name)
    return bucket.blob(blob_path).exists()
