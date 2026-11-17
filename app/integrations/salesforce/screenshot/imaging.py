"""Stamp the capture time onto a screenshot."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def _font(size):
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw, text, font, width):
    lines, rest = [], text
    while rest:
        if draw.textlength(rest, font=font) <= width:
            lines.append(rest)
            break
        cut = len(rest)
        while cut > 1 and draw.textlength(rest[:cut], font=font) > width:
            cut -= 1
        lines.append(rest[:cut])
        rest = rest[cut:]
    return lines or [""]


def stamp(path, taken_at, page_url):
    """Draw the capture time and the page URL in a bar above the screenshot."""
    image = Image.open(path).convert("RGB")
    title_font, url_font = _font(22), _font(18)
    draw = ImageDraw.Draw(image)
    url_lines = _wrap(draw, page_url, url_font, image.width - 24)
    bar = 46 + 26 * len(url_lines)
    canvas = Image.new("RGB", (image.width, image.height + bar), (17, 17, 17))
    canvas.paste(image, (0, bar))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 8), "Screenshot taken " + taken_at, fill=(255, 255, 255), font=title_font)
    for index, line in enumerate(url_lines):
        draw.text((12, 40 + 26 * index), line, fill=(255, 255, 255), font=url_font)
    canvas.save(path, format="PNG")
