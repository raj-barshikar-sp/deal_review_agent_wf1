"""Append Salesforce error responses to <project root>/error-logs.txt.

Secrets (tokens, client secrets) are never written; only the URL, status, content type and a
truncated response body.
"""

import re
import threading
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parents[3] / "error-logs.txt"
MAX_BODY = 5000
_lock = threading.Lock()
_SECRET = re.compile(r"(access_token|client_secret|refresh_token|sid)(\"?\s*[:=]\s*\"?)[^\"&\s,}]+", re.I)


def _redact(text):
    return _SECRET.sub(lambda m: m.group(1) + m.group(2) + "***", text)


def log_salesforce_error(context, url, status=None, content_type="", body=b""):
    if isinstance(body, bytes):
        body = body[:MAX_BODY].decode(errors="replace")
    body = _redact(str(body)[:MAX_BODY])
    url = _redact(str(url))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"[{stamp}] {context}",
        f"  url: {url}",
        f"  status: {status}",
        f"  content-type: {content_type}",
        "  body:",
        *("    " + line for line in (body.splitlines() or [""])),
        "",
    ]
    try:
        with _lock, LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        pass  # logging must never break retrieval
