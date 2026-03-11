from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, ProgressBar, RichLog

from gdrive_to_gcs.transfer import TransferReport


class LogPanel(RichLog):
    """Scrollable log panel that displays transfer events."""

    def __init__(self) -> None:
        super().__init__(highlight=True, markup=True, id="log-panel")

    def write_log(self, message: str) -> None:
        self.write(message, expand=True)


class TransferProgressPanel(Horizontal):
    """Bottom bar showing transfer progress."""

    def compose(self) -> ComposeResult:
        yield Label("Ready", id="transfer-status")
        yield ProgressBar(id="transfer-bar", total=100, show_eta=True)

    def show_progress(self, current: int, total: int, filename: str) -> None:
        self.add_class("active")
        self.query_one("#transfer-status", Label).update(
            f"[{current}/{total}] {filename}"
        )
        bar = self.query_one("#transfer-bar", ProgressBar)
        bar.update(total=total, progress=current)

    def show_complete(self, report: TransferReport) -> None:
        self.query_one("#transfer-status", Label).update(
            f"Done: {report.transferred} transferred, {report.skipped} skipped"
            + (f", {report.failed} failed" if report.failed else "")
        )
        bar = self.query_one("#transfer-bar", ProgressBar)
        bar.update(total=report.total_files, progress=report.total_files)
