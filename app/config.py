"""Paths and server settings shared across the app."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENV_PATH = ROOT / ".env"
DOWNLOAD_DIR = ROOT / "downloaded_docs"
SCREENSHOT_DIR = ROOT / "screenshots"
DEFAULT_JWT_KEY_FILE = ROOT / "certs" / "sf-jwt.key"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Containers set HOST=0.0.0.0; local runs stay on loopback.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
