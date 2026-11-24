"""Where the screenshot sits and how big it is drawn."""

from .sheet import FIRST_ROW

MAX_WIDTH_PX = 1600
EMU_PER_PX = 9525


def anchor_row(line_count: int) -> int:
    """Zero-based row for the image: one blank row below the last quote line."""
    return FIRST_ROW - 1 + max(line_count, 1) + 1


def display_size(width: int, height: int) -> tuple[int, int]:
    scale = min(1.0, MAX_WIDTH_PX / width) if width else 1.0
    return round(width * scale), round(height * scale)
