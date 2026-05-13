from __future__ import annotations

from dataclasses import asdict, dataclass
from sqlite3 import Connection, Row
from typing import Any

from app.services.excel_parser import ParsedQuotationRow
from app.services.lookup_helpers import (
    fetch_products_by_normalized_field,
    unique_text_values,
)


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
    preview["quotation_warnings"] = [
        change["message"]
        for change in preview["quotation_changes"]
        if change["field"] not in REQUIRED_QUOTATION_CHOICE_FIELDS
    ]
    preview["required_choices"].extend(
        required_quotation_changes_from(preview["quotation_changes"])
    )
    return preview


def build_import_preview_rows(
    lookup_context: ImportLookupContext,
    parsed_rows: list[ParsedQuotationRow],
) -> list[dict[str, Any]]:
    return [
        build_import_preview_row(lookup_context, parsed_row)
        for parsed_row in parsed_rows
    ]


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


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
