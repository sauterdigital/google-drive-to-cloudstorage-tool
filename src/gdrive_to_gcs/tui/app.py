from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header
from textual.worker import Worker, WorkerState

from gdrive_to_gcs.auth import ensure_authenticated
from gdrive_to_gcs.config import DEFAULT_CHUNK_SIZE, WORKSPACE_EXPORT_FORMATS
from gdrive_to_gcs.drive import FOLDER_MIME, build_drive_service, iter_folder_tree
from gdrive_to_gcs.exceptions import GDriveToGCSError
from gdrive_to_gcs.gcs import blob_exists, build_gcs_client
from gdrive_to_gcs.transfer import TransferReport, transfer_file
from gdrive_to_gcs.tui.screens import (
    ConfirmTransferScreen,
    ErrorScreen,
    HelpScreen,
    TransferReportScreen,
)
from gdrive_to_gcs.tui.widgets import BucketListPanel, DriveTreePanel, TransferProgressPanel


class GDriveApp(App):
    """TUI application for transferring files from Google Drive to GCS."""

    TITLE = "Google Drive → GCS"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("f5", "transfer", "Transfer"),
        Binding("f10", "quit", "Quit"),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("a", "select_all", "Select All", show=False),
        Binding("d", "deselect_all", "Deselect All", show=False),
    ]

    def __init__(
        self,
        project: Optional[str] = None,
        service_account: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.project = project
        self.service_account = service_account
        self.drive_service = None
        self.gcs_client = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-panels"):
            yield DriveTreePanel()
            yield BucketListPanel()
        yield TransferProgressPanel()
        yield Footer()

    def on_mount(self) -> None:
        self._authenticate()

    @work(thread=True, exclusive=True, group="auth")
    def _authenticate(self) -> None:
        try:
            creds, resolved_project = ensure_authenticated(
                service_account_path=self.service_account,
                project=self.project,
            )
            self.project = resolved_project
            self.drive_service = build_drive_service(creds)
            self.gcs_client = build_gcs_client(creds, project=resolved_project)
        except GDriveToGCSError as exc:
            self.app.call_from_thread(
                self.push_screen,
                ErrorScreen(str(exc)),
            )
            return

        # Trigger loading of Drive tree and bucket list
        self.app.call_from_thread(self._trigger_load)

    def _trigger_load(self) -> None:
        self.query_one(DriveTreePanel)._load_root()
        self.query_one(BucketListPanel)._load_buckets()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_transfer(self) -> None:
        drive_panel = self.query_one(DriveTreePanel)
        bucket_panel = self.query_one(BucketListPanel)

        files = drive_panel.get_selected_files()
        bucket = bucket_panel.selected_bucket
        prefix = bucket_panel.get_prefix()

        if not files:
            self.push_screen(ErrorScreen("No files selected.\nExpand folders and click files to select them."))
            return

        if not bucket:
            self.push_screen(ErrorScreen("No bucket selected.\nClick a bucket in the right panel."))
            return

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self._run_transfer(files, bucket, prefix)

        # Count folders and files separately for the confirmation
        folders = [f for f in files if f.get("mimeType") == FOLDER_MIME]
        regular = [f for f in files if f.get("mimeType") != FOLDER_MIME]
        label = f"{len(regular)} file(s)"
        if folders:
            label += f" + {len(folders)} folder(s)"

        self.push_screen(
            ConfirmTransferScreen(label, bucket, prefix),
            callback=on_confirm,
        )

    def action_refresh(self) -> None:
        focused = self.focused
        if focused:
            # Find which panel contains the focused widget
            drive_panel = self.query_one(DriveTreePanel)
            bucket_panel = self.query_one(BucketListPanel)
            if focused in drive_panel.query("*") or focused is drive_panel:
                drive_panel.refresh_tree()
            else:
                bucket_panel.refresh_buckets()

    def action_select_all(self) -> None:
        self.query_one(DriveTreePanel).select_all_visible()

    def action_deselect_all(self) -> None:
        self.query_one(DriveTreePanel).deselect_all()

    @work(thread=True, exclusive=True, group="transfer")
    def _run_transfer(self, selected_items: list[dict], bucket: str, prefix: str) -> TransferReport:
        report = TransferReport()
        start_time = time.time()

        progress_panel = self.query_one(TransferProgressPanel)
        self.app.call_from_thread(progress_panel.show_progress, 0, 1, "Scanning folders...")

        # Expand selected folders into individual files, preserving structure
        all_files: list[dict] = []
        for item in selected_items:
            if item.get("mimeType") == FOLDER_MIME:
                folder_name = item["name"]
                try:
                    for file_meta in iter_folder_tree(self.drive_service, item["id"]):
                        # Prefix with folder name to preserve structure
                        file_meta["relativePath"] = f"{folder_name}/{file_meta['relativePath']}"
                        all_files.append(file_meta)
                except Exception as exc:
                    report.failed += 1
                    report.errors.append((folder_name, f"Failed to scan folder: {exc}"))
            else:
                if "relativePath" not in item:
                    item["relativePath"] = item["name"]
                all_files.append(item)

        report.total_files = len(all_files)

        if not all_files:
            report.elapsed_seconds = time.time() - start_time
            self.app.call_from_thread(progress_panel.hide)
            self.app.call_from_thread(self.push_screen, TransferReportScreen(report))
            return report

        self.app.call_from_thread(
            progress_panel.show_progress, 0, len(all_files), "Starting transfer..."
        )

        for i, file_meta in enumerate(all_files, 1):
            rel_path = file_meta.get("relativePath", file_meta["name"])
            self.app.call_from_thread(progress_panel.show_progress, i, len(all_files), rel_path)

            try:
                # Check if blob already exists in GCS — skip if so
                blob_path = f"{prefix}/{rel_path}" if prefix else rel_path
                blob_path = blob_path.lstrip("/")

                # Adjust extension for Workspace files
                mime_type = file_meta.get("mimeType", "")
                if mime_type in WORKSPACE_EXPORT_FORMATS:
                    _, ext = WORKSPACE_EXPORT_FORMATS[mime_type]
                    if not blob_path.endswith(ext):
                        blob_path += ext

                if blob_exists(self.gcs_client, bucket, blob_path):
                    report.skipped += 1
                    continue

                bytes_transferred = transfer_file(
                    self.drive_service,
                    self.gcs_client,
                    file_meta,
                    bucket,
                    prefix,
                    chunk_size=DEFAULT_CHUNK_SIZE,
                )
                report.transferred += 1
                report.total_bytes += bytes_transferred
            except Exception as exc:
                report.failed += 1
                report.errors.append((rel_path, str(exc)))

        report.elapsed_seconds = time.time() - start_time

        self.app.call_from_thread(progress_panel.hide)
        self.app.call_from_thread(self.push_screen, TransferReportScreen(report))

        return report
