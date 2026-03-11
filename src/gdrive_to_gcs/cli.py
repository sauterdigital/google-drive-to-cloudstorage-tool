"""Entry point for gdrive-to-gcs.

Usage:
  gdrive-to-gcs transfer --drive-folder PATH --bucket BUCKET [--prefix PREFIX] [--project PROJECT]
  gdrive-to-gcs transfer --folder-id ID --bucket BUCKET [--prefix PREFIX] [--project PROJECT]
  gdrive-to-gcs auth login [--project PROJECT]
  gdrive-to-gcs --help
"""
from __future__ import annotations

import sys

from gdrive_to_gcs.auth import login
from gdrive_to_gcs.exceptions import GDriveToGCSError


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        _print_help()
        return

    if args[0] == "auth" and len(args) >= 2 and args[1] == "login":
        _handle_auth_login(args[2:])
        return

    if args[0] == "transfer":
        _handle_transfer(args[1:])
        return

    print(f"Unknown command: {args[0]}", file=sys.stderr)
    _print_help()
    sys.exit(1)


def _handle_auth_login(args: list[str]) -> None:
    project = _extract_option(args, "--project", "-p")
    try:
        login(project=project)
        print("Authentication successful!")
    except GDriveToGCSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _handle_transfer(args: list[str]) -> None:
    drive_folder = _extract_option(args, "--drive-folder", "-d")
    folder_id = _extract_option(args, "--folder-id", "-f")
    bucket = _extract_option(args, "--bucket", "-b")
    prefix = _extract_option(args, "--prefix", "-x") or ""
    project = _extract_option(args, "--project", "-p")

    if not bucket:
        print("Error: --bucket is required.", file=sys.stderr)
        sys.exit(1)

    if not drive_folder and not folder_id:
        print("Error: --drive-folder or --folder-id is required.", file=sys.stderr)
        sys.exit(1)

    from gdrive_to_gcs.tui.app import TransferApp

    app = TransferApp(
        drive_folder=drive_folder,
        folder_id=folder_id,
        bucket=bucket,
        prefix=prefix,
        project=project,
    )
    app.run()


def _extract_option(args: list[str], long_flag: str, short_flag: str) -> str | None:
    for flag in (long_flag, short_flag):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return args[idx + 1]
    return None


def _print_help() -> None:
    print(
        "gdrive-to-gcs - Transfer files from Google Drive to Google Cloud Storage\n"
        "\n"
        "Usage:\n"
        "  gdrive-to-gcs transfer --drive-folder PATH --bucket BUCKET [options]\n"
        "  gdrive-to-gcs transfer --folder-id ID --bucket BUCKET [options]\n"
        "  gdrive-to-gcs auth login [--project PROJECT_ID]\n"
        "  gdrive-to-gcs --help\n"
        "\n"
        "Transfer options:\n"
        "  -d, --drive-folder PATH    Google Drive folder path (e.g. 'My Drive/Data')\n"
        "  -f, --folder-id ID         Google Drive folder ID\n"
        "  -b, --bucket BUCKET        GCS destination bucket name\n"
        "  -x, --prefix PREFIX        GCS path prefix (optional)\n"
        "  -p, --project PROJECT_ID   GCP project ID (auto-detected if omitted)\n"
    )
