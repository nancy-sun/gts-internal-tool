from pathlib import Path

from openpyxl import Workbook

from app.services.excel_parser import parse_full_quotation_workbook


def test_parse_full_quotation_workbook_uses_configured_rows(tmp_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet["B4"] = "GTS-00123"
    sheet["C4"] = "Brake Pad"
    sheet["D4"] = " A 500 008 3949 "
    sheet["G4"] = 2
    sheet["I4"] = 10.5
    path = tmp_path / "quotation.xlsx"
    workbook.save(path)

    rows = parse_full_quotation_workbook(path)

    assert len(rows) == 1
    assert rows[0].values["gts_no_normalized"] == "GTS00123"
    assert rows[0].values["oem_normalized"] == "A5000083949"
    assert rows[0].values["quantity"] == 2
    assert rows[0].values["unit_price"] == 10.5
