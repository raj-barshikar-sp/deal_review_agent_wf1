"""Open the Salesforce Quote Lines report through a JWT web session and stamp the capture time."""

import json
import os
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import salesforce

SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"
DEFAULT_KEY_FILE = Path(__file__).resolve().parent / "certs" / "sf-jwt.key"
REPORT_DEVELOPER_NAME = "Quote_Lines"
_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
# Lightning hides the report in shadow DOM and sometimes an iframe.
_DEEP_QUERY_JS = """
function deepQuery(root, selector, out) {
  out = out || [];
  for (const n of root.querySelectorAll(selector)) out.push(n);
  for (const el of root.querySelectorAll('*')) {
    if (el.shadowRoot) deepQuery(el.shadowRoot, selector, out);
  }
  return out;
}
"""
_TOTAL_RECORDS_TILE_JS = (
    "const tile = deepQuery(document, '*').find(e => e.children.length === 0 "
    "&& (e.textContent || '').trim() === 'Total Records');"
)
REPORT_READY_JS = _DEEP_QUERY_JS + _TOTAL_RECORDS_TILE_JS + "return !!tile;"
REPORT_TOTAL_JS = _DEEP_QUERY_JS + _TOTAL_RECORDS_TILE_JS + r"""
if (!tile || !tile.parentElement) return null;
const m = tile.parentElement.innerText.match(/Total Records\s*([\d,]+)/);
return m ? parseInt(m[1].replace(/,/g, ''), 10) : null;
"""
REPORT_BOTTOM_JS = _DEEP_QUERY_JS + """
const tables = deepQuery(document, 'table');
if (!tables.length) return null;
return Math.ceil(Math.max(...tables.map(t => t.getBoundingClientRect().bottom)) + window.scrollY);
"""
DISMISS_POPUPS_JS = _DEEP_QUERY_JS + """
for (const b of deepQuery(document, 'button', [])) {
  const label = ((b.getAttribute('title') || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + b.innerText).toLowerCase();
  let inPrompt = false;
  for (let n = b; n; n = n.parentNode || n.host) {
    if (n.nodeType === 1 && n.matches && n.matches('.forceInAppGuidance, .prompt, .docked-composer, section[role=dialog]')) inPrompt = true;
  }
  if (inPrompt && /close|dismiss|minimize/.test(label)) b.click();
}
"""


def lightning_origin(instance):
    """Lightning host for the org that issued the access token.

    https://sailpoint--full.sandbox.my.salesforce.com
    becomes https://sailpoint--full.sandbox.lightning.force.com
    """
    parts = urllib.parse.urlsplit(instance)
    host = parts.netloc
    suffix = ".my.salesforce.com"
    if host.endswith(suffix):
        host = host[: -len(suffix)] + ".lightning.force.com"
    return "https://" + host


def _jwt_audiences(domain, explicit=""):
    """Hosts Salesforce accepts as the JWT audience. Sandboxes use test.salesforce.com."""
    if explicit:
        return [explicit]
    host = urllib.parse.urlsplit(domain).netloc
    first = "https://test.salesforce.com" if ".sandbox." in host else "https://login.salesforce.com"
    audiences = []
    for item in (first, "https://login.salesforce.com", "https://test.salesforce.com", domain.rstrip("/")):
        if item not in audiences:
            audiences.append(item)
    return audiences


def _private_key():
    pem = os.environ.get("SALESFORCE_JWT_PRIVATE_KEY", "").strip()
    if pem:
        return pem.replace("\\n", "\n")
    key_file = Path(os.environ.get("SALESFORCE_JWT_KEY_FILE", "").strip() or DEFAULT_KEY_FILE)
    if key_file.is_file():
        return key_file.read_text()
    return ""


def _screenshot_login():
    """My Domain, consumer key, integration username, and the JWT private key."""
    salesforce.load_env()
    domain = (
        os.environ.get("SALESFORCE_MY_DOMAIN_URL", "").strip()
        or os.environ.get("SALESFORCE_INSTANCE_URL", "").strip()
    ).rstrip("/")
    client_id = (
        os.environ.get("SALESFORCE_JWT_CLIENT_ID", "").strip()
        or os.environ.get("SALESFORCE_CLIENT_ID", "").strip()
    )
    username = os.environ.get("SALESFORCE_USERNAME", "").strip()
    key = _private_key()
    missing = []
    if not domain.startswith("https://"):
        missing.append("SALESFORCE_MY_DOMAIN_URL or SALESFORCE_INSTANCE_URL")
    if not client_id:
        missing.append("SALESFORCE_JWT_CLIENT_ID or SALESFORCE_CLIENT_ID")
    if not username:
        missing.append("SALESFORCE_USERNAME")
    if not key:
        missing.append("SALESFORCE_JWT_PRIVATE_KEY, SALESFORCE_JWT_KEY_FILE, or certs/sf-jwt.key")
    if missing:
        raise RuntimeError("Screenshot login is missing " + ", ".join(missing) + ".")
    return domain, client_id, username, key


def _web_token():
    """Mint a web-scoped token for the integration user. Client credentials cannot open frontdoor."""
    domain, client_id, username, private_key = _screenshot_login()
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("Install PyJWT[crypto] to sign the Salesforce screenshot login.") from exc
    explicit = os.environ.get("SALESFORCE_JWT_AUDIENCE", "").strip()
    last_error = ""
    for audience in _jwt_audiences(domain, explicit):
        assertion = jwt.encode(
            {"iss": client_id, "sub": username, "aud": audience, "exp": int(time.time()) + 180},
            private_key,
            algorithm="RS256",
        )
        try:
            body = salesforce._form_post(
                domain + "/services/oauth2/token",
                {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            )
            break
        except RuntimeError as exc:
            last_error = str(exc)
            if "invalid assertion" not in last_error.lower() and "audience" not in last_error.lower():
                raise
    else:
        raise RuntimeError(
            "Salesforce rejected the screenshot JWT (" + last_error + "). "
            "Check the uploaded certificate, the Consumer Key, and that SALESFORCE_USERNAME "
            "is exactly the integration user's username."
        )
    token = str(body.get("access_token") or "")
    if not token:
        raise RuntimeError("Salesforce token response did not include an access token.")
    return token, str(body.get("instance_url") or domain).rstrip("/")


def _query(instance, token, soql):
    version = os.environ.get("SALESFORCE_API_VERSION", "v66.0").strip() or "v66.0"
    url = instance + "/services/data/" + version + "/query?q=" + urllib.parse.quote(soql)
    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    raw, status, _content_type = salesforce._read(request)
    if status >= 400:
        raise RuntimeError(f"Salesforce report lookup failed ({status}): {raw.decode(errors='replace')[:300]}")
    body = json.loads(raw.decode())
    if isinstance(body, list):
        message = "; ".join(item.get("message", str(item)) for item in body if isinstance(item, dict))
        raise RuntimeError("Salesforce report lookup failed: " + (message or str(body)))
    return body.get("records") or []


def _report_id(instance, token, field, value):
    rows = _query(
        instance,
        token,
        "SELECT Id FROM Report WHERE " + field + " = " + salesforce.soql_literal(value) + " LIMIT 2",
    )
    if len(rows) != 1:
        raise RuntimeError(f"Expected one Salesforce report with {field} {value!r}, found {len(rows)}.")
    report_id = str(rows[0].get("Id") or rows[0].get("id") or "")
    if not report_id:
        raise RuntimeError(f"Salesforce report {value!r} has no Id.")
    return report_id


def report_page_url(quote, instance, token):
    """Report page for this quote. fv0 applies only when Quote Number is the report's first filter."""
    origin = lightning_origin(instance)
    explicit = os.environ.get("SALESFORCE_SCREENSHOT_URL", "").strip()
    if explicit:
        url = explicit.format(quote=urllib.parse.quote(quote))
        return url, "/lightning/r/Report/" in url
    report_id = os.environ.get("SALESFORCE_QUOTE_LINES_REPORT_ID", "").strip()
    if not report_id:
        name = os.environ.get("SALESFORCE_QUOTE_LINES_REPORT_NAME", "").strip()
        if name:
            report_id = _report_id(instance, token, "Name", name)
        else:
            report_id = _report_id(instance, token, "DeveloperName", REPORT_DEVELOPER_NAME)
    url = (
        origin
        + "/lightning/r/Report/"
        + urllib.parse.quote(report_id, safe="")
        + "/view?fv0="
        + urllib.parse.quote(quote)
    )
    return url, True


def _ret_path(page_url):
    """Path Salesforce should open after frontdoor accepts the access token."""
    parts = urllib.parse.urlsplit(page_url)
    if not parts.path:
        return "/lightning/page/home"
    return parts.path + (("?" + parts.query) if parts.query else "")


def frontdoor_url(instance, token, ret_url):
    """Log in on the org that issued the token, then open ret_url."""
    return instance.rstrip("/") + "/secur/frontdoor.jsp?" + urllib.parse.urlencode({
        "sid": token,
        "retURL": ret_url,
    })


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


def _log_shot(taken_at, quote, path, page_url, rows):
    line = f"{taken_at} {quote} {path} {page_url} rows={rows}"
    print("screenshot " + line, flush=True)
    with (SCREENSHOT_DIR / "screenshot.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _redact(message, token):
    if not token:
        return message
    return message.replace(token, "[token]").replace(urllib.parse.quote(token, safe=""), "[token]")


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


def _wait_for_report(driver):
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
    return rows


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
    token, instance = _web_token()
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
            rows = _wait_for_report(driver)
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


def _self_check():
    sandbox = "https://sailpoint--full.sandbox.my.salesforce.com"
    developer = "https://mydomain.develop.my.salesforce.com"
    assert lightning_origin(sandbox) == "https://sailpoint--full.sandbox.lightning.force.com"
    assert _ret_path(sandbox + "/lightning/page/home") == "/lightning/page/home"
    assert _jwt_audiences(sandbox)[0] == "https://test.salesforce.com"
    assert _jwt_audiences(developer)[0] == "https://login.salesforce.com"
    assert _jwt_audiences(developer, explicit="https://login.salesforce.com") == ["https://login.salesforce.com"]
    assert "https://login.salesforce.com" in _jwt_audiences(sandbox)
    assert _jwt_audiences(sandbox)[-1] == sandbox
