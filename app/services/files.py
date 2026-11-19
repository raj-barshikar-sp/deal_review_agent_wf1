"""Which local files the API may hand back to a caller."""

from pathlib import Path

from app.config import DOWNLOAD_DIR, SCREENSHOT_DIR

FILE_ROOTS = (DOWNLOAD_DIR.resolve(), SCREENSHOT_DIR.resolve())
# Only what the app itself produces. Never browser profiles, logs, or databases.
ALLOWED_SUFFIXES = {".pdf", ".png"}


def shared_file(path: str) -> Path | None:
    """Return a downloaded PDF or screenshot, and nothing outside those folders."""
    try:
        target = Path(path).expanduser().resolve()
    except (OSError, ValueError):
        return None
    if target.suffix.lower() not in ALLOWED_SUFFIXES:
        return None
    if not target.is_file():
        return None
    if any(root in target.parents for root in FILE_ROOTS):
        return target
    return None
