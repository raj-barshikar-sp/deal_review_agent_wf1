"""Headless Chrome control and waiting for the report to render."""

import os
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .page_scripts import (
    DISMISS_POPUPS_JS,
    REPORT_BOTTOM_JS,
    REPORT_COLUMNS_JS,
    REPORT_OVERFLOW_JS,
    REPORT_READY_JS,
    REPORT_TOTAL_JS,
)


def chrome_options(profile):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--user-data-dir=" + profile)
    binary = os.environ.get("CHROME_BIN", "").strip()
    if binary:
        options.binary_location = binary
    return options


def start_chrome(profile):
    options = chrome_options(profile)
    driver_path = os.environ.get("CHROMEDRIVER", "").strip()
    if driver_path:
        return webdriver.Chrome(service=Service(executable_path=driver_path), options=options)
    return webdriver.Chrome(options=options)


def _blocked(driver):
    url = driver.current_url or ""
    if "/_ui/identity/verification" in url or "EmailVerification" in url:
        raise RuntimeError(
            "Salesforce asked for an identity verification code. "
            "The screenshot login must be the JWT bearer token with the web scope."
        )
    return url


def _run_in_report_frame(driver, js):
    """Run js in the document that holds the report. Returns (result, frame_top_px)."""
    driver.switch_to.default_content()
    for frame in [None] + driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            top = 0
            if frame is not None:
                top = driver.execute_script(
                    "return arguments[0].getBoundingClientRect().top + window.scrollY",
                    frame,
                )
                driver.switch_to.frame(frame)
            if driver.execute_script(REPORT_READY_JS):
                return driver.execute_script(js), top
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()
    return None, 0


EXPECTED_COLUMNS = 16  # NDT - Quote Lines report, Quote Number through Currency


def _require_columns(driver, max_width=6000):
    """Widen the window until every report column is on screen; fail rather than save a cropped shot."""
    seen = {}
    for _ in range(6):
        seen = _run_in_report_frame(driver, REPORT_COLUMNS_JS)[0] or {}
        if seen.get("total", 0) >= EXPECTED_COLUMNS and seen.get("visible", 0) >= seen["total"]:
            return seen["total"]
        size = driver.get_window_size()
        if size["width"] >= max_width:
            break
        driver.set_window_size(min(size["width"] + 300, max_width), size["height"])
        time.sleep(2)
    raise RuntimeError(
        f"Only {seen.get('visible', 0)} of {seen.get('total', 0)} report columns visible "
        f"(expected {EXPECTED_COLUMNS}); not saving a cropped screenshot."
    )


def _fit_width(driver, max_width=6000):
    """Widen the window until no report column or the filter panel is cut off on the right."""
    for _ in range(4):
        overflow = _run_in_report_frame(driver, REPORT_OVERFLOW_JS)[0] or 0
        size = driver.get_window_size()
        if overflow <= 2 or size["width"] >= max_width:
            return
        driver.set_window_size(min(size["width"] + int(overflow) + 40, max_width), size["height"])
        time.sleep(2)


def wait_for_report(driver):
    """Wait until the Total Records tile exists and the table has stopped moving, then trim the window."""
    try:
        WebDriverWait(driver, 30).until(lambda browser: "lightning" in _blocked(browser))
        WebDriverWait(driver, 60).until(lambda browser: _run_in_report_frame(browser, "return true")[0])
    except TimeoutException as exc:
        raise RuntimeError(
            "The Quote Lines report never rendered. Check Run Reports, the report folder share, "
            "and that the integration user can read the report's object. Stuck at "
            + (driver.current_url or "")
        ) from exc
    time.sleep(6)
    bottom, frame_top, previous = None, 0, -1
    for _ in range(30):
        bottom, frame_top = _run_in_report_frame(driver, REPORT_BOTTOM_JS)
        if bottom and bottom == previous:
            break
        previous = bottom
        time.sleep(1)
    rows = _run_in_report_frame(driver, REPORT_TOTAL_JS)[0] or 0
    if bottom:
        browser_chrome = driver.execute_script("return window.outerHeight - window.innerHeight") or 0
        driver.set_window_size(2500, max(int(bottom + frame_top) + 260 + browser_chrome, 700 + browser_chrome))
        time.sleep(2)
    try:
        driver.execute_script(DISMISS_POPUPS_JS)
        time.sleep(1)
    except Exception:
        pass
    _fit_width(driver)
    _require_columns(driver)
    return rows
