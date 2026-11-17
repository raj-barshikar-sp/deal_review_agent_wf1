"""Paths and server settings shared across the app."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENV_PATH = ROOT / ".env"
DOWNLOAD_DIR = ROOT / "downloaded_docs"
SCREENSHOT_DIR = ROOT / "screenshots"
DEFAULT_JWT_KEY_FILE = ROOT / "certs" / "sf-jwt.key"
STATIC_DIR = Path(__file__).resolve().parent / "static"

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))
# Pages on other origins may call this API only if listed here (comma separated).
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
    ).split(",")
    if origin.strip()
]
