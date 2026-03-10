class GDriveToGCSError(Exception):
    """Base exception for gdrive-to-gcs."""


class AuthenticationError(GDriveToGCSError):
    """Raised when authentication fails or credentials are missing."""


class DriveAPIError(GDriveToGCSError):
    """Raised when a Google Drive API call fails."""


class GCSUploadError(GDriveToGCSError):
    """Raised when a GCS upload operation fails."""


class PathNotFoundError(GDriveToGCSError):
    """Raised when a Drive path cannot be resolved."""
