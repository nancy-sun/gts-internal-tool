from __future__ import annotations

from dataclasses import asdict
from sqlite3 import Connection, Row
from typing import Any

from app.services.excel_parser import ParsedQuotationRow
from app.services.operation_logging import create_operation_log, utc_now_text


PRODUCT_UPDATE_FIELDS = ("oem", "description", "chinese_description")


def build_import_preview(
    connection: Connection,
    parsed_rows: list[ParsedQuotationRow],
) -> list[dict[str, Any]]:
    preview_rows = []
    for parsed_row in parsed_rows:
        preview = asdict(parsed_row)
        preview["matched_product"] = None
        preview["product_changes"] = []
        preview["factory_warning"] = None

        if parsed_row.is_valid:
            product, conflict = find_product_for_import(connection, parsed_row.values)
            if conflict:
                preview["errors"].append(
                    "GTS No. and OEM match different products. Manual review required."
                )
            elif product:
                preview["matched_product"] = dict(product)
                preview["product_changes"] = detect_product_changes(product, parsed_row.values)
                preview["factory_warning"] = detect_factory_warning(
                    connection,
                    product["id"],
                    parsed_row.values.get("factory"),
                )

        preview_rows.append(preview)
    return preview_rows


def find_product_for_import(
    connection: Connection,
    values: dict[str, Any],
) -> tuple[Row | None, bool]:
    gts_no_normalized = values.get("gts_no_normalized") or ""
    oem_normalized = values.get("oem_normalized") or ""

    gts_product = None
    oem_product = None
    if gts_no_normalized:
        gts_product = connection.execute(
            "SELECT * FROM products WHERE gts_no_normalized = ? ORDER BY id LIMIT 1",
            (gts_no_normalized,),
        ).fetchone()
    if oem_normalized:
        oem_product = connection.execute(
            "SELECT * FROM products WHERE oem_normalized = ? ORDER BY id LIMIT 1",
            (oem_normalized,),
        ).fetchone()

    if gts_product and oem_product and gts_product["id"] != oem_product["id"]:
        return None, True
    if gts_product:
        return gts_product, False
    if oem_product:
        return oem_product, False
    return None, False


def detect_product_changes(product: Row, values: dict[str, Any]) -> list[dict[str, str]]:
    changes = []
    for field in PRODUCT_UPDATE_FIELDS:
        incoming_value = _text(values.get(field))
        existing_value = _text(product[field])
        if incoming_value and incoming_value != existing_value:
            changes.append(
                {
                    "field": field,
                    "existing": existing_value,
                    "incoming": incoming_value,
                }
            )
    return changes


def detect_factory_warning(
    connection: Connection,
    product_id: int,
    incoming_factory: Any,
) -> str | None:
    factory = _text(incoming_factory)
    if not factory:
        return None

    existing = connection.execute(
        """
        SELECT DISTINCT factory
        FROM quotation_items
        WHERE product_id = ?
          AND factory IS NOT NULL
          AND TRIM(factory) != ''
          AND factory != ?
        LIMIT 1
        """,
        (product_id, factory),
    ).fetchone()
    if not existing:
        return None
    return (
        "This product already has quotation history from another factory. "
        "Confirming import will add a new historical quotation row; existing rows are not overwritten."
    )


def import_preview_rows(
    connection: Connection,
    *,
    preview_rows: list[dict[str, Any]],
    operator_name: str,
    file_name: str,
    selected_updates: set[tuple[int, str]],
) -> dict[str, int]:
    created_products = 0
    updated_products = 0
    inserted_items = 0
    failed_rows = 0
    now = utc_now_text()

    for preview_row in preview_rows:
        if preview_row["errors"]:
            failed_rows += 1
            continue

        values = preview_row["values"]
        product, conflict = find_product_for_import(connection, values)
        if conflict:
            failed_rows += 1
            continue

        if product:
            update_fields = {
                field: values[field]
                for field in PRODUCT_UPDATE_FIELDS
                if (preview_row["row_number"], field) in selected_updates
                and _text(values.get(field))
            }
            if update_fields:
                assignments = ", ".join(f"{field} = ?" for field in update_fields)
                connection.execute(
                    f"""
                    UPDATE products
                    SET {assignments},
                        updated_by = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (*update_fields.values(), operator_name, now, product["id"]),
                )
                updated_products += 1
            product_id = product["id"]
        else:
            product_id = create_product(connection, values, operator_name, now)
            created_products += 1

        create_quotation_item(connection, product_id, values, operator_name, now)
        inserted_items += 1

    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="upload_full_quotation",
        file_name=file_name,
        row_count=inserted_items,
        note=(
            f"created_products={created_products}; "
            f"updated_products={updated_products}; failed_rows={failed_rows}"
        ),
    )
    return {
        "created_products": created_products,
        "updated_products": updated_products,
        "inserted_items": inserted_items,
        "failed_rows": failed_rows,
    }


def create_product(
    connection: Connection,
    values: dict[str, Any],
    operator_name: str,
    now: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO products (
            gts_no,
            gts_no_normalized,
            oem,
            oem_normalized,
            description,
            chinese_description,
            created_by,
            created_at,
            updated_by,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            values.get("gts_no"),
            values.get("gts_no_normalized"),
            values.get("oem"),
            values.get("oem_normalized"),
            values.get("description"),
            values.get("chinese_description"),
            operator_name,
            now,
            operator_name,
            now,
        ),
    )
    return int(cursor.lastrowid)


def create_quotation_item(
    connection: Connection,
    product_id: int,
    values: dict[str, Any],
    operator_name: str,
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id,
            no,
            gts_no,
            gts_no_normalized,
            description,
            oem,
            oem_normalized,
            factory,
            chinese_description,
            quantity,
            unit,
            unit_price,
            total_price,
            item_per_package,
            packages,
            weight_per_package,
            gross_weight,
            length,
            width,
            height,
            measurements_volume,
            packaging,
            expected_delivery,
            comment,
            created_by,
            created_at,
            updated_by,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            values.get("no"),
            values.get("gts_no"),
            values.get("gts_no_normalized"),
            values.get("description"),
            values.get("oem"),
            values.get("oem_normalized"),
            values.get("factory"),
            values.get("chinese_description"),
            values.get("quantity"),
            values.get("unit"),
            values.get("unit_price"),
            values.get("total_price"),
            values.get("item_per_package"),
            values.get("packages"),
            values.get("weight_per_package"),
            values.get("gross_weight"),
            values.get("length"),
            values.get("width"),
            values.get("height"),
            values.get("measurements_volume"),
            values.get("packaging"),
            values.get("expected_delivery"),
            values.get("comment"),
            operator_name,
            now,
            operator_name,
            now,
        ),
    )


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
