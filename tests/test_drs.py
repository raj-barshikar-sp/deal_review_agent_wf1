import io
import zipfile
from datetime import date

from openpyxl import load_workbook
from PIL import Image

from app.services.drs import build, patch
from app.services.drs.sheet import SHEET, account_name, order_start


def line(name, qty, start="2026-03-16"):
    return {
        "SBQQ__Quote__r": {"Name": "Q-127182", "SBQQ__Account__r": {"Name": "Fidelity Investments"}},
        "Name": name,
        "SBQQ__ProductCode__c": "TERM-IIQ",
        "SBQQ__ProductName__c": "IdentityIQ",
        "SBQQ__ProductFamily__c": "Term License",
        "SBQQ__Quantity__c": qty,
        "SBQQ__EffectiveStartDate__c": start,
        "SBQQ__EffectiveEndDate__c": "2029-03-15",
        "CurrencyIsoCode": "EUR",
        "SBQQ__NetTotal__c": 10.5,
    }


def png(width, height, color):
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, "PNG")
    return out.getvalue()


def anchor_row(xlsx):
    ws = load_workbook(io.BytesIO(xlsx))[SHEET]
    return ws._images[0].anchor._from.row


def test_account_and_order_start():
    records = [line("QL-2", 1, "2026-04-01"), line("QL-1", 1, "2026-03-16")]
    assert account_name(records) == "Fidelity Investments"
    assert order_start(records) == date(2026, 3, 16)


def test_build_lays_out_the_tab():
    xlsx = build([line("QL-1", 22000), line("QL-2", 1)], png(400, 200, "red"), "https://example/report")
    ws = load_workbook(io.BytesIO(xlsx))[SHEET]
    assert ws["G3"].value == "=COUNT(G7:G1048576)"
    assert ws["B6"].value == "Quote Number" and ws["W6"].value == "Currency"
    assert [ws["C7"].value, ws["G7"].value, ws["C8"].value] == ["QL-1", 22000, "QL-2"]
    assert ws["H7"].value.date() == date(2026, 3, 16)
    assert ws["J7"].value == "EUR" and ws["L7"].value == "USD"
    assert anchor_row(xlsx) == 9


def test_patch_rewrites_lines_and_image_only():
    original = build([line(f"QL-{i}", i) for i in range(1, 6)], png(400, 200, "red"))
    wb = load_workbook(io.BytesIO(original))
    wb.create_sheet("NS RA Extract")["A1"] = "analyst data"
    wb[SHEET]["A7"] = '=IF(B7="","","x")'
    buffer = io.BytesIO()
    wb.save(buffer)
    edited = buffer.getvalue()

    patched = patch(edited, [line("QL-9", 7), line("QL-10", 3)], png(300, 100, "blue"))

    wb = load_workbook(io.BytesIO(patched))
    ws = wb[SHEET]
    assert [ws["C7"].value, ws["C8"].value] == ["QL-9", "QL-10"]
    assert all(ws[f"C{r}"].value is None for r in range(9, 12))
    assert ws["A7"].value == '=IF(B7="","","x")'
    assert ws["G3"].value == "=COUNT(G7:G1048576)"
    assert ws["H7"].number_format == "m/d/yyyy"
    assert wb["NS RA Extract"]["A1"].value == "analyst data"
    assert anchor_row(patched) == 9
    with zipfile.ZipFile(io.BytesIO(patched)) as z:
        media = [n for n in z.namelist() if n.startswith("xl/media/")]
        assert Image.open(io.BytesIO(z.read(media[0]))).size == (300, 100)
        before = zipfile.ZipFile(io.BytesIO(edited))
        untouched = [n for n in before.namelist() if "sheet2" in n]
        assert untouched and all(z.read(n) == before.read(n) for n in untouched)
