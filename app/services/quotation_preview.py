from __future__ import annotations

from dataclasses import asdict, dataclass
from sqlite3 import Connection, Row
from typing import Any

from app.services.lookup_helpers import (
    fetch_products_by_normalized_field,
    unique_text_values,
)
from app.services.request_parser import ParsedRequestRow
from app.services.suppliers import supplier_link_available


@dataclass(frozen=True)
class GenerationLookupContext:
    products_by_gts: dict[str, Row]
    products_by_oem: dict[str, Row]
    products_by_historical_gts: dict[str, Row]
    products_by_historical_oem: dict[str, Row]
    candidates_by_product_id: dict[int, list[Row]]


def build_generation_preview(
    connection: Connection,
    parsed_rows: list[ParsedRequestRow],
) -> list[dict[str, Any]]:
    lookup_context = build_generation_lookup_context(connection, parsed_rows)
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
        if request_row_missing_identifier(parsed_row.values):
            preview["status"] = "missing_identifier"
            preview_rows.append(preview)
            continue

        product, conflict = find_product_in_context(
            lookup_context,
            parsed_row.values,
        )
        if conflict:
            preview["status"] = "conflict"
            preview["errors"].append(
                "GTS 和 OEM 匹配到不同产品，需要人工确认。"
            )
            preview_rows.append(preview)
            continue

        if not product:
            preview["status"] = "unmatched"
            preview_rows.append(preview)
            continue

        preview["product"] = dict(product)
        candidates = lookup_context.candidates_by_product_id.get(product["id"], [])
        preview["candidates"] = [dict(candidate) for candidate in candidates]
        preview["change_notices"] = build_product_change_notices(
            product,
            parsed_row.values,
        )
        if not candidates:
            preview["status"] = "no_quotation"
        elif len(candidates) > 1:
            preview["status"] = "multiple_candidates"
        preview_rows.append(preview)
    return preview_rows


def request_rows_have_any_identifier(parsed_rows: list[ParsedRequestRow]) -> bool:
    return any(
        not parsed_row.errors and not request_row_missing_identifier(parsed_row.values)
        for parsed_row in parsed_rows
    )


def request_row_missing_identifier(values: dict[str, Any]) -> bool:
    return not values.get("gts_no_normalized") and not values.get("oem_normalized")


def build_generation_lookup_context(
    connection: Connection,
    parsed_rows: list[ParsedRequestRow],
) -> GenerationLookupContext:
    valid_values = [row.values for row in parsed_rows if not row.errors]
    gts_numbers = unique_text_values(row.get("gts_no_normalized") for row in valid_values)
    oem_numbers = unique_text_values(row.get("oem_normalized") for row in valid_values)

    products_by_gts = fetch_products_by_normalized_field(
        connection,
        "gts_no_normalized",
        gts_numbers,
        order_by="updated_at DESC, id DESC",
    )
    products_by_oem = fetch_products_by_normalized_field(
        connection,
        "oem_normalized",
        oem_numbers,
        order_by="updated_at DESC, id DESC",
    )
    products_by_historical_gts = fetch_products_by_historical_quotation_field(
        connection,
        "gts_no_normalized",
        gts_numbers,
    )
    products_by_historical_oem = fetch_products_by_historical_quotation_field(
        connection,
        "oem_normalized",
        oem_numbers,
    )
    product_ids = {
        int(product["id"])
        for product in [
            *products_by_gts.values(),
            *products_by_oem.values(),
            *products_by_historical_gts.values(),
            *products_by_historical_oem.values(),
        ]
    }
    candidates_by_product_id = fetch_quotation_candidates_by_product_id(
        connection,
        product_ids,
    )
    return GenerationLookupContext(
        products_by_gts=products_by_gts,
        products_by_oem=products_by_oem,
        products_by_historical_gts=products_by_historical_gts,
        products_by_historical_oem=products_by_historical_oem,
        candidates_by_product_id=candidates_by_product_id,
    )


def find_product_in_context(
    context: GenerationLookupContext,
    values: dict[str, Any],
) -> tuple[Row | None, bool]:
    gts_no_normalized = values.get("gts_no_normalized") or ""
    oem_normalized = values.get("oem_normalized") or ""
    gts_product = context.products_by_gts.get(
        gts_no_normalized,
    ) or context.products_by_historical_gts.get(gts_no_normalized)
    oem_product = context.products_by_oem.get(
        oem_normalized,
    ) or context.products_by_historical_oem.get(oem_normalized)

    if gts_product and oem_product and gts_product["id"] != oem_product["id"]:
        return None, True
    if gts_product:
        return gts_product, False
    if oem_product:
        return oem_product, False
    return None, False


def fetch_products_by_historical_quotation_field(
    connection: Connection,
    field: str,
    values: list[str],
) -> dict[str, Row]:
    if field not in {"gts_no_normalized", "oem_normalized"}:
        raise ValueError("Unsupported historical quotation lookup field")
    if not values:
        return {}

    placeholders = ", ".join("?" for _ in values)
    rows = connection.execute(
        f"""
        SELECT
            q.{field} AS lookup_value,
            p.*
        FROM quotation_items q
        JOIN products p ON p.id = q.product_id
        WHERE q.{field} IN ({placeholders})
        ORDER BY q.updated_at DESC, q.id DESC
        """,
        values,
    ).fetchall()
    products = {}
    for row in rows:
        lookup_value = _text(row["lookup_value"])
        if lookup_value and lookup_value not in products:
            products[lookup_value] = row
    return products


def build_product_change_notices(
    product: Row | dict[str, Any],
    request_values: dict[str, Any],
) -> list[str]:
    notices = []
    request_gts = _text(request_values.get("gts_no"))
    request_oem = _text(request_values.get("oem"))
    product_gts = _text(product["gts_no"])
    product_oem = _text(product["oem"])
    if request_gts and request_values.get("gts_no_normalized") != product["gts_no_normalized"]:
        notices.append(f"GTS 已从 {request_gts} 改为 {product_gts or '(空)'}")
    if request_oem and request_values.get("oem_normalized") != product["oem_normalized"]:
        notices.append(f"OEM 已从 {request_oem} 改为 {product_oem or '(空)'}")
    return notices


def fetch_quotation_candidates_by_product_id(
    connection: Connection,
    product_ids: set[int],
) -> dict[int, list[Row]]:
    if not product_ids:
        return {}

    ordered_ids = sorted(product_ids)
    placeholders = ", ".join("?" for _ in ordered_ids)
    if supplier_link_available(connection):
        supplier_select = """
            COALESCE(
                NULLIF(TRIM(s.supplier_short_name), ''),
                NULLIF(TRIM(s.supplier_full_name), '')
            ) AS supplier_display_name
        """
        supplier_join = "LEFT JOIN suppliers s ON s.id = q.supplier_id"
    else:
        supplier_select = "NULL AS supplier_display_name"
        supplier_join = ""
    rows = connection.execute(
        f"""
        SELECT
            q.*,
            {supplier_select}
        FROM quotation_items q
        {supplier_join}
        WHERE q.product_id IN ({placeholders})
        ORDER BY product_id, updated_at DESC, id DESC
        """,
        ordered_ids,
    ).fetchall()

    grouped_rows: dict[int, list[Row]] = {}
    for row in rows:
        grouped_rows.setdefault(int(row["product_id"]), []).append(row)

    return {
        product_id: dedupe_candidate_rows(product_rows)
        for product_id, product_rows in grouped_rows.items()
    }


def dedupe_candidate_rows(rows: list[Row]) -> list[Row]:
    candidates = []
    seen = set()
    for row in rows:
        signature = (
            _text(row["gts_no_normalized"]),
            _text(row["factory"]),
            _text(row["unit"]),
            _price_key(row["unit_price"]),
        )
        if signature in seen:
            continue
        seen.add(signature)
        candidates.append(row)
    return candidates


def _price_key(value: Any) -> str:
    if value in ("", None):
        return ""
    return f"{float(value):.4f}"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
