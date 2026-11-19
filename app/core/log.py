"""Logging helpers: levelled output and sanitised, opaque error details."""

import logging
import os
import re
import uuid

logger = logging.getLogger("dra")

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def configure() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    logger.setLevel(level)


def clean(value, limit: int = 300) -> str:
    """One line, no control characters, so user text cannot forge log entries."""
    text = _CONTROL.sub(" ", str(value)).strip()
    return text if len(text) <= limit else text[:limit] + "..."


def public_error(exc: BaseException, label: str) -> str:
    """Log the real error with a reference; hand the caller only the reference."""
    ref = uuid.uuid4().hex[:8]
    logger.error("%s ref=%s: %s", label, ref, clean(exc, 2000))
    return f"{label} (ref {ref})"
