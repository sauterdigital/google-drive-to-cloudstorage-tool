"""Entry point for gdrive-to-gcs.

- No args: launches the TUI
- auth login [--project PROJECT]: runs gcloud auth flow
"""
from __future__ import annotations

import sys

from gdrive_to_gcs.auth import login
from gdrive_to_gcs.exceptions import GDriveToGCSError


def main() -> None:
    args = sys.argv[1:]

    # Handle: gdrive-to-gcs auth login [--project PROJECT] [-s SERVICE_ACCOUNT]
    if len(args) >= 2 and args[0] == "auth" and args[1] == "login":
        _handle_auth_login(args[2:])
        return

    # Handle: gdrive-to-gcs --help / -h
    if args and args[0] in ("--help", "-h"):
        _print_help()
        return

    # Default: launch TUI
    project = _extract_option(args, "--project", "-p")

    from gdrive_to_gcs.tui.app import GDriveApp

    app = GDriveApp(project=project)
    app.run()


def _handle_auth_login(args: list[str]) -> None:
    project = _extract_option(args, "--project", "-p")

    try:
        login(project=project)
        print("Authentication successful!")
    except GDriveToGCSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


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
        "  gdrive-to-gcs                          Launch TUI\n"
        "  gdrive-to-gcs --project PROJECT_ID     Launch TUI with project\n"
        "  gdrive-to-gcs auth login               Authenticate via gcloud\n"
        "  gdrive-to-gcs auth login -p PROJECT_ID Authenticate with project\n"
        "  gdrive-to-gcs --help                   Show this help\n"
    )
