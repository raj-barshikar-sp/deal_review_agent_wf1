"""Run the new screenshot login and capture against the org in .env.

Usage: .venv/bin/python test_salesforce_ss_test.py
"""

import os
import sys
from pathlib import Path

import screenshot

QUOTE = os.environ.get("SCREENSHOT_TEST_QUOTE", "Q-100231")


def main():
    token, instance = screenshot._web_token()
    kind = "jwt" if token.startswith("ey") else "opaque"
    print(f"token minted host={instance} type={kind}", flush=True)
    page, is_report = screenshot.report_page_url(QUOTE, instance, token)
    print(f"report is_report={is_report} url={page.split('?')[0]}", flush=True)
    shot = screenshot.capture(QUOTE)
    path = Path(shot["path"])
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG"):
        raise RuntimeError(f"screenshot is not a PNG: {path}")
    if len(data) < 10000:
        raise RuntimeError(f"screenshot looks empty ({len(data)} bytes): {path}")
    print(
        f"ok {path} {len(data)} bytes taken_at={shot['taken_at']} page={shot['page_url']}",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAIL " + str(exc), file=sys.stderr)
        raise SystemExit(1)
