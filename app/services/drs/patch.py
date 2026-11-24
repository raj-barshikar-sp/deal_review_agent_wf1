"""Update the SF Quote Extract tab inside an existing DRS workbook.

The workbook is edited as a zip package: only the tab's XML, its screenshot and the
workbook calc flag change; every other part is copied as-is. Analysts add NetSuite
extracts of 100+ MB to this file, which openpyxl cannot load quickly or save losslessly.
"""

import io
import posixpath
import re
import zipfile
from xml.sax.saxutils import escape

from PIL import Image as PILImage

from .image import EMU_PER_PX, anchor_row, display_size
from .sheet import FIRST_ROW, LAST_COL, SHEET, excel_serial, rows

_CELL = re.compile(r"<c\b[^>]*?(?:/>|>.*?</c>)", re.S)
_ROW = re.compile(r"<row\b([^>]*?)(?:/>|>(.*?)</row>)", re.S)


class DrsPatchError(ValueError):
    pass


def _rels(package: zipfile.ZipFile, part: str) -> dict[str, str]:
    """rId -> absolute part name for the relationships of `part`."""
    folder, name = posixpath.split(part)
    rels_name = posixpath.join(folder, "_rels", name + ".rels")
    if rels_name not in package.namelist():
        return {}
    xml = package.read(rels_name).decode()
    out = {}
    for rel in re.finditer(r"<Relationship\b[^>]*>", xml):
        tag = rel.group(0)
        rid = re.search(r'Id="([^"]+)"', tag).group(1)
        target = re.search(r'Target="([^"]+)"', tag).group(1)
        if 'TargetMode="External"' in tag:
            continue
        out[rid] = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
    return out


def _sheet_part(package: zipfile.ZipFile) -> str:
    workbook = package.read("xl/workbook.xml").decode()
    for tag in re.findall(r"<sheet\b[^>]*>", workbook):
        name = re.search(r'name="([^"]*)"', tag).group(1)
        if name.replace("&amp;", "&") == SHEET:
            rid = re.search(r'r:id="([^"]+)"', tag).group(1)
            return _rels(package, "xl/workbook.xml")[rid]
    raise DrsPatchError(f"workbook has no {SHEET!r} tab")


def _col(ref: str) -> str:
    return re.match(r"[A-Z]+", ref).group(0)


def _col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def _cell_xml(ref: str, value, kind: str, style: str) -> str:
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>'
    if kind == "date":
        return f'<c r="{ref}"{s}><v>{excel_serial(value)}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{s}><v>{value!r}</v></c>'
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'


def _patch_sheet(xml: str, data) -> str:
    match = re.search(r"<sheetData\s*/>|<sheetData>(.*?)</sheetData>", xml, re.S)
    if not match:
        raise DrsPatchError("tab has no sheetData")
    existing: dict[int, tuple[str, list[str]]] = {}
    for row in _ROW.finditer(match.group(1) or ""):
        number = int(re.search(r'\br="(\d+)"', row.group(1)).group(1))
        existing[number] = (row.group(1), _CELL.findall(row.group(2) or ""))
    # Column styles from the first data row, so dates and money keep their formats.
    styles = {}
    for cell in existing.get(FIRST_ROW, ("", []))[1]:
        found = re.search(r'\bs="(\d+)"', cell)
        styles[_col(re.search(r'\br="([A-Z]+\d+)"', cell).group(1))] = found.group(1) if found else ""
    last_col = _col_index(LAST_COL)
    new_rows = {}
    for number, (attrs, cells) in existing.items():
        if number < FIRST_ROW:
            new_rows[number] = (attrs, cells)
            continue
        # Keep analyst formulas (column A category lookup, anything past W); drop old line values.
        kept = [c for c in cells if _col_index(_col(re.search(r'\br="([A-Z]+\d+)"', c).group(1))) not in range(2, last_col + 1)]
        new_rows[number] = (attrs, kept)
    for offset, line in enumerate(data):
        number = FIRST_ROW + offset
        attrs, cells = new_rows.get(number, (f' r="{number}"', []))
        cells = cells + [_cell_xml(f"{col}{number}", value, kind, styles.get(col, "")) for col, value, kind in line]
        cells.sort(key=lambda c: _col_index(_col(re.search(r'\br="([A-Z]+\d+)"', c).group(1))))
        attrs = re.sub(r'\s*spans="[^"]*"', "", attrs)
        new_rows[number] = (attrs, cells)
    body = "".join(
        f"<row{attrs}>{''.join(cells)}</row>" if cells else f"<row{attrs}/>"
        for _, (attrs, cells) in sorted(new_rows.items())
    )
    xml = xml[: match.start()] + f"<sheetData>{body}</sheetData>" + xml[match.end():]
    # Cached results of COUNT/SUM are stale now; Excel recomputes on open.
    xml = re.sub(r"(<c\b[^>]*>)(<f>[^<]*</f>)<v>[^<]*</v>", r"\1\2", xml)
    last = max(sorted(new_rows) or [1])
    return re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:{LAST_COL}{last}"/>', xml)


def _patch_drawing(xml: str, row: int, width: int, height: int) -> str:
    anchor = re.search(r"<(xdr:|)(oneCellAnchor|twoCellAnchor)\b[^>]*>(.*?)</\1\2>", xml, re.S)
    if not anchor or "pic" not in anchor.group(3):
        raise DrsPatchError(f"{SHEET!r} has no screenshot image to replace")
    p = anchor.group(1) or ""
    rest = re.sub(
        rf"^\s*<{p}from>.*?</{p}from>\s*(?:<{p}to>.*?</{p}to>|<{p}ext\b[^>]*/>)",
        "", anchor.group(3), count=1, flags=re.S,
    )
    cx, cy = width * EMU_PER_PX, height * EMU_PER_PX
    rest = re.sub(r'<a:ext cx="\d+" cy="\d+"\s*/>', f'<a:ext cx="{cx}" cy="{cy}"/>', rest, count=1)
    new = (
        f"<{p}oneCellAnchor><{p}from><{p}col>1</{p}col><{p}colOff>0</{p}colOff>"
        f"<{p}row>{row}</{p}row><{p}rowOff>0</{p}rowOff></{p}from>"
        f'<{p}ext cx="{cx}" cy="{cy}"/>{rest}</{p}oneCellAnchor>'
    )
    return xml[: anchor.start()] + new + xml[anchor.end():]


def _image_bytes(png: bytes, target: str) -> bytes:
    if target.lower().endswith(".png"):
        return png
    fmt = "JPEG" if target.lower().endswith((".jpg", ".jpeg")) else None
    if not fmt:
        raise DrsPatchError(f"cannot replace image of type {target!r}")
    out = io.BytesIO()
    PILImage.open(io.BytesIO(png)).convert("RGB").save(out, fmt, quality=90)
    return out.getvalue()


def patch(xlsx: bytes, records, png: bytes) -> bytes:
    data = rows(records)
    width, height = display_size(*PILImage.open(io.BytesIO(png)).size)
    with zipfile.ZipFile(io.BytesIO(xlsx)) as package:
        sheet = _sheet_part(package)
        sheet_xml = package.read(sheet).decode()
        drawing_rid = re.search(r'<drawing\b[^>]*\br:id="([^"]+)"', sheet_xml)
        if not drawing_rid:
            raise DrsPatchError(f"{SHEET!r} has no screenshot image to replace")
        drawing = _rels(package, sheet)[drawing_rid.group(1)]
        drawing_xml = package.read(drawing).decode()
        patched_drawing = _patch_drawing(drawing_xml, anchor_row(len(data)), width, height)
        blip = re.search(r'<a:blip\b[^>]*r:embed="([^"]+)"', patched_drawing)
        media = _rels(package, drawing)[blip.group(1)]
        replaced = {
            sheet: _patch_sheet(sheet_xml, data).encode(),
            drawing: patched_drawing.encode(),
            media: _image_bytes(png, media),
        }
        workbook = package.read("xl/workbook.xml").decode()
        # Without calcPr, formulas missing a cached value are still computed on open.
        if "<calcPr" in workbook:
            workbook = re.sub(r'\s*fullCalcOnLoad="[^"]*"', "", workbook)
            workbook = workbook.replace("<calcPr", '<calcPr fullCalcOnLoad="1"', 1)
            replaced["xl/workbook.xml"] = workbook.encode()
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
            for info in package.infolist():
                target.writestr(info, replaced.get(info.filename) or package.read(info.filename), compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()
