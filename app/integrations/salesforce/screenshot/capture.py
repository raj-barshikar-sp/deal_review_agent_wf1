"""Capture the stamped Quote Lines screenshot for one quote."""

import shutil
import tempfile
import time
import urllib.parse
from datetime import datetime

from selenium.webdriver.support.ui import WebDriverWait

from app.config import SCREENSHOT_DIR

from .browser import start_chrome, wait_for_report
from .imaging import stamp
from .report import report_page_url
from .session import frontdoor_url, lightning_origin, web_token


def _log_shot(taken_at, quote, path, page_url, rows):
    line = f"{taken_at} {quote} {path} {page_url} rows={rows}"
    print("screenshot " + line, flush=True)
    with (SCREENSHOT_DIR / "screenshot.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _redact(message, token):
    if not token:
        return message
    return message.replace(token, "[token]").replace(urllib.parse.quote(token, safe=""), "[token]")


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
    profile = tempfile.mkdtemp(prefix="dra-chrome-")
    driver = None
    try:
        driver = start_chrome(profile)
        driver.set_page_load_timeout(60)
        if is_report:
            driver.set_window_size(2500, 2800)
        print("salesforce frontdoor " + instance + " -> " + lightning_origin(instance), flush=True)
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
        landed = driver.current_url.split("?")[0]
    except Exception as exc:
        debug = _save_error_shot(driver, quote)
        message = _redact(str(exc), token)
        if debug:
            message += " Debug screenshot: " + debug + "."
        raise RuntimeError(message) from exc
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            shutil.rmtree(profile, ignore_errors=True)
    safe_time = taken_at.replace(" ", "T").replace(":", "").replace("+", "")
    path = SCREENSHOT_DIR / ("quote-lines-" + quote + "-" + safe_time + ".png")
    path.write_bytes(png)
    stamp(path, taken_at)
    _log_shot(taken_at, quote, str(path), landed, rows)
    return {
        "path": str(path),
        "taken_at": taken_at,
        "page_url": landed,
    }
