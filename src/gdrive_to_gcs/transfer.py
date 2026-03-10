from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from gdrive_to_gcs.config import DEFAULT_CHUNK_SIZE, WORKSPACE_EXPORT_FORMATS
from gdrive_to_gcs.drive import download_file, iter_folder_tree
from gdrive_to_gcs.gcs import blob_exists, upload_from_stream


@dataclass
class TransferReport:
    total_files: int = 0
    transferred: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    total_bytes: int = 0
    elapsed_seconds: float = 0.0


def transfer_file(
    drive_service,
    gcs_client,
    file_meta: dict,
    bucket_name: str,
    destination_prefix: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None,
) -> int:
    """Transfer a single file from Drive to GCS. Returns bytes transferred."""
    file_id = file_meta["id"]
    mime_type = file_meta["mimeType"]
    rel_path = file_meta.get("relativePath", file_meta["name"])

    # Build GCS destination path
    blob_path = f"{destination_prefix}/{rel_path}" if destination_prefix else rel_path
    blob_path = blob_path.lstrip("/")

    # Adjust extension for exported Workspace files
    if mime_type in WORKSPACE_EXPORT_FORMATS:
        _, ext = WORKSPACE_EXPORT_FORMATS[mime_type]
        if not blob_path.endswith(ext):
            blob_path += ext

    file_size = int(file_meta.get("size", 0))

    def on_progress(downloaded: int, total: Optional[int]) -> None:
        if progress and task_id is not None and total:
            progress.update(task_id, completed=downloaded, total=total)

    # Download from Drive
    buffer = download_file(
        drive_service,
        file_id,
        mime_type,
        chunk_size=chunk_size,
        progress_callback=on_progress,
    )

    # Get actual size from buffer
    buffer.seek(0, 2)
    actual_size = buffer.tell()
    buffer.seek(0)

    # Upload to GCS
    upload_from_stream(
        gcs_client,
        bucket_name,
        blob_path,
        buffer,
        size=actual_size,
    )

    return actual_size


def transfer_folder(
    drive_service,
    gcs_client,
    folder_id: str,
    bucket_name: str,
    destination_prefix: str = "",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    dry_run: bool = False,
    skip_existing: bool = False,
    include_pattern: Optional[str] = None,
    exclude_pattern: Optional[str] = None,
    console: Optional[Console] = None,
) -> TransferReport:
    """Transfer all files under a Drive folder to GCS."""
    console = console or Console()
    report = TransferReport()
    start_time = time.time()

    # Enumerate all files
    console.print("[bold]Scanning Drive folder...[/bold]")
    files = list(iter_folder_tree(drive_service, folder_id))
    report.total_files = len(files)
    console.print(f"Found [bold]{len(files)}[/bold] files.")

    if not files:
        report.elapsed_seconds = time.time() - start_time
        return report

    # Apply include/exclude filters
    if include_pattern:
        files = [f for f in files if fnmatch.fnmatch(f["name"], include_pattern)]
    if exclude_pattern:
        files = [f for f in files if not fnmatch.fnmatch(f["name"], exclude_pattern)]

    if dry_run:
        console.print("\n[bold yellow]DRY RUN — no files will be transferred:[/bold yellow]")
        for f in files:
            size = _format_size(int(f.get("size", 0)))
            console.print(f"  {f.get('relativePath', f['name'])}  ({size})")
        report.elapsed_seconds = time.time() - start_time
        return report

    # Transfer with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        overall = progress.add_task("Overall", total=len(files))

        for file_meta in files:
            rel_path = file_meta.get("relativePath", file_meta["name"])
            blob_path = f"{destination_prefix}/{rel_path}" if destination_prefix else rel_path
            blob_path = blob_path.lstrip("/")

            # Skip existing
            if skip_existing and blob_exists(gcs_client, bucket_name, blob_path):
                report.skipped += 1
                progress.advance(overall)
                continue

            file_task = progress.add_task(
                f"  {rel_path}",
                total=int(file_meta.get("size", 0)) or None,
            )

            try:
                bytes_transferred = transfer_file(
                    drive_service,
                    gcs_client,
                    file_meta,
                    bucket_name,
                    destination_prefix,
                    chunk_size=chunk_size,
                    progress=progress,
                    task_id=file_task,
                )
                report.transferred += 1
                report.total_bytes += bytes_transferred
            except Exception as exc:
                report.failed += 1
                report.errors.append((rel_path, str(exc)))
                console.print(f"[red]Error transferring {rel_path}: {exc}[/red]")
            finally:
                progress.remove_task(file_task)
                progress.advance(overall)

    report.elapsed_seconds = time.time() - start_time
    return report


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
