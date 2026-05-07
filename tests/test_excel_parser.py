from pathlib import Path

from openpyxl import Workbook

from app.services.excel_parser import parse_full_quotation_workbook


def test_parse_full_quotation_workbook_detects_header_row_and_skips_photo_column(tmp_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet["A6"] = "No."
    sheet["B6"] = "GTS No."
    sheet["E6"] = "Photo"
    sheet["A7"] = 1
    sheet["B7"] = "GTS-00123"
    sheet["C7"] = "Brake Pad"
    sheet["D7"] = " A 500 008 3949 "
    sheet["E7"] = "ignored photo cell"
    sheet["F7"] = "Factory A"
    sheet["H7"] = 2
    sheet["J7"] = 10.5
    path = tmp_path / "quotation.xlsx"
    workbook.save(path)

    rows = parse_full_quotation_workbook(path)

    assert len(rows) == 1
    assert rows[0].values["gts_no_normalized"] == "GTS00123"
    assert rows[0].values["oem_normalized"] == "A5000083949"
    assert rows[0].values["factory"] == "Factory A"
    assert rows[0].values["quantity"] == 2
    assert rows[0].values["unit_price"] == 10.5
