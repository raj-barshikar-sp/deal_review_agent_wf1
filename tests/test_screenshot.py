from PIL import Image, ImageDraw

from app.integrations.salesforce.screenshot.capture import _proof_url
from app.integrations.salesforce.screenshot.imaging import _font, _wrap

REPORT = "https://org.lightning.force.com/lightning/r/Report/00Oxx/view?fv0=Q-127182"


def test_proof_url_keeps_report_and_drops_session():
    analytics = "https://org.lightning.force.com/lightning/page/analytics"
    assert _proof_url(analytics, REPORT) == REPORT
    assert _proof_url(REPORT + "&sid=SECRET", REPORT) == REPORT


def test_wrap_splits_long_url_without_loss():
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = _wrap(draw, "abcdefghijklmnop", _font(18), 1)
    assert len(lines) > 1
    assert "".join(lines) == "abcdefghijklmnop"
