"""Render the front end in headless Chrome with stubbed API replies and save screenshots.

Usage: python -m scripts.ui_preview [out_dir]
Shows each pane before the call, mid-flight (animation), and after the reply.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

from app.config import STATIC_DIR
from app.integrations.salesforce.screenshot.browser import start_chrome

ACK_REPLY = {
    "task_name": "Fidelity Investments", "quote_number": "Q-127182", "description": "Signed quote Q-127182.",
    "delivery_date": "2026-11-24", "period": "Nov 2026", "asana_gid": "1", "asana_url": "https://app.asana.com/x",
    "documents": {
        "status": "partial",
        "documents": {
            "purchase_order": {"status": "found", "title": "Purchase Order BPO2384-R1", "path": "/a.pdf"},
            "fully_executed_quote": {"status": "found", "title": "Q-127182-7 FE", "path": "/b.pdf"},
            "transaction_approval_form": {"status": "missing"},
            "master_agreement": {"status": "missing"},
        },
        "sharepoint": {
            "status": "uploaded", "folder": "TEST - New Deal Review Agent/Fidelity Investments/New Deals/2026.11 November",
            "folder_url": "https://sailpoint.sharepoint.com/folder",
            "files": {"Q-127182 Purchase Order.pdf": "https://sailpoint.sharepoint.com/a", "Q-127182 FE.pdf": "https://sailpoint.sharepoint.com/b"},
        },
    },
}
QUOTE_REPLY = {
    "quote_number": "Q-127182", "record_count": 5, "records": [{"Name": "QL-1"}] * 5, "screenshot_path": "/s.png",
    "screenshot_taken_at": "2026-11-24 19:13:41 +0530", "screenshot_png_base64": "",
    "drs": {"status": "updated", "file": "DRS - 11.24.2026 - Fidelity Investments (03.2026).xlsx", "url": "https://sailpoint.sharepoint.com/drs"},
}
QUOTE_FAILED = {"detail": {"error": "Screenshot failed (ref abc)", "quote_number": "Q-127182", "record_count": 5, "records": [{"Name": "QL-1"}] * 5}}


def stub(reply, ok=True, delay_ms=6000):
    return (
        "window.fetch = () => new Promise((resolve) => setTimeout(() => resolve({ ok: %s, json: async () => (%s) }), %d));"
        % (str(ok).lower(), json.dumps(reply), delay_ms)
    )


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="dra-ui-")
    driver = start_chrome(profile)
    try:
        driver.set_window_size(1400, 800)
        for name, button, reply, ok in (
            ("ack", "ack-button", ACK_REPLY, True),
            ("quote", "quote-button", QUOTE_REPLY, True),
            ("quote-failed", "quote-button", QUOTE_FAILED, False),
        ):
            driver.get((STATIC_DIR / "index.html").as_uri())
            driver.execute_script(stub(reply, ok))
            driver.save_screenshot(str(out / f"{name}-1-before.png"))
            driver.execute_script(f"document.getElementById('{button}').click()")
            time.sleep(3.2)
            driver.save_screenshot(str(out / f"{name}-2-running.png"))
            time.sleep(6.5)
            driver.save_screenshot(str(out / f"{name}-3-done.png"))
        print("saved to", out)
    finally:
        driver.quit()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ui-preview"))
