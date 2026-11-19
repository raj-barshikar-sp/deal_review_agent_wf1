"""Capture the stamped Quote Lines screenshot for one quote."""

import shutil
import tempfile
import time
import urllib.parse
from datetime import datetime

from selenium.webdriver.support.ui import WebDriverWait

from app.config import SCREENSHOT_DIR
from app.core.limits import prune_old_files
from app.core.log import clean, logger

from .browser import start_chrome, wait_for_report
from .imaging import stamp
from .report import report_page_url
from .session import frontdoor_url, lightning_origin, web_token


def _log_shot(taken_at, quote, path, page_url, rows):
    line = f"{taken_at} {quote} {path} {page_url} rows={rows}"
    logger.info("screenshot %s", clean(line, 600))
    with (SCREENSHOT_DIR / "screenshot.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _redact(message, token):
    if not token:
        return message
    return message.replace(token, "[token]").replace(urllib.parse.quote(token, safe=""), "[token]")


def _proof_url(current, requested):
    """URL a reviewer can open. Never the frontdoor link, which carries the session."""
    parts = urllib.parse.urlsplit(current or "")
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() != "sid"
    ]
    cleaned = urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), "")
    )
    if "/lightning/r/Report/" in cleaned:
        return cleaned
    return requested or cleaned


def _save_error_shot(driver, quote):
    if driver is None:
        return ""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / ("quote-lines-" + quote + "-error.png")
    try:
        driver.save_screenshot(str(path))
    except Exception:
        return ""
    return str(path)


def capture(quote):
    """Open the quote's report through frontdoor and return the stamped PNG path."""
    token, instance = web_token()
    page_url, is_report = report_page_url(quote, instance, token)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    prune_old_files(SCREENSHOT_DIR)
    profile = tempfile.mkdtemp(prefix="dra-chrome-")
    driver = None
    try:
        driver = start_chrome(profile)
        driver.set_page_load_timeout(60)
        if is_report:
            driver.set_window_size(2500, 2800)
        logger.info("salesforce frontdoor %s -> %s", instance, lightning_origin(instance))
        driver.get(frontdoor_url(instance, token, page_url))
        if is_report:
            rows = wait_for_report(driver)
        else:
            WebDriverWait(driver, 45).until(
                lambda browser: browser.execute_script("return document.readyState") == "complete"
            )
            time.sleep(3)
            rows = 0
        taken_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        png = driver.get_screenshot_as_png()
        landed = _proof_url(driver.current_url, page_url)
    except Exception as exc:
        debug = _save_error_shot(driver, quote)
        # Full detail stays in the server log; callers get a short message.
        logger.error("screenshot failed: %s debug=%s", clean(_redact(str(exc), token), 2000), debug)
        raise RuntimeError("Screenshot capture failed") from exc
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            shutil.rmtree(profile, ignore_errors=True)
    safe_time = taken_at.replace(" ", "T").replace(":", "").replace("+", "")
    path = SCREENSHOT_DIR / ("quote-lines-" + quote + "-" + safe_time + ".png")
    path.write_bytes(png)
    stamp(path, taken_at, landed)
    _log_shot(taken_at, quote, str(path), landed, rows)
    return {
        "path": str(path),
        "taken_at": taken_at,
        "page_url": landed,
    }
