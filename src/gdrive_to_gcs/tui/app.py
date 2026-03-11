from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from gdrive_to_gcs.auth import ensure_authenticated
from gdrive_to_gcs.config import DEFAULT_CHUNK_SIZE, WORKSPACE_EXPORT_FORMATS
from gdrive_to_gcs.drive import build_drive_service, iter_folder_tree, resolve_path
from gdrive_to_gcs.exceptions import GDriveToGCSError
from gdrive_to_gcs.gcs import blob_exists, build_gcs_client
from gdrive_to_gcs.transfer import TransferReport, transfer_file
from gdrive_to_gcs.tui.widgets import LogPanel, TransferProgressPanel


class TransferApp(App):
    """Log-only TUI that runs a Drive-to-GCS transfer and displays progress."""

    TITLE = "Google Drive → GCS"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
    ]

    def __init__(
        self,
        drive_folder: Optional[str] = None,
        folder_id: Optional[str] = None,
        bucket: str = "",
        prefix: str = "",
        project: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.drive_folder = drive_folder
        self.folder_id = folder_id
        self.bucket = bucket
        self.prefix = prefix
        self.project = project
        self.drive_service = None
        self.gcs_client = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield LogPanel()
        yield TransferProgressPanel()
        yield Footer()

    def on_mount(self) -> None:
        self._run()

    def log_message(self, text: str) -> None:
        self.query_one(LogPanel).write_log(text)

    @work(thread=True, exclusive=True, group="transfer")
    def _run(self) -> None:
        log = lambda msg: self.call_from_thread(self.log_message, msg)
        progress_panel = self.query_one(TransferProgressPanel)

        # 1. Authenticate
        log("[bold]Authenticating...[/bold]")
        try:
            creds, resolved_project = ensure_authenticated(project=self.project)
            self.project = resolved_project
            self.drive_service = build_drive_service(creds)
            self.gcs_client = build_gcs_client(creds, project=resolved_project)
        except GDriveToGCSError as exc:
            log(f"[bold red]AUTH ERROR:[/bold red] {exc}")
            return

        log(f"[green]Authenticated[/green] (project: {resolved_project or 'auto'})")

        # 2. Resolve folder
        if self.drive_folder:
            log(f"Resolving Drive path: [bold]{self.drive_folder}[/bold]")
            try:
                meta = resolve_path(self.drive_service, self.drive_folder)
                self.folder_id = meta["id"]
                folder_name = meta["name"]
            except Exception as exc:
                log(f"[bold red]ERROR:[/bold red] {exc}")
                return
        else:
            folder_name = self.folder_id
        log(f"Source folder: [bold]{folder_name}[/bold] ({self.folder_id})")
        log(f"Destination: [bold]gs://{self.bucket}/{self.prefix}[/bold]")

        # 3. Scan folder tree
        log("[bold]Scanning folder...[/bold]")
        try:
            all_files = list(iter_folder_tree(self.drive_service, self.folder_id))
        except Exception as exc:
            log(f"[bold red]ERROR:[/bold red] Failed to scan folder: {exc}")
            return

        if not all_files:
            log("[yellow]No files found in folder.[/yellow]")
            return

        log(f"Found [bold]{len(all_files)}[/bold] file(s)")

        # 4. Transfer
        report = TransferReport()
        report.total_files = len(all_files)
        start_time = time.time()

        self.call_from_thread(progress_panel.show_progress, 0, len(all_files), "Starting...")

        for i, file_meta in enumerate(all_files, 1):
            rel_path = file_meta.get("relativePath", file_meta["name"])
            self.call_from_thread(progress_panel.show_progress, i, len(all_files), rel_path)

            try:
                # Build blob path and check for duplicates
                blob_path = f"{self.prefix}/{rel_path}" if self.prefix else rel_path
                blob_path = blob_path.lstrip("/")

                mime_type = file_meta.get("mimeType", "")
                if mime_type in WORKSPACE_EXPORT_FORMATS:
                    _, ext = WORKSPACE_EXPORT_FORMATS[mime_type]
                    if not blob_path.endswith(ext):
                        blob_path += ext

                if blob_exists(self.gcs_client, self.bucket, blob_path):
                    report.skipped += 1
                    log(f"[yellow]SKIP[/yellow] {rel_path} (already exists)")
                    continue

                bytes_transferred = transfer_file(
                    self.drive_service,
                    self.gcs_client,
                    file_meta,
                    self.bucket,
                    self.prefix,
                    chunk_size=DEFAULT_CHUNK_SIZE,
                )
                report.transferred += 1
                report.total_bytes += bytes_transferred
                size_str = _format_size(bytes_transferred)
                log(f"[green]  OK[/green] {rel_path} ({size_str})")

            except Exception as exc:
                report.failed += 1
                report.errors.append((rel_path, str(exc)))
                log(f"[red] ERR[/red] {rel_path}: {exc}")

        report.elapsed_seconds = time.time() - start_time

        # 5. Summary
        self.call_from_thread(progress_panel.show_complete, report)
        log("")
        log("[bold]Transfer complete![/bold]")
        log(f"  Transferred: [green]{report.transferred}[/green]")
        log(f"  Skipped:     [yellow]{report.skipped}[/yellow]")
        if report.failed:
            log(f"  Failed:      [red]{report.failed}[/red]")
        log(f"  Total bytes: {_format_size(report.total_bytes)}")
        log(f"  Elapsed:     {report.elapsed_seconds:.1f}s")
        log("")
        log("[dim]Press q or Esc to exit.[/dim]")


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
