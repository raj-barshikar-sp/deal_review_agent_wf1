"""Find the Finance drive, create folders idempotently, upload files."""

import json
import threading
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from app.core.env import setting
from app.core.log import logger

from . import graph
from .graph import SharePointError, fail
from .layout import folder_segments

SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024
CHUNK = 32 * 320 * 1024  # Graph needs multiples of 320 KiB

_lock = threading.Lock()
_drive_id = ""


def root_path() -> str:
    """No default on purpose: a missing value must never silently write to the live Finance folders."""
    value = setting("SHAREPOINT_ROOT_PATH")
    if not value:
        raise SharePointError("Set SHAREPOINT_ROOT_PATH (test: 'TEST - New Deal Review Agent')", 500)
    return value


def root_segments() -> list[str]:
    return [p for p in root_path().replace("\\", "/").split("/") if p.strip()]


def _quote_path(segments) -> str:
    return "/".join(urllib.parse.quote(s, safe="") for s in segments)


def drive_id() -> str:
    """SHAREPOINT_SITE is 'host/sites/Name', e.g. sailpoint.sharepoint.com/sites/Finance."""
    global _drive_id
    with _lock:
        if _drive_id:
            return _drive_id
    site = graph.site_setting().strip().removeprefix("https://").strip("/")
    host, _, path = site.partition("/")
    status, body = graph.request("GET", f"/sites/{host}:/{path}")
    if status >= 400 or not body:
        raise fail("Finance site lookup", status, body)
    status, drives = graph.request("GET", f"/sites/{body['id']}/drives")
    if status >= 400 or not drives:
        raise fail("Finance drive lookup", status, drives)
    wanted = (setting("SHAREPOINT_DRIVE_NAME") or "Documents").lower()
    for drive in drives.get("value", []):
        if drive.get("name", "").lower() == wanted:
            with _lock:
                _drive_id = drive["id"]
            return _drive_id
    raise SharePointError(f"Drive {wanted!r} not found on the site", 500)


def ensure_folder(segments: list[str], existing: int = 0) -> str:
    """Create missing folders below the first `existing` segments (the pre-made root, which the
    app may only be granted access to as a whole); return the webUrl of the last folder."""
    drive = drive_id()
    web_url = ""
    for depth in range(max(existing, 1), len(segments) + 1):
        path = _quote_path(segments[:depth])
        status, item = graph.request("GET", f"/drives/{drive}/root:/{path}")
        if status == 404:
            parent = _quote_path(segments[: depth - 1])
            children = f"/drives/{drive}/root:/{parent}:/children" if parent else f"/drives/{drive}/root/children"
            status, item = graph.request(
                "POST",
                children,
                json_body={"name": segments[depth - 1], "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
            )
            if status == 409:  # created by a concurrent run
                status, item = graph.request("GET", f"/drives/{drive}/root:/{path}")
            else:
                logger.info("sharepoint folder created: %s", "/".join(segments[:depth]))
        if status >= 400 or not item:
            raise fail(f"Folder {'/'.join(segments[:depth])!r}", status, item)
        if "folder" not in item:
            raise SharePointError(f"{'/'.join(segments[:depth])!r} exists but is not a folder")
        web_url = item.get("webUrl", "")
    return web_url


def upload_file(segments: list[str], name: str, data: bytes) -> str:
    """Upload (replacing any same-named file, so re-runs are safe). Returns the file webUrl."""
    drive = drive_id()
    target = _quote_path([*segments, name])
    if len(data) <= SIMPLE_UPLOAD_LIMIT:
        status, item = graph.request(
            "PUT",
            f"/drives/{drive}/root:/{target}:/content?@microsoft.graph.conflictBehavior=replace",
            data=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        if status >= 400 or not item:
            raise fail(f"Upload {name!r}", status, item)
        return item.get("webUrl", "")
    status, session = graph.request(
        "POST",
        f"/drives/{drive}/root:/{target}:/createUploadSession",
        json_body={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
    )
    if status >= 400 or not session:
        raise fail(f"Upload session {name!r}", status, session)
    url, total, item = session["uploadUrl"], len(data), None
    for start in range(0, total, CHUNK):
        part = data[start : start + CHUNK]
        # The upload URL is pre-authorised; sending our bearer token to it is rejected.
        req = urllib.request.Request(
            url,
            data=part,
            method="PUT",
            headers={"Content-Range": f"bytes {start}-{start + len(part) - 1}/{total}"},
        )
        status, raw = graph._send(req, timeout=120)
        if status >= 400:
            raise fail(f"Upload chunk {name!r}", status, None)
        if status in (200, 201):
            item = json.loads(raw.decode())
    return (item or {}).get("webUrl", "")


def list_children(segments: list[str]) -> list[dict]:
    """Items directly in a folder; [] if the folder does not exist."""
    url = f"/drives/{drive_id()}/root:/{_quote_path(segments)}:/children?$top=200"
    items = []
    while url:
        status, body = graph.request("GET", url)
        if status == 404:
            return []
        if status >= 400 or not body:
            raise fail(f"List {'/'.join(segments)!r}", status, body)
        items.extend(body.get("value", []))
        url = body.get("@odata.nextLink", "")
    return items


def download(item: dict) -> bytes:
    """File content via its pre-authorised download URL (no bearer token)."""
    url = item.get("@microsoft.graph.downloadUrl")
    if not url:
        status, item = graph.request("GET", f"/drives/{drive_id()}/items/{item['id']}")
        url = (item or {}).get("@microsoft.graph.downloadUrl")
        if status >= 400 or not url:
            raise fail("Download URL", status, item)
    status, raw = graph._send(urllib.request.Request(url), timeout=300)
    if status >= 400:
        raise fail("Download", status, None)
    return raw


def upload_deal_documents(customer: str, files: list[str], today: date | None = None) -> dict:
    """Put each local file in <root>/<customer>/New Deals/<YYYY.MM Month>/."""
    segments = folder_segments(root_path(), customer, today or date.today())
    folder_url = ensure_folder(segments, existing=len(root_segments()))
    uploaded = {}
    for path in files:
        file = Path(path)
        uploaded[file.name] = upload_file(segments, file.name, file.read_bytes())
        logger.info("sharepoint uploaded %s", file.name)
    return {"folder": "/".join(segments), "folder_url": folder_url, "files": uploaded}
