"""Open the Salesforce Quote Lines report and stamp the capture time on the image."""

import json
import os
import shutil
import tempfile
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

import salesforce

SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"
REPORT_NAME = "Quote Lines"
RUBY_ORIGIN = "https://ruby-data-8243.lightning.force.com"
_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def report_page_url(quote):
    """Page to screenshot, and the title to wait for (None for the home page).

    Until a report is chosen, this is the Salesforce home page. Set
    SALESFORCE_SCREENSHOT_URL, SALESFORCE_QUOTE_LINES_REPORT_ID, or
    SALESFORCE_QUOTE_LINES_REPORT_NAME to point it at a report instead.
    """
    explicit = os.environ.get("SALESFORCE_SCREENSHOT_URL", "").strip()
    if explicit:
        return explicit.format(quote=urllib.parse.quote(quote)), None
    report_id = os.environ.get("SALESFORCE_QUOTE_LINES_REPORT_ID", "").strip()
    name = os.environ.get("SALESFORCE_QUOTE_LINES_REPORT_NAME", "").strip()
    if not report_id and name:
        rows = salesforce.rest_query(
            "SELECT Id FROM Report WHERE Name = " + salesforce.soql_literal(name) + " LIMIT 2"
        )
        if len(rows) != 1:
            raise RuntimeError(f"Expected one Salesforce report named {name!r}, found {len(rows)}.")
        report_id = str(rows[0].get("Id") or rows[0].get("id") or "")
        if not report_id:
            raise RuntimeError(f"Salesforce report {name!r} has no Id.")
    if report_id:
        url = (
            RUBY_ORIGIN
            + "/lightning/r/Report/"
            + urllib.parse.quote(report_id, safe="")
            + "/view?fv0="
            + urllib.parse.quote(quote)
        )
        return url, REPORT_NAME
    return RUBY_ORIGIN + "/lightning/page/home", None


def cookie_list():
    path = os.environ.get("SALESFORCE_COOKIES_FILE", "").strip()
    raw = os.environ.get("SALESFORCE_COOKIES_JSON", "").strip()
    if path:
        file = Path(path)
        if not file.is_file():
            raise RuntimeError("SALESFORCE_COOKIES_FILE does not exist: " + path)
        raw = file.read_text()
    if not raw:
        return []
    cookies = json.loads(raw)
    if not isinstance(cookies, list):
        raise RuntimeError("Salesforce cookies must be a JSON list.")
    return cookies


def cookie_domain(value):
    text = str(value or "").strip()
    if "://" in text:
        text = urllib.parse.urlsplit(text).hostname or ""
    return text.strip(".")


def _selenium_cookie(raw):
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    value = raw.get("value")
    if not name or value is None:
        return None
    item = {"name": str(name), "value": str(value), "path": raw.get("path") or "/"}
    domain = cookie_domain(raw.get("domain"))
    if domain:
        item["domain"] = domain
    if raw.get("secure") is not None:
        item["secure"] = bool(raw["secure"])
    if raw.get("httpOnly") is not None:
        item["httpOnly"] = bool(raw["httpOnly"])
    expiry = raw.get("expiry", raw.get("expirationDate"))
    if isinstance(expiry, (int, float)):
        item["expiry"] = int(expiry)
    same = raw.get("sameSite")
    mapped = {"strict": "Strict", "lax": "Lax", "none": "None"}.get(str(same).lower()) if same else None
    if mapped:
        item["sameSite"] = mapped
    return item


def apply_cookies(driver, cookies):
    loaded = 0
    failed = 0
    for raw in cookies:
        item = _selenium_cookie(raw)
        if item is None:
            failed += 1
            continue
        try:
            driver.add_cookie(item)
            loaded += 1
        except Exception:
            print("cookie rejected " + item["name"], flush=True)
            failed += 1
    return loaded, failed


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


def _font(size):
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def stamp(path, taken_at):
    """Draw the capture time in a bar above the screenshot."""
    image = Image.open(path).convert("RGB")
    font = _font(22)
    bar = 40
    canvas = Image.new("RGB", (image.width, image.height + bar), (17, 17, 17))
    canvas.paste(image, (0, bar))
    ImageDraw.Draw(canvas).text((12, 8), "Screenshot taken " + taken_at, fill=(255, 255, 255), font=font)
    canvas.save(path, format="PNG")


def _log_shot(taken_at, quote, path, page_url):
    line = f"{taken_at} {quote} {path} {page_url}"
    print("screenshot " + line, flush=True)
    with (SCREENSHOT_DIR / "screenshot.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def capture(quote):
    """Open Report: Quote Lines and return the stamped PNG path plus the capture time."""
    page_url, expected_title = report_page_url(quote)
    cookies = cookie_list()
    if not cookies:
        raise RuntimeError(
            "Set SALESFORCE_COOKIES_JSON or SALESFORCE_COOKIES_FILE so Chrome opens a signed-in Salesforce session."
        )
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="dra-chrome-")
    driver = None
    try:
        driver = start_chrome(profile)
        driver.set_page_load_timeout(60)
        origin = urllib.parse.urlsplit(page_url)
        driver.get(origin.scheme + "://" + origin.netloc + "/")
        loaded, failed = apply_cookies(driver, cookies)
        driver.get(page_url)
        if expected_title:
            WebDriverWait(driver, 45).until(lambda browser: expected_title in (browser.title or ""))
        else:
            WebDriverWait(driver, 45).until(
                lambda browser: browser.execute_script("return document.readyState") == "complete"
            )
        # shortcut: Lightning paints content after readyState. A fixed pause covers it.
        time.sleep(3)
        taken_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        png = driver.get_screenshot_as_png()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Salesforce page did not open. " + str(exc)) from exc
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
    _log_shot(taken_at, quote, str(path), page_url)
    return {
        "path": str(path),
        "taken_at": taken_at,
        "cookies_loaded": loaded,
        "cookies_failed": failed,
        "page_url": page_url,
    }


def _self_check():
    assert cookie_domain("https://ruby-data-8243.lightning.force.com") == "ruby-data-8243.lightning.force.com"
    assert report_page_url("Q-127182")[0].startswith(RUBY_ORIGIN)
