"""Check the Quote Lines capture is not cropped, then take a real stamped screenshot.

Usage: python -m scripts.screenshot_probe Q-127182
"""

import shutil
import sys
import tempfile

from PIL import Image

from app.integrations.salesforce.screenshot import capture
from app.integrations.salesforce.screenshot.browser import _run_in_report_frame, start_chrome, wait_for_report
from app.integrations.salesforce.screenshot.page_scripts import _DEEP_QUERY_JS, REPORT_COLUMNS_JS, REPORT_OVERFLOW_JS
from app.integrations.salesforce.screenshot.report import report_page_url
from app.integrations.salesforce.screenshot.session import frontdoor_url, web_token

LAYOUT_JS = _DEEP_QUERY_JS + """
const tables = deepQuery(document, 'table').map(t => Math.round(t.getBoundingClientRect().right));
const panel = deepQuery(document, 'button').find(b => (b.getAttribute('title') || '') === 'Close Filter Panel');
const shown = panel && panel.getBoundingClientRect().width > 0;
return {viewport: window.innerWidth, table_right: Math.max(...tables),
        filter_panel: shown ? 'visible at x=' + Math.round(panel.getBoundingClientRect().right) : 'NOT visible'};
"""


def probe(quote):
    token, instance = web_token()
    page, _ = report_page_url(quote, instance, token)
    profile = tempfile.mkdtemp(prefix="dra-probe-")
    driver = start_chrome(profile)
    try:
        driver.set_window_size(2500, 2800)
        driver.get(frontdoor_url(instance, token, page))
        wait_for_report(driver)
        layout = _run_in_report_frame(driver, LAYOUT_JS)[0]
        overflow = _run_in_report_frame(driver, REPORT_OVERFLOW_JS)[0]
        print("window:", driver.get_window_size())
        print("layout:", layout)
        print("hidden px on the right:", overflow, "->", "OK" if overflow <= 2 else "STILL CROPPED")
        columns = _run_in_report_frame(driver, REPORT_COLUMNS_JS)[0]
        print("columns:", columns, "->", "OK" if columns["total"] >= 16 and columns["visible"] == columns["total"] else "MISSING COLUMNS")
        return overflow <= 2 and columns["visible"] == columns["total"] >= 16
    finally:
        driver.quit()
        shutil.rmtree(profile, ignore_errors=True)


def main(quote):
    fits = probe(quote)
    shot = capture(quote)
    print("screenshot:", shot["path"], Image.open(shot["path"]).size)
    raise SystemExit(0 if fits else 1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Q-127182")
