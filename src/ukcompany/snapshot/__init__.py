"""Lazy access to the Companies House Free Company Data Product."""

from .download import LANDING_PAGE_URL, SnapshotDownloadError, discover_parts, download_snapshot
from .loader import COLUMNS, SnapshotLoader
from .manifest import create_manifest, load_manifest

__all__ = [
    "COLUMNS",
    "LANDING_PAGE_URL",
    "SnapshotDownloadError",
    "SnapshotLoader",
    "create_manifest",
    "discover_parts",
    "download_snapshot",
    "load_manifest",
]
