"""HTTP routes. SERVICE_ROLE picks which ones this deployment serves."""

import os

from fastapi import APIRouter

from . import asana, pages, purchase, quote_lines, screenshot

ROLES = {
    "frontend": (pages, asana, purchase, quote_lines),
    "screenshot": (screenshot,),
    "all": (pages, asana, purchase, quote_lines, screenshot),
}

router = APIRouter()
for module in ROLES[os.environ.get("SERVICE_ROLE", "all")]:
    router.include_router(module.router)
