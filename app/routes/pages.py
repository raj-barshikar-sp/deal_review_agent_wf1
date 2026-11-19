"""Front-end page and file downloads."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import STATIC_DIR
from app.services.files import shared_file

router = APIRouter()

NO_SNIFF = {"X-Content-Type-Options": "nosniff"}


@router.get("/")
def front_end() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={**NO_SNIFF, "X-Frame-Options": "DENY"},
    )


@router.get("/files")
def files(path: str) -> FileResponse:
    target = shared_file(path)
    if target is None:
        raise HTTPException(status_code=404, detail="file not found")
    # Inline so the page can preview it; nosniff stops the browser guessing a type.
    return FileResponse(target, headers=NO_SNIFF)
