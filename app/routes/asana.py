"""Asana OAuth endpoints."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.integrations import asana

router = APIRouter(prefix="/asana")


@router.get("/authorize")
def asana_authorize() -> RedirectResponse:
    try:
        return RedirectResponse(asana.authorization_url())
    except asana.AsanaError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/callback")
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
