"""Purchase acknowledgement: Asana task plus quote PDFs."""

import asyncio

from fastapi import APIRouter, HTTPException

from app.integrations import asana
from app.integrations.salesforce import DOCUMENT_KINDS, retrieve_documents
from app.schemas import CreatedPurchaseTask, Email
from app.services.purchase import extract_purchase

router = APIRouter()


@router.post("/purchase-acknowledge")
@router.post("/purchase-acknowledgement")
async def purchase_acknowledge(email: Email) -> CreatedPurchaseTask:
    try:
        task = extract_purchase(email)
    except ValueError as exc:
        print(f"purchase-acknowledge rejected: {exc}", flush=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    print(f"purchase-acknowledge {task.quote_number} {task.task_name}", flush=True)
    created, documents = await asyncio.gather(
        asyncio.to_thread(asana.create_task, task),
        retrieve_documents(task.quote_number, verbose=True),
        return_exceptions=True,
    )
    if isinstance(documents, Exception):
        print(f"purchase-acknowledge documents failed: {documents}", flush=True)
        documents = {
            "status": "error",
            "error_message": str(documents),
            "documents": {
                kind: {"status": "error", "error_message": str(documents)}
                for kind in DOCUMENT_KINDS
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
