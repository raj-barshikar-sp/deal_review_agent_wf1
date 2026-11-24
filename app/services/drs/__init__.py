"""Deal Review Sheet: create it once in SharePoint, then update its SF Quote Extract tab."""

import re
from datetime import date

from app.core.log import logger
from app.integrations import sharepoint
from app.integrations.sharepoint.client import list_children, download, root_segments, upload_file
from app.integrations.sharepoint.layout import clean_name

from .build import build
from .patch import DrsPatchError, patch
from .sheet import account_name, order_start

__all__ = ["DrsPatchError", "build", "patch", "publish"]


def _find_existing(customer: str, start: date) -> tuple[list[str], dict] | None:
    """The customer's DRS for this order-start month, in any of their New Deals month folders."""
    new_deals = [*root_segments(), clean_name(customer), "New Deals"]
    pattern = re.compile(
        rf"^DRS - .+ - {re.escape(clean_name(customer))} \({start.month:02d}\.{start.year}\)\.xlsx$", re.I
    )
    for month in sorted((f for f in list_children(new_deals) if "folder" in f), key=lambda f: f["name"], reverse=True):
        for item in list_children([*new_deals, month["name"]]):
            if "file" in item and pattern.match(item["name"]):
                return [*new_deals, month["name"]], item
    return None


def publish(records: list, png: bytes, report_url: str = "", today: date | None = None) -> dict:
    today = today or date.today()
    customer = account_name(records)
    start = order_start(records)
    if not customer or not start:
        raise ValueError("quote lines have no account name or effective start date")
    found = _find_existing(customer, start)
    if found:
        segments, item = found
        content = patch(download(item), records, png)
        url = upload_file(segments, item["name"], content)
        logger.info("drs updated %s", item["name"])
        return {"status": "updated", "file": item["name"], "folder": "/".join(segments), "url": url}
    segments = sharepoint.folder_segments("/".join(root_segments()), customer, today)
    sharepoint.ensure_folder(segments, existing=len(root_segments()))
    name = sharepoint.drs_name(today, customer, start)
    url = upload_file(segments, name, build(records, png, report_url))
    logger.info("drs created %s", name)
    return {"status": "created", "file": name, "folder": "/".join(segments), "url": url}
