"""Screenshot service endpoint. Called by the front-end service, not by browsers."""

import base64
import hmac
import os
import threading
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

from app.core.log import public_error
from app.integrations.salesforce.screenshot import capture
from app.schemas import Quote

router = APIRouter()

# One headless Chrome at a time. Others wait this long, then get a 503.
_browser_lock = threading.Lock()
BROWSER_WAIT_SECONDS = 120


def _check_token(authorization: str) -> None:
    expected = os.environ.get("SCREENSHOT_SERVICE_TOKEN", "").strip()
    given = authorization.removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/screenshot")
def screenshot(quote: Quote, authorization: str = Header(default="")) -> dict:
    _check_token(authorization)
    if not _browser_lock.acquire(timeout=BROWSER_WAIT_SECONDS):
        raise HTTPException(status_code=503, detail="screenshot service is busy, try again shortly")
    try:
        shot = capture(quote.quote_number)
        png = Path(shot["path"]).read_bytes()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail=public_error(exc, "Screenshot failed")
        ) from exc
    finally:
        _browser_lock.release()
    return {
        "taken_at": shot["taken_at"],
        "page_url": shot["page_url"],
        "png_base64": base64.b64encode(png).decode(),
    }
