"""Front-end page and file downloads."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import STATIC_DIR
from app.services.files import shared_file

router = APIRouter()


@router.get("/")
def front_end() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/files")
def files(path: str) -> FileResponse:
    target = shared_file(path)
    if target is None:
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target)
