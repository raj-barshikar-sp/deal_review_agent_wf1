"""Quote lines plus a stamped report screenshot."""

import threading

from fastapi import APIRouter, HTTPException

from app.integrations.salesforce import fetch_quote_lines
from app.integrations.salesforce.screenshot import capture
from app.schemas import Quote, QuoteLinesResult

router = APIRouter()

# One headless Chrome at a time.
_browser_lock = threading.Lock()


@router.post("/quote-lines-drs")
def quote_lines_drs(quote: Quote) -> QuoteLinesResult:
    try:
        records = fetch_quote_lines(quote.quote_number)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        with _browser_lock:
            shot = capture(quote.quote_number)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": str(exc),
                "quote_number": quote.quote_number,
                "record_count": len(records),
                "records": records,
            },
        ) from exc
    return QuoteLinesResult(
        quote_number=quote.quote_number,
        record_count=len(records),
        records=records,
        screenshot_taken_at=shot["taken_at"],
        screenshot_path=shot["path"],
        page_url=shot["page_url"],
    )
