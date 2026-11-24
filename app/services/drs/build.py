"""Create a new DRS workbook holding only the SF Quote Extract tab."""

import io

from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Font, PatternFill

from .sheet import COLUMNS, FIRST_ROW, HEADER_ROW, INSTRUCTION, SHEET, rows
from .image import anchor_row, display_size

FORMATS = {"date": "m/d/yyyy", "money": "#,##0.00", "number": "#,##0.###"}
HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")


def build(records, png: bytes, report_url: str = "") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws["B1"] = INSTRUCTION
    ws["B1"].font = Font(bold=True)
    if report_url:
        ws["F1"] = report_url
        ws["F1"].hyperlink = report_url
        ws["F1"].style = "Hyperlink"
    ws["B3"] = "Reviewer Note"
    ws["F3"], ws["G3"] = "Line Count", f"=COUNT(G{FIRST_ROW}:G1048576)"
    ws["F4"], ws["G4"] = "Sum", f"=SUM(G{FIRST_ROW}:G1048576)"
    ws.cell(HEADER_ROW, 1, "Category - Price List").font = Font(bold=True)
    for col, header, _, _ in COLUMNS:
        cell = ws[f"{col}{HEADER_ROW}"]
        cell.value, cell.font, cell.fill = header, Font(bold=True), HEADER_FILL
        ws.column_dimensions[col].width = max(12, min(len(header) + 2, 50))
    ws.column_dimensions["E"].width = 50
    data = rows(records)
    for offset, line in enumerate(data):
        for col, value, kind in line:
            cell = ws[f"{col}{FIRST_ROW + offset}"]
            cell.value = value
            if kind in FORMATS:
                cell.number_format = FORMATS[kind]
    image = Image(io.BytesIO(png))
    image.width, image.height = display_size(image.width, image.height)
    ws.add_image(image, f"B{anchor_row(len(data)) + 1}")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
