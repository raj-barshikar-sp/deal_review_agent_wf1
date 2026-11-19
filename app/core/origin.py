"""Same-origin guard: the API answers only the page it serves itself."""

import os
import urllib.parse

from starlette.requests import Request
from starlette.responses import JSONResponse

MAX_BODY_BYTES = 256 * 1024
SAFE_METHODS = {"GET", "HEAD"}
# Comma-separated; http://localhost:8080 is always allowed for `gcloud run services proxy`.
TRUSTED_ORIGINS = ["http://localhost:8080", "http://127.0.0.1:8080"] + [
    o.strip().rstrip("/") for o in os.environ.get("FRONTEND_ORIGIN", "").split(",") if o.strip()
]


def _deny(status: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status)


async def same_origin_only(request: Request, call_next):
    """Reject browser requests that come from another site, and oversized bodies.

    Non-browser callers (curl, Power Automate) send no Origin header and are not
    affected here; they are covered by the authentication layer.
    """
    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    trusted = origin is not None and origin.rstrip("/") in TRUSTED_ORIGINS
    if origin is not None and not trusted and urllib.parse.urlsplit(origin).netloc != host:
        return _deny(403, "cross-origin requests are not allowed")
    site = request.headers.get("sec-fetch-site")
    mode = request.headers.get("sec-fetch-mode")
    if site == "cross-site" and mode != "navigate" and not trusted:
        return _deny(403, "cross-site requests are not allowed")
    if request.method not in SAFE_METHODS:
        try:
            length = int(request.headers.get("content-length") or 0)
        except ValueError:
            return _deny(400, "invalid content-length")
        if length > MAX_BODY_BYTES:
            return _deny(413, "request body too large")
    return await call_next(request)
