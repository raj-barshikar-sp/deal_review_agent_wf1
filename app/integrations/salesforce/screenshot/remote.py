"""Take the screenshot on the separate screenshot service instead of locally."""

import base64
import json
import os
import urllib.error
import urllib.request

from app.config import SCREENSHOT_DIR
from app.core.limits import prune_old_files

TIMEOUT_SECONDS = 280


def remote_url() -> str:
    return os.environ.get("SCREENSHOT_SERVICE_URL", "").strip().rstrip("/")


def capture_remote(quote):
    """Same result as capture(), with the PNG saved here so /files can serve it."""
    request = urllib.request.Request(
        remote_url() + "/screenshot",
        data=json.dumps({"quote_number": quote}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + os.environ.get("SCREENSHOT_SERVICE_TOKEN", ""),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("Screenshot service failed") from exc
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    prune_old_files(SCREENSHOT_DIR)
    safe_time = data["taken_at"].replace(" ", "T").replace(":", "").replace("+", "")
    path = SCREENSHOT_DIR / ("quote-lines-" + quote + "-" + safe_time + ".png")
    path.write_bytes(base64.b64decode(data["png_base64"]))
    return {"path": str(path), "taken_at": data["taken_at"], "page_url": data["page_url"]}
