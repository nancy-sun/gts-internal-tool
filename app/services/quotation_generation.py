from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from sqlite3 import Connection, Row
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.services.operation_logging import create_operation_log
from app.services.request_parser import ParsedRequestRow


GENERATED_COLUMNS = [
    ("no", "No."),
    ("gts_no", "GTS No."),
    ("description", "Description"),
    ("oem", "OEM"),
    ("photo", "Photo"),
    ("factory", "Factory"),
    ("chinese_description", "Chinese Description"),
    ("quantity", "Quantity"),
    ("unit", "Unit"),
    ("unit_price", "Unit Price"),
    ("total_price", "Total Price"),
    ("item_per_package", "Item/Package"),
    ("packages", "Packages"),
    ("weight_per_package", "Weight / Package"),
    ("gross_weight", "G.W."),
    ("length", "Length"),
    ("width", "Width"),
    ("height", "Height"),
    ("measurements_volume", "Measurements / Volume"),
    ("packaging", "Packaging"),
    ("expected_delivery", "Expected Delivery"),
    ("comment", "Comment"),
    ("updated_by", "Updated By"),
    ("updated_at", "Updated At"),
]


def build_generation_preview(
    connection: Connection,
    parsed_rows: list[ParsedRequestRow],
) -> list[dict[str, Any]]:
    preview_rows = []
    for parsed_row in parsed_rows:
        preview = asdict(parsed_row)
        preview["status"] = "ready"
        preview["product"] = None
        preview["candidates"] = []

        if parsed_row.errors:
            preview["status"] = "invalid"
            preview_rows.append(preview)
            continue

        product, conflict = find_product_for_request(connection, parsed_row.values)
        if conflict:
            preview["status"] = "conflict"
            preview["errors"].append(
                "GTS No. and OEM match different products. Manual review required."
            )
            preview_rows.append(preview)
            continue

        if not product:
            preview["status"] = "unmatched"
            preview_rows.append(preview)
            continue

        preview["product"] = dict(product)
        candidates = list_quotation_candidates(connection, product["id"])
        preview["candidates"] = [dict(candidate) for candidate in candidates]
        if not candidates:
            preview["status"] = "no_quotation"
        elif len(candidates) > 1:
            preview["status"] = "multiple_candidates"
        preview_rows.append(preview)
    return preview_rows


def find_product_for_request(
    connection: Connection,
    values: dict[str, Any],
) -> tuple[Row | None, bool]:
    gts_no_normalized = values.get("gts_no_normalized") or ""
    oem_normalized = values.get("oem_normalized") or ""
    gts_product = None
    oem_product = None

    if gts_no_normalized:
        gts_product = connection.execute(
            "SELECT * FROM products WHERE gts_no_normalized = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
            (gts_no_normalized,),
        ).fetchone()
    if oem_normalized:
        oem_product = connection.execute(
            "SELECT * FROM products WHERE oem_normalized = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
            (oem_normalized,),
        ).fetchone()

    if gts_product and oem_product and gts_product["id"] != oem_product["id"]:
        return None, True
    if gts_product:
        return gts_product, False
    if oem_product:
        return oem_product, False
    return None, False


def list_quotation_candidates(connection: Connection, product_id: int) -> list[Row]:
    return connection.execute(
        """
        SELECT *
        FROM quotation_items
        WHERE product_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (product_id,),
    ).fetchall()


def create_generated_workbook(
    connection: Connection,
    *,
    preview_rows: list[dict[str, Any]],
    selected_candidate_ids: dict[int, int],
    operator_name: str,
    request_file_name: str,
) -> tuple[BytesIO, int]:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Internal Quotation"

    worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(GENERATED_COLUMNS))
    title_cell = worksheet.cell(row=1, column=1, value="GTS Internal Quotation")
    title_cell.font = Font(bold=True, size=14, color="172033")
    title_cell.fill = PatternFill(fill_type="solid", fgColor="EAF3F0")

    for column_index, (_, label) in enumerate(GENERATED_COLUMNS, start=1):
        cell = worksheet.cell(row=2, column=column_index, value=label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(fill_type="solid", fgColor="176D5D")

    output_row = 3
    generated_count = 0
    for preview_row in preview_rows:
        row_number = int(preview_row["row_number"])
        selected_id = selected_candidate_ids.get(row_number)
        if not selected_id:
            continue

        candidate = connection.execute(
            "SELECT * FROM quotation_items WHERE id = ?",
            (selected_id,),
        ).fetchone()
        if not candidate:
            continue

        request_quantity = preview_row["values"].get("quantity")
        request_description = preview_row["values"].get("description")
        output_values = build_output_row(candidate, request_quantity, request_description)
        output_values["no"] = generated_count + 1
        for column_index, (field, _) in enumerate(GENERATED_COLUMNS, start=1):
            worksheet.cell(row=output_row, column=column_index, value=output_values.get(field))
        output_row += 1
        generated_count += 1

    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="generate_quotation",
        file_name=request_file_name,
        row_count=generated_count,
        note="Generated internal quotation workbook for immediate download.",
    )

    apply_generated_workbook_formatting(worksheet)

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream, generated_count


def build_output_row(
    candidate: Row,
    request_quantity: float | None,
    request_description: str | None = None,
) -> dict[str, Any]:
    output = {field: candidate[field] for field, _ in GENERATED_COLUMNS if field in candidate.keys()}
    output["photo"] = None
    if request_description:
        output["description"] = request_description
    output["quantity"] = request_quantity if request_quantity is not None else None
    if request_quantity is not None and candidate["unit_price"] is not None:
        output["total_price"] = float(request_quantity) * float(candidate["unit_price"])
    elif request_quantity is None:
        output["total_price"] = None
    return output


def apply_generated_workbook_formatting(worksheet) -> None:
    column_widths = {
        "A": 8,
        "B": 16,
        "C": 28,
        "D": 20,
        "E": 12,
        "F": 18,
        "G": 24,
        "H": 12,
        "I": 10,
        "J": 14,
        "K": 14,
        "L": 16,
        "M": 12,
        "N": 18,
        "O": 12,
        "P": 10,
        "Q": 10,
        "R": 10,
        "S": 20,
        "T": 18,
        "U": 18,
        "V": 28,
        "W": 16,
        "X": 22,
    }
    for column, width in column_widths.items():
        worksheet.column_dimensions[column].width = width

    worksheet.freeze_panes = "A3"
    currency_format = '"¥"#,##0.00'
    decimal_format = "0.00"

    field_to_column = {
        field: get_column_letter(index)
        for index, (field, _) in enumerate(GENERATED_COLUMNS, start=1)
    }
    for row in range(3, worksheet.max_row + 1):
        worksheet[f"{field_to_column['quantity']}{row}"].number_format = "0"
        worksheet[f"{field_to_column['unit_price']}{row}"].number_format = currency_format
        worksheet[f"{field_to_column['total_price']}{row}"].number_format = currency_format
        for field in ("length", "width", "height", "measurements_volume"):
            worksheet[f"{field_to_column[field]}{row}"].number_format = decimal_format
