from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import google.auth
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from gdrive_to_gcs.config import SCOPES
from gdrive_to_gcs.exceptions import AuthenticationError


def login(
    project: Optional[str] = None,
    scopes: Optional[list[str]] = None,
) -> None:
    """Run `gcloud auth application-default login` to authenticate interactively.

    This opens the browser for the user to log in with their Google account.
    The credentials are stored by gcloud and picked up automatically via ADC.
    """
    scopes = scopes or SCOPES

    gcloud = shutil.which("gcloud")
    if not gcloud:
        raise AuthenticationError(
            "gcloud CLI not found. Install it from:\n"
            "  https://cloud.google.com/sdk/docs/install"
        )

    cmd = [
        gcloud,
        "auth",
        "application-default",
        "login",
        "--scopes",
        ",".join(scopes),
    ]

    if project:
        cmd.extend(["--billing-project", project])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise AuthenticationError(f"gcloud login failed (exit code {exc.returncode})") from exc

    # Also set the active project so quota project is configured
    if project:
        try:
            subprocess.run([gcloud, "config", "set", "project", project], check=True)
            subprocess.run(
                [gcloud, "auth", "application-default", "set-quota-project", project],
                check=True,
            )
        except subprocess.CalledProcessError:
            pass  # Non-critical, credentials still work


def get_credentials(
    service_account_path: Optional[Path] = None,
    project: Optional[str] = None,
    scopes: Optional[list[str]] = None,
) -> Credentials:
    """Load credentials using Application Default Credentials (ADC).

    Priority:
    1. Service account JSON file (if provided)
    2. ADC (gcloud auth application-default login, GOOGLE_APPLICATION_CREDENTIALS env var, etc.)
    """
    scopes = scopes or SCOPES

    if service_account_path:
        return _load_service_account(service_account_path, scopes)

    return _load_adc(scopes, project)


def ensure_authenticated(
    service_account_path: Optional[Path] = None,
    project: Optional[str] = None,
) -> tuple[Credentials, str | None]:
    """High-level entry point: get valid credentials ready to use.

    Returns (credentials, resolved_project) where resolved_project is the
    project from the argument, ADC default, or gcloud config.
    """
    try:
        creds = get_credentials(service_account_path, project)
    except Exception as exc:
        raise AuthenticationError(
            f"Authentication failed: {exc}\n"
            "Run 'gdrive-to-gcs auth login --project YOUR_PROJECT_ID' to authenticate."
        ) from exc

    resolved_project = project or getattr(creds, "quota_project_id", None) or get_gcloud_project()
    return creds, resolved_project


def _load_service_account(path: Path, scopes: list[str]) -> Credentials:
    if not path.exists():
        raise AuthenticationError(f"Service account file not found: {path}")
    try:
        return service_account.Credentials.from_service_account_file(
            str(path), scopes=scopes
        )
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise AuthenticationError(
            f"Invalid service account file '{path}': {exc}"
        ) from exc


def get_gcloud_project() -> Optional[str]:
    """Try to get the active project from gcloud config."""
    gcloud = shutil.which("gcloud")
    if not gcloud:
        return None
    try:
        result = subprocess.run(
            [gcloud, "config", "get-value", "project"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _load_adc(scopes: list[str], project: Optional[str] = None) -> Credentials:
    """Load Application Default Credentials."""
    try:
        creds, default_project = google.auth.default(scopes=scopes)
    except google.auth.exceptions.DefaultCredentialsError as exc:
        raise AuthenticationError(
            "No credentials found. Run:\n"
            "  gdrive-to-gcs auth login --project YOUR_PROJECT_ID"
        ) from exc

    if creds.expired:
        creds.refresh(Request())

    # Set quota project so APIs like Drive don't fail with 403
    quota_project = project or default_project or get_gcloud_project()
    if quota_project and hasattr(creds, "with_quota_project"):
        creds = creds.with_quota_project(quota_project)

    return creds
