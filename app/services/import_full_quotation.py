from __future__ import annotations

from dataclasses import asdict, dataclass
from sqlite3 import Connection, Row
from typing import Any

from app.services.excel_parser import ParsedQuotationRow
from app.services.lookup_helpers import (
    fetch_products_by_normalized_field,
    unique_text_values,
)
from app.services.normalization import normalize_gts_no, normalize_oem
from app.services.operation_logging import create_operation_log, utc_now_text


OPTIONAL_PRODUCT_UPDATE_FIELDS = ("description", "chinese_description")
REQUIRED_PRODUCT_CHOICE_FIELDS = ("gts_no", "oem")
REQUIRED_QUOTATION_CHOICE_FIELDS = ("factory", "unit_price")


@dataclass(frozen=True)
class ImportLookupContext:
    products_by_gts: dict[str, Row]
    products_by_oem: dict[str, Row]
    latest_quotes_by_product_id: dict[int, Row]


def build_import_preview(
    connection: Connection,
    parsed_rows: list[ParsedQuotationRow],
) -> list[dict[str, Any]]:
    lookup_context = build_import_lookup_context(connection, parsed_rows)
    return build_import_preview_rows(lookup_context, parsed_rows)


def build_import_preview_row(
    lookup_context: ImportLookupContext,
    parsed_row: ParsedQuotationRow,
) -> dict[str, Any]:
    preview = asdict(parsed_row)
    preview["matched_product"] = None
    preview["product_changes"] = []
    preview["quotation_warnings"] = []
    preview["quotation_changes"] = []
    preview["required_choices"] = []

    if not parsed_row.is_valid:
        return preview

    product, conflict = find_product_in_context(
        lookup_context,
        parsed_row.values,
    )
    if conflict:
        preview["errors"].append(
            "GTS 和 OEM 匹配到不同产品，需要人工确认。"
        )
        return preview

    if not product:
        return preview

    preview["matched_product"] = dict(product)
    preview["required_choices"].extend(
        detect_required_product_choices(product, parsed_row.values)
    )
    preview["product_changes"] = detect_product_changes(product, parsed_row.values)
    latest_quote = lookup_context.latest_quotes_by_product_id.get(product["id"])
    preview["quotation_changes"] = detect_quotation_changes_from_latest(
        latest_quote,
        parsed_row.values,
    )
    required_quotation_choices = required_quotation_changes_from(
        preview["quotation_changes"]
    )
    preview["quotation_warnings"] = [
        change["message"]
        for change in preview["quotation_changes"]
        if change["field"] not in REQUIRED_QUOTATION_CHOICE_FIELDS
    ]
    preview["required_choices"].extend(required_quotation_choices)
    return preview


def build_import_preview_rows(
    lookup_context: ImportLookupContext,
    parsed_rows: list[ParsedQuotationRow],
) -> list[dict[str, Any]]:
    preview_rows = []
    for parsed_row in parsed_rows:
        preview_rows.append(build_import_preview_row(lookup_context, parsed_row))
    return preview_rows


def build_import_lookup_context(
    connection: Connection,
    parsed_rows: list[ParsedQuotationRow],
) -> ImportLookupContext:
    valid_values = [row.values for row in parsed_rows if row.is_valid]
    gts_numbers = unique_text_values(row.get("gts_no_normalized") for row in valid_values)
    oem_numbers = unique_text_values(row.get("oem_normalized") for row in valid_values)

    products_by_gts = fetch_products_by_normalized_field(
        connection,
        "gts_no_normalized",
        gts_numbers,
        order_by="id",
    )
    products_by_oem = fetch_products_by_normalized_field(
        connection,
        "oem_normalized",
        oem_numbers,
        order_by="id",
    )
    product_ids = {
        int(product["id"])
        for product in [*products_by_gts.values(), *products_by_oem.values()]
    }
    latest_quotes_by_product_id = fetch_latest_quotes_by_product_id(
        connection,
        product_ids,
    )
    return ImportLookupContext(
        products_by_gts=products_by_gts,
        products_by_oem=products_by_oem,
        latest_quotes_by_product_id=latest_quotes_by_product_id,
    )


def find_product_in_context(
    context: ImportLookupContext,
    values: dict[str, Any],
) -> tuple[Row | None, bool]:
    gts_no_normalized = values.get("gts_no_normalized") or ""
    oem_normalized = values.get("oem_normalized") or ""
    gts_product = context.products_by_gts.get(gts_no_normalized)
    oem_product = context.products_by_oem.get(oem_normalized)

    if gts_product and oem_product and gts_product["id"] != oem_product["id"]:
        return None, True
    if gts_product:
        return gts_product, False
    if oem_product:
        return oem_product, False
    return None, False


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
    for field in OPTIONAL_PRODUCT_UPDATE_FIELDS:
        incoming_value = _text(values.get(field))
        existing_value = _text(product[field])
        if incoming_value and incoming_value != existing_value:
            previous_source = previous_data_note(product)
            changes.append(
                {
                    "field": field,
                    "existing": existing_value,
                    "incoming": incoming_value,
                    "previous_source": previous_source,
                    "existing_with_source": append_previous_source(
                        existing_value,
                        previous_source,
                    ),
                }
            )
    return changes


def detect_required_product_choices(product: Row, values: dict[str, Any]) -> list[dict[str, str]]:
    choices = []
    labels = {
        "gts_no": "GTS",
        "oem": "OEM",
    }
    for field in REQUIRED_PRODUCT_CHOICE_FIELDS:
        incoming_value = _text(values.get(field))
        existing_value = _text(product[field])
        if incoming_value and existing_value and incoming_value != existing_value:
            previous_source = previous_data_note(product)
            existing_with_source = append_previous_source(existing_value, previous_source)
            choices.append(
                {
                    "field": field,
                    "label": labels[field],
                    "existing": existing_value,
                    "incoming": incoming_value,
                    "previous_source": previous_source,
                    "existing_with_source": existing_with_source,
                    "message": f"{existing_with_source} => {incoming_value}",
                }
            )
    return choices


def required_quotation_changes_from(changes: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        change
        for change in changes
        if change["field"] in REQUIRED_QUOTATION_CHOICE_FIELDS
    ]


def detect_quotation_changes_from_latest(
    latest: Row | None,
    values: dict[str, Any],
) -> list[dict[str, str]]:
    if not latest:
        return []

    changes = []
    labels = {
        "factory": "工厂",
        "unit": "单位",
        "unit_price": "价格",
    }
    for field in ("factory", "unit"):
        incoming_value = _text(values.get(field))
        existing_value = _text(latest[field])
        if incoming_value and existing_value and incoming_value != existing_value:
            previous_source = previous_data_note(latest)
            existing_with_source = append_previous_source(
                existing_value,
                previous_source,
            )
            changes.append(
                {
                    "field": field,
                    "label": labels[field],
                    "existing": existing_value,
                    "incoming": incoming_value,
                    "previous_source": previous_source,
                    "existing_with_source": existing_with_source,
                    "message": f"{existing_with_source} => {incoming_value}",
                }
            )

    incoming_price = values.get("unit_price")
    if incoming_price is not None and latest["unit_price"] is not None:
        existing_price = float(latest["unit_price"])
        new_price = float(incoming_price)
        if existing_price != new_price:
            previous_source = previous_data_note(latest)
            existing_value = f"¥{existing_price:.2f}"
            incoming_value = f"¥{new_price:.2f}"
            existing_with_source = append_previous_source(
                existing_value,
                previous_source,
            )
            changes.append(
                {
                    "field": "unit_price",
                    "label": labels["unit_price"],
                    "existing": existing_value,
                    "incoming": incoming_value,
                    "previous_source": previous_source,
                    "existing_with_source": existing_with_source,
                    "message": f"{existing_with_source} => {incoming_value}",
                }
            )
    return changes


def fetch_latest_quotes_by_product_id(
    connection: Connection,
    product_ids: set[int],
) -> dict[int, Row]:
    if not product_ids:
        return {}

    ordered_ids = sorted(product_ids)
    placeholders = ", ".join("?" for _ in ordered_ids)
    rows = connection.execute(
        f"""
        SELECT gts_no, factory, unit, unit_price, updated_by, updated_at, product_id
        FROM quotation_items
        WHERE product_id IN ({placeholders})
        ORDER BY product_id, updated_at DESC, id DESC
        """,
        ordered_ids,
    ).fetchall()
    latest_quotes = {}
    for row in rows:
        product_id = int(row["product_id"])
        if product_id not in latest_quotes:
            latest_quotes[product_id] = row
    return latest_quotes


def previous_data_note(row: Row) -> str:
    updated_by = _text(row["updated_by"]) if "updated_by" in row.keys() else ""
    updated_at = _text(row["updated_at"])[:10] if "updated_at" in row.keys() else ""
    if updated_by and updated_at:
        return f"{updated_by} {updated_at}"
    if updated_by:
        return updated_by
    if updated_at:
        return updated_at
    return ""


def append_previous_source(value: str, previous_source: str) -> str:
    if not previous_source:
        return value
    return f"{value} ({previous_source})"


def import_preview_rows(
    connection: Connection,
    *,
    preview_rows: list[dict[str, Any]],
    operator_name: str,
    file_name: str,
    selected_updates: set[tuple[int, str]],
    required_choices: dict[tuple[int, str], str] | None = None,
) -> dict[str, int]:
    required_choices = required_choices or {}
    created_products = 0
    updated_products = 0
    inserted_items = 0
    failed_rows = 0
    skipped_duplicates = 0
    now = utc_now_text()

    for preview_row in preview_rows:
        if preview_row["errors"]:
            failed_rows += 1
            continue

        values = dict(preview_row["values"])
        if missing_required_choice(preview_row, required_choices):
            failed_rows += 1
            continue
        apply_required_choices(values, preview_row, required_choices)

        product, conflict = find_product_for_import(connection, values)
        if conflict:
            failed_rows += 1
            continue

        product_id = product["id"] if product else None
        if product:
            update_fields = required_product_update_fields(preview_row, required_choices, values)
            if update_fields:
                update_product(connection, product["id"], update_fields, operator_name, now)
                updated_products += 1
            product_id = product["id"]
        else:
            product_id = create_product(connection, values, operator_name, now)
            created_products += 1

        if product_id and quotation_item_duplicate_exists(connection, product_id, values):
            skipped_duplicates += 1
            continue

        if product:
            update_fields = {
                field: values[field]
                for field in OPTIONAL_PRODUCT_UPDATE_FIELDS
                if (preview_row["row_number"], field) in selected_updates
                and _text(values.get(field))
            }
            if update_fields:
                update_product(connection, product["id"], update_fields, operator_name, now)
                updated_products += 1

        create_quotation_item(connection, product_id, values, operator_name, now)
        inserted_items += 1

    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="upload_full_quotation",
        file_name=file_name,
        row_count=inserted_items,
        note=(
            f"新增产品={created_products}; "
            f"更新产品={updated_products}; "
            f"跳过重复行={skipped_duplicates}; "
            f"失败行={failed_rows}"
        ),
    )
    return {
        "created_products": created_products,
        "updated_products": updated_products,
        "inserted_items": inserted_items,
        "failed_rows": failed_rows,
        "skipped_duplicates": skipped_duplicates,
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


def quotation_item_duplicate_exists(
    connection: Connection,
    product_id: int,
    values: dict[str, Any],
) -> bool:
    gts_no_normalized = values.get("gts_no_normalized") or ""
    oem_normalized = values.get("oem_normalized") or ""
    identifier_clause = "gts_no_normalized = ?" if gts_no_normalized else "oem_normalized = ?"
    identifier_value = gts_no_normalized or oem_normalized
    if not identifier_value:
        return False

    return (
        connection.execute(
            f"""
            SELECT 1
            FROM quotation_items
            WHERE product_id = ?
              AND {identifier_clause}
              AND factory = ?
              AND unit = ?
              AND unit_price = ?
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
        is not None
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
