"""Request rate limiting and clean-up of old generated files."""

import os
import threading
import time
from pathlib import Path

from fastapi import HTTPException

RETENTION_SUFFIXES = {".pdf", ".png"}


class RateLimit:
    """Sliding-window limit shared by every caller of one route."""

    def __init__(self, name: str, default_per_minute: int):
        self.name = name
        self.per_minute = int(os.environ.get(f"RATE_LIMIT_{name.upper()}", default_per_minute))
        self._hits: list[float] = []
        self._lock = threading.Lock()

    def __call__(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._hits = [stamp for stamp in self._hits if now - stamp < 60]
            if self.per_minute > 0 and len(self._hits) >= self.per_minute:
                raise HTTPException(status_code=429, detail="too many requests, try again shortly")
            self._hits.append(now)


def prune_old_files(folder: Path) -> None:
    """Delete generated PDFs/PNGs older than RETENTION_DAYS (0 turns this off)."""
    days = float(os.environ.get("RETENTION_DAYS", "14"))
    if days <= 0 or not folder.is_dir():
        return
    cutoff = time.time() - days * 86400
    for item in folder.iterdir():
        try:
            if item.is_file() and item.suffix.lower() in RETENTION_SUFFIXES and item.stat().st_mtime < cutoff:
                item.unlink()
        except OSError:
            continue
