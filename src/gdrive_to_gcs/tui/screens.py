from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ErrorScreen(ModalScreen[None]):
    """Modal screen to display an error message."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("[bold red]Error[/bold red]", markup=True)
            yield Static(self.message)
            yield Horizontal(
                Button("OK", variant="primary", id="btn-ok"),
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class ConfirmTransferScreen(ModalScreen[bool]):
    """Modal screen to confirm a transfer operation."""

    def __init__(self, selection_label: str, bucket: str, prefix: str) -> None:
        super().__init__()
        self.selection_label = selection_label
        self.bucket = bucket
        self.prefix = prefix

    def compose(self) -> ComposeResult:
        dest = f"gs://{self.bucket}/{self.prefix}" if self.prefix else f"gs://{self.bucket}/"
        with Vertical(id="modal-container"):
            yield Label("[bold]Confirm Transfer[/bold]", markup=True)
            yield Static(f"Selection: [bold]{self.selection_label}[/bold]", markup=True)
            yield Static(f"Destination: [bold]{dest}[/bold]", markup=True)
            yield Static("Existing files in GCS will be [bold]skipped[/bold].", markup=True)
            yield Horizontal(
                Button("Transfer", variant="success", id="btn-transfer"),
                Button("Cancel", variant="error", id="btn-cancel"),
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-transfer")


class TransferReportScreen(ModalScreen[None]):
    """Modal screen showing transfer results."""

    def __init__(self, report) -> None:
        super().__init__()
        self.report = report

    def compose(self) -> ComposeResult:
        r = self.report
        with Vertical(id="modal-container"):
            yield Label("[bold]Transfer Complete[/bold]", markup=True)
            yield Static(f"Total files: {r.total_files}")
            yield Static(f"Transferred: [green]{r.transferred}[/green]", markup=True)
            yield Static(f"Skipped (already exist): [yellow]{r.skipped}[/yellow]", markup=True)
            if r.failed:
                yield Static(f"Failed: [red]{r.failed}[/red]", markup=True)
            yield Static(f"Total bytes: {_format_size(r.total_bytes)}")
            yield Static(f"Elapsed: {r.elapsed_seconds:.1f}s")
            if r.errors:
                yield Label("[bold red]Errors:[/bold red]", markup=True)
                for path, err in r.errors[:10]:
                    yield Static(f"  {path}: {err}")
            yield Horizontal(
                Button("Close", variant="primary", id="btn-close"),
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """Modal screen showing keybinding help."""

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("[bold]Help — Keybindings[/bold]", markup=True)
            yield Static(
                "[bold]F1[/bold]     Help (this screen)\n"
                "[bold]F5[/bold]     Start transfer\n"
                "[bold]F10[/bold]    Quit\n"
                "[bold]r[/bold]      Refresh current panel\n"
                "[bold]a[/bold]      Select all files\n"
                "[bold]d[/bold]      Deselect all files\n"
                "[bold]Tab[/bold]    Switch panel\n"
                "[bold]Esc[/bold]    Cancel / Close\n"
                "\n"
                "[bold]Drive Panel:[/bold]\n"
                "  Enter/Click  Expand folder or toggle file selection\n"
                "\n"
                "[bold]Bucket Panel:[/bold]\n"
                "  Enter/Click  Select destination bucket\n"
                "  Type in prefix field to set GCS path prefix",
                markup=True,
            )
            yield Horizontal(
                Button("Close", variant="primary", id="btn-close"),
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
