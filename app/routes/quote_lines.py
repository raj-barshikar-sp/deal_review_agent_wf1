"""Quote lines plus a stamped report screenshot."""

import base64
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.core.limits import RateLimit
from app.core.log import public_error
from app.integrations import sharepoint
from app.integrations.salesforce import fetch_quote_lines
from app.integrations.salesforce.screenshot import capture
from app.integrations.salesforce.screenshot.remote import capture_remote, remote_url
from app.schemas import Quote, QuoteLinesResult
from app.services import drs

router = APIRouter()
limit = RateLimit("quote_lines", 6)

# One headless Chrome at a time. Others wait this long, then get a 503.
_browser_lock = threading.Lock()
BROWSER_WAIT_SECONDS = 120


@router.post("/quote-lines-drs", dependencies=[Depends(limit)])
def quote_lines_drs(quote: Quote) -> QuoteLinesResult:
    try:
        records = fetch_quote_lines(quote.quote_number)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail=public_error(exc, "Salesforce quote lines failed")
        ) from exc
    # With a separate screenshot service, that service does the queuing.
    if not remote_url() and not _browser_lock.acquire(timeout=BROWSER_WAIT_SECONDS):
        raise HTTPException(status_code=503, detail="screenshot service is busy, try again shortly")
    try:
        shot = (capture_remote if remote_url() else capture)(quote.quote_number)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": public_error(exc, "Screenshot failed"),
                "quote_number": quote.quote_number,
                "record_count": len(records),
                "records": records,
            },
        ) from exc
    finally:
        if not remote_url():
            _browser_lock.release()
    png = Path(shot["path"]).read_bytes()
    return QuoteLinesResult(
        quote_number=quote.quote_number,
        record_count=len(records),
        records=records,
        screenshot_taken_at=shot["taken_at"],
        screenshot_path=shot["path"],
        screenshot_png_base64=base64.b64encode(png).decode(),
        page_url=shot["page_url"],
        drs=_publish_drs(records, png, shot["page_url"]),
    )


def _publish_drs(records: list, png: bytes, report_url: str) -> dict:
    """Create or update the DRS in SharePoint. Never fails the request: report the outcome."""
    if not sharepoint.configured():
        return {"status": "skipped", "reason": "SharePoint is not configured"}
    if not records:
        return {"status": "skipped", "reason": "quote has no lines"}
    try:
        return drs.publish(records, png, report_url)
    except Exception as exc:  # noqa: BLE001 - the lines and screenshot are still returned
        return {"status": "error", "error_message": public_error(exc, "DRS update failed")}
