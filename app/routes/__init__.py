"""HTTP routes."""

from fastapi import APIRouter

from . import asana, pages, purchase, quote_lines

router = APIRouter()
for module in (pages, asana, purchase, quote_lines):
    router.include_router(module.router)
