from pathlib import Path

from openpyxl import Workbook

from app.services.excel_parser import parse_full_quotation_workbook


def test_parse_full_quotation_workbook_detects_header_row_and_skips_photo_column(tmp_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet["A6"] = "No."
    sheet["B6"] = "GTS No."
    sheet["C6"] = "Description"
    sheet["D6"] = "OEM"
    sheet["E6"] = "Photo"
    sheet["F6"] = "Factory"
    sheet["H6"] = "Quantity"
    sheet["J6"] = "Unit Price"
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


def test_parse_full_quotation_workbook_supports_extended_case_insensitive_aliases(tmp_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    headers = [
        "no",
        "gts",
        "desc.",
        "oem.",
        "工厂",
        "品名",
        "qty",
        "单位",
        "prix",
        "amount",
        "item/pkg",
        "pkg.",
        "w./pkg",
        "毛重",
        "l.",
        "w.",
        "h.",
        "vol.",
        "包装",
        "delivery date",
        "备注",
    ]
    for index, header in enumerate(headers, start=1):
        sheet.cell(row=5, column=index, value=header)

    values = [
        1,
        "gts-lower",
        "Lowercase Alias Product",
        "oem-lower",
        "工厂A",
        "中文产品",
        6,
        "PCS",
        3.5,
        21,
        "12/CTN",
        2,
        "5 kg",
        "10 kg",
        10,
        20,
        30,
        "0.06 CBM",
        "纸箱",
        "45 days",
        "测试备注",
    ]
    for index, value in enumerate(values, start=1):
        sheet.cell(row=6, column=index, value=value)
    path = tmp_path / "quotation_extended_aliases.xlsx"
    workbook.save(path)

    rows = parse_full_quotation_workbook(path)

    assert len(rows) == 1
    assert rows[0].values["gts_no_normalized"] == "GTSLOWER"
    assert rows[0].values["description"] == "Lowercase Alias Product"
    assert rows[0].values["oem_normalized"] == "OEMLOWER"
    assert rows[0].values["factory"] == "工厂A"
    assert rows[0].values["chinese_description"] == "中文产品"
    assert rows[0].values["quantity"] == 6
    assert rows[0].values["unit"] == "PCS"
    assert rows[0].values["unit_price"] == 3.5
    assert rows[0].values["total_price"] == 21
    assert rows[0].values["item_per_package"] == "12/CTN"
    assert rows[0].values["packages"] == 2
    assert rows[0].values["weight_per_package"] == "5 kg"
    assert rows[0].values["gross_weight"] == "10 kg"
    assert rows[0].values["length"] == 10
    assert rows[0].values["width"] == 20
    assert rows[0].values["height"] == 30
    assert rows[0].values["measurements_volume"] == "0.06 CBM"
    assert rows[0].values["packaging"] == "纸箱"
    assert rows[0].values["expected_delivery"] == "45 days"
    assert rows[0].values["comment"] == "测试备注"


def test_parse_full_quotation_workbook_warns_when_important_columns_missing(tmp_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "No."
    sheet["B1"] = "GTS No."
    sheet["A2"] = 1
    sheet["B2"] = "GTS-300"
    path = tmp_path / "quotation_missing_columns.xlsx"
    workbook.save(path)

    rows = parse_full_quotation_workbook(path)

    assert len(rows) == 1
    assert "Factory column was not found; value will be blank." in rows[0].warnings
    assert "Unit column was not found; value will be blank." in rows[0].warnings
    assert "Unit Price column was not found; value will be blank." in rows[0].warnings
