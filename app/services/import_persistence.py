from __future__ import annotations

from sqlite3 import Connection, Row
from typing import Any

from app.services.import_preview import (
    OPTIONAL_PRODUCT_UPDATE_FIELDS,
    REQUIRED_PRODUCT_CHOICE_FIELDS,
)
from app.services.normalization import normalize_gts_no, normalize_oem
from app.services.operation_logging import create_operation_log, utc_now_text
from app.services.suppliers import find_supplier_by_name, supplier_link_available


def import_preview_rows(
    connection: Connection,
    *,
    preview_rows: list[dict[str, Any]],
    operator_name: str,
    file_name: str,
    selected_updates: set[tuple[int, str]],
    required_choices: dict[tuple[int, str], str] | None = None,
    auto_backup_path: str | None = None,
) -> dict[str, int]:
    required_choices = required_choices or {}
    result = ImportResult()
    now = utc_now_text()

    for preview_row in preview_rows:
        if preview_row["errors"]:
            result.failed_details.append(failed_row_detail(preview_row, "预览有错误"))
            result.failed_rows += 1
            continue

        values = dict(preview_row["values"])
        if missing_required_choice(preview_row, required_choices):
            result.failed_details.append(failed_row_detail(preview_row, "缺少人工选择"))
            result.failed_rows += 1
            continue
        result.change_details.extend(change_details_from_choices(preview_row, required_choices))
        apply_required_choices(values, preview_row, required_choices)

        product, conflict = find_product_for_import(connection, values)
        if conflict:
            result.failed_details.append(failed_row_detail(preview_row, "GTS 和 OEM 匹配到不同产品"))
            result.failed_rows += 1
            continue

        product_id = save_product_for_import(
            connection,
            product=product,
            values=values,
            preview_row=preview_row,
            required_choices=required_choices,
            operator_name=operator_name,
            now=now,
            result=result,
        )

        duplicate_item = find_duplicate_quotation_item(connection, product_id, values)
        if duplicate_item:
            refresh_quotation_item_confirmation(
                connection,
                quotation_item_id=duplicate_item["id"],
                operator_name=operator_name,
                now=now,
            )
            result.confirmed_duplicates += 1
            result.duplicate_details.append(duplicate_detail(preview_row))
            continue

        if product:
            selected_product_updates = selected_product_update_fields(
                preview_row,
                selected_updates,
                values,
            )
            if selected_product_updates:
                update_product(
                    connection,
                    product["id"],
                    selected_product_updates,
                    operator_name,
                    now,
                )
                result.updated_products += 1

        create_quotation_item(connection, product_id, values, operator_name, now)
        result.inserted_items += 1

    create_upload_log(connection, operator_name, file_name, result, auto_backup_path)
    return result.as_dict()


class ImportResult:
    def __init__(self) -> None:
        self.created_products = 0
        self.updated_products = 0
        self.inserted_items = 0
        self.failed_rows = 0
        self.confirmed_duplicates = 0
        self.change_details: list[dict[str, str | int]] = []
        self.duplicate_details: list[dict[str, str | int]] = []
        self.failed_details: list[dict[str, str | int]] = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "created_products": self.created_products,
            "updated_products": self.updated_products,
            "inserted_items": self.inserted_items,
            "failed_rows": self.failed_rows,
            "confirmed_duplicates": self.confirmed_duplicates,
            "audit": {
                "changes": self.change_details,
                "duplicates": self.duplicate_details,
                "failed": self.failed_details,
            },
        }


def save_product_for_import(
    connection: Connection,
    *,
    product: Row | None,
    values: dict[str, Any],
    preview_row: dict[str, Any],
    required_choices: dict[tuple[int, str], str],
    operator_name: str,
    now: str,
    result: ImportResult,
) -> int:
    if not product:
        result.created_products += 1
        return create_product(connection, values, operator_name, now)

    update_fields = required_product_update_fields(preview_row, required_choices, values)
    if update_fields:
        update_product(connection, product["id"], update_fields, operator_name, now)
        result.updated_products += 1
    return int(product["id"])


def create_upload_log(
    connection: Connection,
    operator_name: str,
    file_name: str,
    result: ImportResult,
    auto_backup_path: str | None,
) -> None:
    note = (
        f"新增产品={result.created_products}; "
        f"更新产品={result.updated_products}; "
        f"确认重复报价={result.confirmed_duplicates}; "
        f"失败行={result.failed_rows}"
    )
    if auto_backup_path:
        note = f"{note}; 自动备份={auto_backup_path}"
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="upload_full_quotation",
        file_name=file_name,
        row_count=result.inserted_items,
        note=note,
    )


def change_details_from_choices(
    preview_row: dict[str, Any],
    required_choices: dict[tuple[int, str], str],
) -> list[dict[str, str | int]]:
    details = []
    for choice in preview_row.get("required_choices") or []:
        selected = required_choices.get((preview_row["row_number"], choice["field"]))
        if selected not in {"old", "new"}:
            continue
        details.append(
                {
                    "row_number": preview_row["row_number"],
                    "field": choice["field"],
                    "label": choice.get("label") or field_label(choice["field"]),
                    "existing": choice["existing"],
                    "incoming": choice["incoming"],
                    "decision": "保留旧值" if selected == "old" else "使用新值",
            }
        )
    return details


def duplicate_detail(preview_row: dict[str, Any]) -> dict[str, str | int]:
    values = preview_row.get("values") or {}
    return {
        "row_number": preview_row["row_number"],
        "gts_no": _text(values.get("gts_no")),
        "oem": _text(values.get("oem")),
        "factory": _text(values.get("factory")),
        "unit": _text(values.get("unit")),
        "unit_price": format_price(values.get("unit_price")),
    }


def failed_row_detail(preview_row: dict[str, Any], fallback_message: str) -> dict[str, str | int]:
    messages = [str(message) for message in preview_row.get("errors") or []]
    return {
        "row_number": preview_row["row_number"],
        "message": "；".join(messages) if messages else fallback_message,
    }


def format_price(value: Any) -> str:
    if value in ("", None):
        return ""
    return f"¥{float(value):.2f}"


def field_label(field: str) -> str:
    return {
        "gts_no": "GTS",
        "oem": "OEM",
        "factory": "工厂",
        "unit_price": "价格",
    }.get(field, field)


def selected_product_update_fields(
    preview_row: dict[str, Any],
    selected_updates: set[tuple[int, str]],
    values: dict[str, Any],
) -> dict[str, Any]:
    return {
        field: values[field]
        for field in OPTIONAL_PRODUCT_UPDATE_FIELDS
        if (preview_row["row_number"], field) in selected_updates
        and _text(values.get(field))
    }


def missing_required_choice(
    preview_row: dict[str, Any],
    required_choices: dict[tuple[int, str], str],
) -> bool:
    for choice in preview_row.get("required_choices") or []:
        selected = required_choices.get((preview_row["row_number"], choice["field"]))
        if selected not in {"old", "new"}:
            return True
    return False


def apply_required_choices(
    values: dict[str, Any],
    preview_row: dict[str, Any],
    required_choices: dict[tuple[int, str], str],
) -> None:
    for choice in preview_row.get("required_choices") or []:
        field = choice["field"]
        selected = required_choices[(preview_row["row_number"], field)]
        if selected == "old":
            values[field] = choice["existing"]
            if field == "gts_no":
                values["gts_no_normalized"] = normalize_gts_no(choice["existing"])[0]
            elif field == "oem":
                values["oem_normalized"] = normalize_oem(choice["existing"])[0]
            elif field == "unit_price":
                values["unit_price"] = parse_currency_choice(choice["existing"])


def parse_currency_choice(value: str) -> float:
    return float(value.replace("¥", "").replace(",", "").strip())


def required_product_update_fields(
    preview_row: dict[str, Any],
    required_choices: dict[tuple[int, str], str],
    values: dict[str, Any],
) -> dict[str, Any]:
    update_fields = {}
    for field in REQUIRED_PRODUCT_CHOICE_FIELDS:
        if required_choices.get((preview_row["row_number"], field)) != "new":
            continue
        if _text(values.get(field)):
            update_fields[field] = values[field]
            normalized_field = f"{field}_normalized"
            update_fields[normalized_field] = values.get(normalized_field)
    return update_fields


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


def update_product(
    connection: Connection,
    product_id: int,
    update_fields: dict[str, Any],
    operator_name: str,
    now: str,
) -> None:
    assignments = ", ".join(f"{field} = ?" for field in update_fields)
    connection.execute(
        f"""
        UPDATE products
        SET {assignments},
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (*update_fields.values(), operator_name, now, product_id),
    )


def find_duplicate_quotation_item(
    connection: Connection,
    product_id: int,
    values: dict[str, Any],
) -> Row | None:
    gts_no_normalized = values.get("gts_no_normalized") or ""
    oem_normalized = values.get("oem_normalized") or ""
    identifier_clause = "gts_no_normalized = ?" if gts_no_normalized else "oem_normalized = ?"
    identifier_value = gts_no_normalized or oem_normalized
    if not identifier_value:
        return None

    return connection.execute(
        f"""
        SELECT id
        FROM quotation_items
        WHERE product_id = ?
          AND {identifier_clause}
          AND factory = ?
          AND unit = ?
          AND unit_price = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (
            product_id,
            identifier_value,
            values.get("factory") or "",
            values.get("unit") or "",
            values.get("unit_price"),
        ),
    ).fetchone()


def refresh_quotation_item_confirmation(
    connection: Connection,
    *,
    quotation_item_id: int,
    operator_name: str,
    now: str,
) -> None:
    connection.execute(
        """
        UPDATE quotation_items
        SET updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (operator_name, now, quotation_item_id),
    )


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
    supplier_id = None
    include_supplier_id = supplier_link_available(connection)
    if include_supplier_id:
        supplier = find_supplier_by_name(connection, values.get("factory") or "")
        supplier_id = supplier["id"] if supplier else None
    supplier_column = "supplier_id," if include_supplier_id else ""
    supplier_placeholder = "?," if include_supplier_id else ""
    supplier_values = (supplier_id,) if include_supplier_id else ()
    connection.execute(
        f"""
        INSERT INTO quotation_items (
            product_id,
            {supplier_column}
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
        VALUES (?, {supplier_placeholder} ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            *supplier_values,
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
