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


def test_parse_full_quotation_workbook_ignores_inserted_extra_columns(tmp_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    headers = [
        "No.",
        "GTS No.",
        "Description",
        "OEM",
        "Extra Column",
        "Photo",
        "Factory",
        "Chinese Description",
        "Quantity",
        "Unit",
        "Unit Price",
        "Total Price",
        "Another Extra",
        "Item/Package",
        "Packages",
        "Weight / Package",
        "G.W.",
        "Length",
        "Width",
        "Height",
        "Measurements (Volume)",
        "Packaging",
        "Expected Delivery",
        "Comment",
    ]
    for index, header in enumerate(headers, start=1):
        sheet.cell(row=3, column=index, value=header)

    sheet["A4"] = 1
    sheet["B4"] = "GTS-00999"
    sheet["C4"] = "Filter"
    sheet["D4"] = "OEM-00999"
    sheet["E4"] = "ignored extra"
    sheet["F4"] = "ignored photo"
    sheet["G4"] = "Factory Extra"
    sheet["I4"] = 3
    sheet["K4"] = 6.5
    sheet["L4"] = 19.5
    sheet["X4"] = "ok"
    path = tmp_path / "quotation_extra_columns.xlsx"
    workbook.save(path)

    rows = parse_full_quotation_workbook(path)

    assert len(rows) == 1
    assert rows[0].values["gts_no_normalized"] == "GTS00999"
    assert rows[0].values["factory"] == "Factory Extra"
    assert rows[0].values["quantity"] == 3
    assert rows[0].values["unit_price"] == 6.5
    assert rows[0].values["total_price"] == 19.5
    assert rows[0].values["comment"] == "ok"


def test_parse_full_quotation_workbook_supports_common_header_aliases(tmp_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet["A2"] = "No"
    sheet["B2"] = "GTS"
    sheet["C2"] = "Desc"
    sheet["D2"] = "OEM No"
    sheet["E2"] = "Qty"
    sheet["F2"] = "Price"
    sheet["A3"] = 1
    sheet["B3"] = "GTS-ABC"
    sheet["C3"] = "Alias Product"
    sheet["D3"] = "OEM-ABC"
    sheet["E3"] = 8
    sheet["F3"] = 2.25
    path = tmp_path / "quotation_aliases.xlsx"
    workbook.save(path)

    rows = parse_full_quotation_workbook(path)

    assert len(rows) == 1
    assert rows[0].values["gts_no_normalized"] == "GTSABC"
    assert rows[0].values["description"] == "Alias Product"
    assert rows[0].values["oem_normalized"] == "OEMABC"
    assert rows[0].values["quantity"] == 8
    assert rows[0].values["unit_price"] == 2.25
