APP_NAME = "gdrive-to-gcs"

DEFAULT_CHUNK_SIZE = 50 * 1024 * 1024  # 50 MB

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Threshold above which SpooledTemporaryFile spills to disk
LARGE_FILE_THRESHOLD = 256 * 1024 * 1024  # 256 MB

# Export formats for Google Workspace files
WORKSPACE_EXPORT_FORMATS = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}
