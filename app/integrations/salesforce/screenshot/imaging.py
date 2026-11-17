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


def stamp(path, taken_at):
    """Draw the capture time in a bar above the screenshot."""
    image = Image.open(path).convert("RGB")
    font = _font(22)
    bar = 40
    canvas = Image.new("RGB", (image.width, image.height + bar), (17, 17, 17))
    canvas.paste(image, (0, bar))
    ImageDraw.Draw(canvas).text((12, 8), "Screenshot taken " + taken_at, fill=(255, 255, 255), font=font)
    canvas.save(path, format="PNG")
