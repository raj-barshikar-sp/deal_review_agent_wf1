"""Where documents go in SharePoint and what the DRS file is called. Pure functions."""

import re
from datetime import date

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_BAD = re.compile(r'[\x00-\x1f"*:<>?/\\|#%~]+')


def clean_name(value: str) -> str:
    """Safe SharePoint file/folder name: no reserved characters, no trailing dot/space."""
    name = _BAD.sub(" ", value or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        raise ValueError("empty SharePoint name")
    return name[:120]


def month_folder(today: date) -> str:
    """'2026.04 April'"""
    return f"{today.year}.{today.month:02d} {MONTH_NAMES[today.month - 1]}"


def folder_segments(root: str, customer: str, today: date) -> list[str]:
    """<root...> / <customer> / New Deals / <YYYY.MM Month>"""
    base = [clean_name(part) for part in root.replace("\\", "/").split("/") if part.strip()]
    return [*base, clean_name(customer), "New Deals", month_folder(today)]


def drs_name(today: date, customer: str, order_start: date, extension: str = "xlsx") -> str:
    """'DRS - 4.07.2026 - Acme Corp (03.2026).xlsx'  (M.DD.YYYY, MM.YYYY)"""
    return (
        f"DRS - {today.month}.{today.day:02d}.{today.year} - {clean_name(customer)} "
        f"({order_start.month:02d}.{order_start.year}).{extension}"
    )
