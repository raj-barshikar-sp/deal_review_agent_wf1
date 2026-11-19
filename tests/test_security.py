"""Same-origin guard, file serving limits, input limits, rate limiting, cleanup."""

import asyncio
import json
import os
import time

from app.core.limits import RateLimit, prune_old_files
from app.core.log import clean
from app.main import app
from app.schemas import Email, Quote
from app.services.files import shared_file


def call(method, path, headers=None, body=b"", query=b""):
    """Drive the ASGI app directly and return (status, response headers, body)."""
    raw_headers = [(b"host", b"testserver")] + [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    if body:
        raw_headers.append((b"content-length", str(len(body)).encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "path": path, "raw_path": path.encode(), "query_string": query,
        "headers": raw_headers, "scheme": "http", "server": ("testserver", 80),
        "client": ("127.0.0.1", 1), "root_path": "",
    }
    sent = []
    delivered = []

    async def receive():
        if not delivered:
            delivered.append(True)
            return {"type": "http.request", "body": body, "more_body": False}
        while not any(m["type"] == "http.response.body" and not m.get("more_body") for m in sent):
            await asyncio.sleep(0.01)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(asyncio.wait_for(app(scope, receive, send), timeout=10))
    start = next(m for m in sent if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), payload


def post_json(path, data, headers=None):
    all_headers = {"content-type": "application/json", **(headers or {})}
    return call("POST", path, all_headers, json.dumps(data).encode())


def test_cross_origin_post_is_refused():
    status, _, _ = post_json("/quote-lines-drs", {"quote_number": "Q-123456"}, {"origin": "https://evil.example"})
    assert status == 403


def test_cross_site_fetch_is_refused_but_navigation_is_not():
    assert call("GET", "/", {"sec-fetch-site": "cross-site", "sec-fetch-mode": "cors"})[0] == 403
    assert call("GET", "/", {"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate"})[0] == 200


def test_same_origin_request_reaches_validation():
    status, _, _ = post_json("/quote-lines-drs", {"quote_number": "bad"}, {"origin": "http://testserver"})
    assert status == 422


def test_oversized_body_is_refused():
    status, _, _ = call("POST", "/purchase-acknowledge", {"content-type": "application/json"}, b"x" * 300_000)
    assert status == 413


def test_front_end_has_no_sniff_and_no_framing():
    status, headers, _ = call("GET", "/")
    assert status == 200
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"


def test_files_serves_only_pdf_and_png(tmp_path, monkeypatch):
    import app.services.files as files

    monkeypatch.setattr(files, "FILE_ROOTS", (tmp_path.resolve(),))
    for name in ("a.pdf", "b.PNG", "Cookies", "screenshot.log", "Login Data"):
        (tmp_path / name).write_bytes(b"x")
    assert shared_file(str(tmp_path / "a.pdf")) is not None
    assert shared_file(str(tmp_path / "b.PNG")) is not None
    assert shared_file(str(tmp_path / "Cookies")) is None
    assert shared_file(str(tmp_path / "screenshot.log")) is None
    assert shared_file(str(tmp_path / "Login Data")) is None
    assert shared_file(str(tmp_path / ".." / "a.pdf")) is None


def test_input_length_and_ascii_digits():
    for bad in ({"subject": "s" * 301, "body": "b"}, {"subject": "s", "body": "b" * 50_001}):
        try:
            Email(**bad)
        except ValueError:
            continue
        raise AssertionError("expected a length error")
    for bad in ("Q-12345", "Q-١٢٣٤٥٦"):
        try:
            Quote(quote_number=bad)
        except ValueError:
            continue
        raise AssertionError("expected a format error")
    assert Quote(quote_number="Q-123456").quote_number == "Q-123456"


def test_rate_limit_blocks_after_the_limit():
    limiter = RateLimit("test_route", 2)
    limiter()
    limiter()
    try:
        limiter()
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 429
    else:
        raise AssertionError("expected 429")


def test_prune_removes_only_old_generated_files(tmp_path, monkeypatch):
    monkeypatch.setenv("RETENTION_DAYS", "1")
    old_pdf, old_log, new_pdf = tmp_path / "old.pdf", tmp_path / "old.log", tmp_path / "new.pdf"
    for item in (old_pdf, old_log, new_pdf):
        item.write_bytes(b"x")
    stale = time.time() - 3 * 86400
    for item in (old_pdf, old_log):
        os.utime(item, (stale, stale))
    prune_old_files(tmp_path)
    assert not old_pdf.exists()
    assert old_log.exists()
    assert new_pdf.exists()


def test_log_text_cannot_forge_lines():
    assert "\n" not in clean("subject\nFAKE LOG LINE\r\n")
