"""Purchase acknowledgement: Asana task plus quote PDFs."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.core.limits import RateLimit
from app.core.log import clean, logger, public_error
from app.integrations import asana, sharepoint
from app.integrations.salesforce import DOCUMENT_KINDS, retrieve_documents
from app.schemas import CreatedPurchaseTask, Email
from app.services.purchase import extract_purchase

router = APIRouter()
limit = RateLimit("purchase", 30)


@router.post("/purchase-acknowledge", dependencies=[Depends(limit)])
@router.post("/purchase-acknowledgement", dependencies=[Depends(limit)])
async def purchase_acknowledge(email: Email) -> CreatedPurchaseTask:
    try:
        task = extract_purchase(email)
    except ValueError as exc:
        logger.info("purchase-acknowledge rejected: %s", clean(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info("purchase-acknowledge %s %s", task.quote_number, clean(task.task_name))
    created, documents = await asyncio.gather(
        asyncio.to_thread(asana.create_task, task),
        retrieve_documents(task.quote_number, verbose=True),
        return_exceptions=True,
    )
    if isinstance(documents, Exception):
        message = public_error(documents, "Salesforce document retrieval failed")
        documents = {
            "status": "error",
            "error_message": message,
            "documents": {
                kind: {"status": "error", "error_message": message}
                for kind in DOCUMENT_KINDS
            },
        }
    else:
        parts = " ".join(
            f"{kind}={item.get('status')}"
            for kind, item in (documents.get("documents") or {}).items()
        )
        error = documents.get("error_message") or ""
        logger.info(
            "purchase-acknowledge %s documents=%s %s %s",
            task.quote_number, documents.get("status"), parts, clean(error),
        )
    documents["sharepoint"] = await _upload(documents)
    if isinstance(created, Exception):
        status = created.status if isinstance(created, asana.AsanaError) else 502
        raise HTTPException(
            status_code=status,
            detail={"error": public_error(created, "Asana task creation failed"), "documents": documents},
        )
    return CreatedPurchaseTask(
        **task.model_dump(),
        asana_gid=created.gid,
        asana_url=created.url,
        documents=documents,
    )


async def _upload(documents: dict) -> dict:
    """Copy the downloaded PDFs to SharePoint. Never fails the request: report the outcome."""
    files = documents.get("files") or []
    customer = documents.get("account_name") or ""
    if not sharepoint.configured():
        return {"status": "skipped", "reason": "SharePoint is not configured"}
    if not files or not customer:
        return {"status": "skipped", "reason": "no files or no account name"}
    try:
        result = await asyncio.to_thread(sharepoint.upload_deal_documents, customer, files)
    except Exception as exc:  # noqa: BLE001 - report, don't lose the Asana task
        return {"status": "error", "error_message": public_error(exc, "SharePoint upload failed")}
    return {"status": "uploaded", **result}
