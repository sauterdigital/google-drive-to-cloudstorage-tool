from __future__ import annotations

import io
from typing import Iterator, Optional

from google.auth.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from gdrive_to_gcs.config import DEFAULT_CHUNK_SIZE, WORKSPACE_EXPORT_FORMATS
from gdrive_to_gcs.exceptions import DriveAPIError, PathNotFoundError

FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "id, name, mimeType, size, modifiedTime"


def build_drive_service(credentials: Credentials):
    """Build and return the Drive v3 service object."""
    return build("drive", "v3", credentials=credentials)


def list_files(
    service,
    folder_id: Optional[str] = None,
    query: Optional[str] = None,
    page_size: int = 100,
) -> list[dict]:
    """List files/folders. If folder_id given, lists its children."""
    q_parts = []
    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")
    if query:
        q_parts.append(query)
    q_parts.append("trashed = false")
    q = " and ".join(q_parts)

    results = []
    page_token = None

    while True:
        resp = (
            service.files()
            .list(
                q=q,
                pageSize=page_size,
                fields=f"nextPageToken, files({FILE_FIELDS})",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
            )
            .execute()
        )
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def resolve_path(service, path: str) -> dict:
    """Resolve a human-readable Drive path to file/folder metadata.

    Supports paths like 'My Drive/Data/subfolder' or just 'Data/subfolder'
    (assumes root if 'My Drive' prefix is omitted).
    """
    path = path.strip("/")
    segments = path.split("/")

    # Strip leading 'My Drive' if present
    if segments and segments[0] == "My Drive":
        segments = segments[1:]

    if not segments:
        # Return root folder
        return service.files().get(fileId="root", fields=FILE_FIELDS, supportsAllDrives=True).execute()

    current_id = "root"
    for segment in segments:
        q = (
            f"'{current_id}' in parents "
            f"and name = '{segment}' "
            f"and trashed = false"
        )
        resp = (
            service.files()
            .list(
                q=q,
                fields=f"files({FILE_FIELDS})",
                pageSize=2,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
            )
            .execute()
        )
        files = resp.get("files", [])
        if not files:
            raise PathNotFoundError(
                f"Path segment '{segment}' not found under parent '{current_id}'. "
                "Use --folder-id to specify the folder ID directly."
            )
        if len(files) > 1:
            raise PathNotFoundError(
                f"Ambiguous path: multiple items named '{segment}' found. "
                "Use --folder-id to specify the exact folder ID."
            )
        current_id = files[0]["id"]
        current_meta = files[0]

    return current_meta


def iter_folder_tree(
    service,
    folder_id: str,
    _prefix: str = "",
) -> Iterator[dict]:
    """Recursively yield all files (not folders) under a folder.

    Each yielded dict includes a 'relativePath' key with the path
    relative to the root folder.
    """
    items = list_files(service, folder_id=folder_id)

    for item in items:
        rel_path = f"{_prefix}{item['name']}" if _prefix else item["name"]

        if item["mimeType"] == FOLDER_MIME:
            yield from iter_folder_tree(service, item["id"], _prefix=f"{rel_path}/")
        else:
            item["relativePath"] = rel_path
            yield item


def download_file(
    service,
    file_id: str,
    mime_type: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress_callback=None,
) -> io.BytesIO:
    """Download a file from Drive into a BytesIO buffer.

    For Workspace files (Docs, Sheets, etc.), exports with a default format.
    """
    buffer = io.BytesIO()

    if mime_type in WORKSPACE_EXPORT_FORMATS:
        export_mime, _ = WORKSPACE_EXPORT_FORMATS[mime_type]
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)

    downloader = MediaIoBaseDownload(buffer, request, chunksize=chunk_size)

    done = False
    while not done:
        try:
            status, done = downloader.next_chunk()
            if progress_callback and status:
                progress_callback(status.resumable_progress, status.total_size)
        except Exception as exc:
            raise DriveAPIError(f"Failed to download file '{file_id}': {exc}") from exc

    buffer.seek(0)
    return buffer
