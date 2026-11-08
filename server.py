"""Listener for purchase-acknowledgement emails and quote-line requests."""

import asyncio
import re
import threading
from datetime import date
from pathlib import Path

import asana
import get_quote_lines
import salesforce
import screenshot
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ValidationError, field_validator

HOST = "127.0.0.1"
PORT = 8000
PA_SUFFIX = " - Purchase Acknowledgement for SailPoint Offerings"
QUOTE_IN_BODY = re.compile(r"\bQ-\d{6}\b")
QUOTE_EXACT = re.compile(r"^Q-\d{6}$")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

app = FastAPI()
FRONT_END = Path(__file__).resolve().parent / "front-end"
FILE_ROOTS = (
    Path(salesforce.DOWNLOAD_DIR).resolve(),
    Path(screenshot.SCREENSHOT_DIR).resolve(),
)


def shared_file(path: str) -> Path | None:
    """Return a downloaded PDF or screenshot, and nothing outside those folders."""
    try:
        target = Path(path).expanduser().resolve()
    except OSError:
        return None
    if not target.is_file():
        return None
    if any(target == root or root in target.parents for root in FILE_ROOTS):
        return target
    return None


class Email(BaseModel):
    subject: str
    body: str

    @field_validator("subject", "body")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty text")
        return value


class PurchaseTask(BaseModel):
    task_name: str
    description: str
    delivery_date: date
    period: str
    quote_number: str


class CreatedPurchaseTask(PurchaseTask):
    asana_gid: str
    asana_url: str
    documents: dict


class Quote(BaseModel):
    quote_number: str

    @field_validator("quote_number")
    @classmethod
    def matches(cls, value: str) -> str:
        if QUOTE_EXACT.fullmatch(value) is None:
            raise ValueError("must match Q-XXXXXX")
        return value


class QuoteLinesResult(BaseModel):
    quote_number: str
    record_count: int
    records: list
    screenshot_taken_at: str
    screenshot_path: str
    page_url: str


_browser_lock = threading.Lock()


def extract_purchase(email: Email, created_on: date | None = None) -> PurchaseTask:
    subject = email.subject.strip()
    if not subject.endswith(PA_SUFFIX):
        raise ValueError(f"subject must end with {PA_SUFFIX!r}")
    task_name = subject[: -len(PA_SUFFIX)].strip()
    if not task_name:
        raise ValueError("subject has no task name")

    quotes = list(dict.fromkeys(QUOTE_IN_BODY.findall(email.body)))
    if len(quotes) != 1:
        raise ValueError("body must contain exactly one quote number matching Q-XXXXXX")

    created = created_on or date.today()
    return PurchaseTask(
        task_name=task_name,
        description=email.body,
        delivery_date=created,
        period=f"{MONTHS[created.month - 1]} {created.year}",
        quote_number=quotes[0],
    )


@app.get("/")
def front_end() -> FileResponse:
    return FileResponse(FRONT_END / "index.html")


@app.get("/files")
def files(path: str) -> FileResponse:
    target = shared_file(path)
    if target is None:
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target)


@app.get("/asana/authorize")
def asana_authorize() -> RedirectResponse:
    try:
        return RedirectResponse(asana.authorization_url())
    except asana.AsanaError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.get("/asana/callback")
def asana_callback(code: str = "", state: str = "", error: str = "") -> dict:
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code or state")
    try:
        asana.exchange_code(code, state)
    except asana.AsanaError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"connected": True}


@app.post("/purchase-acknowledge")
@app.post("/purchase-acknowledgement")
async def purchase_acknowledge(email: Email) -> CreatedPurchaseTask:
    try:
        task = extract_purchase(email)
    except ValueError as exc:
        print(f"purchase-acknowledge rejected: {exc}", flush=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    print(f"purchase-acknowledge {task.quote_number} {task.task_name}", flush=True)
    created, documents = await asyncio.gather(
        asyncio.to_thread(asana.create_task, task),
        salesforce.retrieve_documents(task.quote_number, verbose=True),
        return_exceptions=True,
    )
    if isinstance(documents, Exception):
        print(f"purchase-acknowledge documents failed: {documents}", flush=True)
        documents = {
            "status": "error",
            "error_message": str(documents),
            "documents": {
                kind: {"status": "error", "error_message": str(documents)}
                for kind in salesforce.DOCUMENT_KINDS
            },
        }
    else:
        parts = " ".join(
            f"{kind}={item.get('status')}"
            for kind, item in (documents.get("documents") or {}).items()
        )
        error = documents.get("error_message") or ""
        print(
            f"purchase-acknowledge {task.quote_number} documents={documents.get('status')} {parts} {error}".rstrip(),
            flush=True,
        )
    if isinstance(created, Exception):
        status = created.status if isinstance(created, asana.AsanaError) else 502
        raise HTTPException(
            status_code=status,
            detail={"error": str(created), "documents": documents},
        )
    return CreatedPurchaseTask(
        **task.model_dump(),
        asana_gid=created.gid,
        asana_url=created.url,
        documents=documents,
    )


@app.post("/quote-lines-drs")
def quote_lines_drs(quote: Quote) -> QuoteLinesResult:
    try:
        records = get_quote_lines.fetch_quote_lines(quote.quote_number)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        with _browser_lock:
            shot = screenshot.capture(quote.quote_number)
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


def _self_check() -> None:
    created = date(2026, 11, 7)
    task = extract_purchase(
        Email(
            subject="Fidelity Investments - Purchase Acknowledgement for SailPoint Offerings",
            body="Signed quote Q-123456 is attached.",
        ),
        created_on=created,
    )
    assert task.task_name == "Fidelity Investments"
    assert task.description == "Signed quote Q-123456 is attached."
    assert task.delivery_date == created
    assert task.period == "Nov 2026"
    assert task.quote_number == "Q-123456"
    repeated = extract_purchase(
        Email(
            subject="Acme - Purchase Acknowledgement for SailPoint Offerings",
            body="Q-123456 then Q-123456",
        ),
        created_on=created,
    )
    assert repeated.quote_number == "Q-123456"
    for subject, body in (
        ("Hello", "Quote Q-123456"),
        (" - Purchase Acknowledgement for SailPoint Offerings", "Quote Q-123456"),
        ("Acme - Purchase Acknowledgement for SailPoint Offerings", "no quote here"),
        ("Acme - Purchase Acknowledgement for SailPoint Offerings", "Q-123456 and Q-654321"),
        ("Acme - Purchase Acknowledgement for SailPoint Offerings", "Q-1234567"),
    ):
        try:
            extract_purchase(Email(subject=subject, body=body), created_on=created)
        except ValueError:
            continue
        raise AssertionError(f"accepted {subject!r} / {body!r}")
    asana._self_check()
    salesforce._self_check()
    get_quote_lines._self_check()
    screenshot._self_check()
    assert shared_file("/etc/passwd") is None
    assert shared_file(str(FRONT_END / "index.html")) is None
    Quote(quote_number="Q-123456")
    try:
        Quote(quote_number="Q-12")
    except ValidationError:
        return
    raise AssertionError("bad quote was accepted")


if __name__ == "__main__":
    _self_check()
    uvicorn.run(app, host=HOST, port=PORT)
