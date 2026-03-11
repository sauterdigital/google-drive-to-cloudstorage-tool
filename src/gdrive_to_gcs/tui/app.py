from __future__ import annotations

import sys
import time
from typing import Optional

import pyfiglet
from colorama import init as _colorama_init

from gdrive_to_gcs.auth import ensure_authenticated
from gdrive_to_gcs.config import DEFAULT_CHUNK_SIZE, WORKSPACE_EXPORT_FORMATS
from gdrive_to_gcs.drive import build_drive_service, iter_folder_tree, resolve_path
from gdrive_to_gcs.exceptions import GDriveToGCSError
from gdrive_to_gcs.gcs import blob_exists, build_gcs_client
from gdrive_to_gcs.transfer import TransferReport, transfer_file
from gdrive_to_gcs.tui.widgets import LOGO_WIDTH, get_logo_lines

_colorama_init(autoreset=False)


# ── ANSI helpers ────────────────────────────────────────────────────────────

def _ansi_fg(hex_color: str) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"\033[38;2;{r};{g};{b}m"


_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = _ansi_fg("#1da462")
_YELLOW = _ansi_fg("#fbbc04")
_BLUE   = _ansi_fg("#4285f4")
_RED    = _ansi_fg("#ea4335")
_WHITE  = "\033[97m"
_GRAY   = _ansi_fg("#aaaaaa")


# ── Banner ───────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    logo_lines = get_logo_lines()

    # Big title via pyfiglet — two stacked lines
    raw_top = pyfiglet.figlet_format("Drive to", font="slant").rstrip("\n")
    raw_bot = pyfiglet.figlet_format("Cloud Storage", font="slant").rstrip("\n")
    title_lines = (
        [_BOLD + _GREEN  + line + _RESET for line in raw_top.split("\n")]
        + [_BOLD + _BLUE + line + _RESET for line in raw_bot.split("\n")]
    )
    subtitle = _DIM + _GRAY + "  Transfer files from Google Drive to Cloud Storage" + _RESET

    # Merge side-by-side: logo (left) + title (right)
    n = max(len(logo_lines), len(title_lines))
    logo_pad  = logo_lines  + [" " * LOGO_WIDTH] * (n - len(logo_lines))
    title_pad = title_lines + [""] * (n - len(title_lines))

    for left, right in zip(logo_pad, title_pad):
        print(left + "    " + right)

    print(subtitle)
    print()


# ── Runner ───────────────────────────────────────────────────────────────────

class TransferRunner:
    """Plain-terminal transfer runner using colorama for output."""

    def __init__(
        self,
        drive_folder: Optional[str] = None,
        folder_id: Optional[str] = None,
        bucket: str = "",
        prefix: str = "",
        project: Optional[str] = None,
    ) -> None:
        self.drive_folder = drive_folder
        self.folder_id    = folder_id
        self.bucket       = bucket
        self.prefix       = prefix
        self.project      = project

    def run(self) -> None:
        _print_banner()

        # 1. Credentials
        self._step("Loading credentials...")
        try:
            creds, resolved_project = ensure_authenticated(project=self.project)
            self.project   = resolved_project
            drive_service  = build_drive_service(creds)
            gcs_client     = build_gcs_client(creds, project=resolved_project)
        except GDriveToGCSError as exc:
            self._err(f"AUTH ERROR: {exc}")
            sys.exit(1)
        self._ok(f"Credentials loaded  (project: {resolved_project or 'auto'})")

        # 2. Resolve folder
        if self.drive_folder:
            self._step(f"Resolving Drive path: {self.drive_folder}")
            try:
                meta           = resolve_path(drive_service, self.drive_folder)
                self.folder_id = meta["id"]
                folder_name    = meta["name"]
            except Exception as exc:
                self._err(str(exc))
                sys.exit(1)
        else:
            folder_name = self.folder_id

        self._step(f"Source  {_WHITE}{folder_name}{_RESET}  ({self.folder_id})")
        self._step(f"Dest    {_WHITE}gs://{self.bucket}/{self.prefix}{_RESET}")

        # 3. Scan
        self._step("Scanning folder...")
        try:
            all_files = list(iter_folder_tree(drive_service, self.folder_id))
        except Exception as exc:
            self._err(f"Failed to scan folder: {exc}")
            sys.exit(1)

        if not all_files:
            self._warn("No files found.")
            return

        self._step(f"Found {_WHITE}{len(all_files)}{_RESET} file(s)")
        print()

        # 4. Transfer
        report = TransferReport()
        report.total_files = len(all_files)
        start = time.time()

        for i, file_meta in enumerate(all_files, 1):
            rel_path  = file_meta.get("relativePath", file_meta["name"])
            blob_path = f"{self.prefix}/{rel_path}" if self.prefix else rel_path
            blob_path = blob_path.lstrip("/")

            mime_type = file_meta.get("mimeType", "")
            if mime_type in WORKSPACE_EXPORT_FORMATS:
                _, ext = WORKSPACE_EXPORT_FORMATS[mime_type]
                if not blob_path.endswith(ext):
                    blob_path += ext

            tag = f"[{i}/{len(all_files)}]"

            try:
                if blob_exists(gcs_client, self.bucket, blob_path):
                    report.skipped += 1
                    print(f"  {_YELLOW}{tag}{_RESET} SKIP  {_DIM}{rel_path}{_RESET}")
                    continue

                bytes_tx = transfer_file(
                    drive_service, gcs_client, file_meta,
                    self.bucket, self.prefix, chunk_size=DEFAULT_CHUNK_SIZE,
                )
                report.transferred += 1
                report.total_bytes += bytes_tx
                print(f"  {_GREEN}{tag} OK{_RESET}    {rel_path}  {_DIM}({_format_size(bytes_tx)}){_RESET}")

            except Exception as exc:
                report.failed += 1
                report.errors.append((rel_path, str(exc)))
                print(f"  {_RED}{tag} ERR{_RESET}   {rel_path}: {exc}")

        report.elapsed_seconds = time.time() - start

        # 5. Summary
        print()
        print(_BOLD + _WHITE + "Transfer complete!" + _RESET)
        print(f"  Transferred : {_GREEN}{report.transferred}{_RESET}")
        print(f"  Skipped     : {_YELLOW}{report.skipped}{_RESET}")
        if report.failed:
            print(f"  Failed      : {_RED}{report.failed}{_RESET}")
        print(f"  Total bytes : {_format_size(report.total_bytes)}")
        print(f"  Elapsed     : {report.elapsed_seconds:.1f}s")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _step(self, msg: str) -> None:
        print(f"  {_DIM}›{_RESET} {msg}")

    def _ok(self, msg: str) -> None:
        print(f"  {_GREEN}✓{_RESET} {msg}")

    def _warn(self, msg: str) -> None:
        print(f"  {_YELLOW}!{_RESET} {msg}")

    def _err(self, msg: str) -> None:
        print(f"  {_RED}✗{_RESET} {msg}", file=sys.stderr)


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} PB"
