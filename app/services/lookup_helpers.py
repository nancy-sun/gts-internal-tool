from __future__ import annotations

from sqlite3 import Connection, Row
from typing import Iterable, Any


PRODUCT_LOOKUP_FIELDS = {"gts_no_normalized", "oem_normalized"}
PRODUCT_LOOKUP_ORDERS = {"id", "updated_at DESC, id DESC"}


def fetch_products_by_normalized_field(
    connection: Connection,
    field: str,
    values: list[str],
    *,
    order_by: str,
) -> dict[str, Row]:
    if field not in PRODUCT_LOOKUP_FIELDS:
        raise ValueError("Unsupported product lookup field")
    if order_by not in PRODUCT_LOOKUP_ORDERS:
        raise ValueError("Unsupported product lookup order")
    if not values:
        return {}

    placeholders = ", ".join("?" for _ in values)
    rows = connection.execute(
        f"""
        SELECT *
        FROM products
        WHERE {field} IN ({placeholders})
        ORDER BY {order_by}
        """,
        values,
    ).fetchall()

    products = {}
    for row in rows:
        key = text_value(row[field])
        if key and key not in products:
            products[key] = row
    return products


def unique_text_values(values: Iterable[Any]) -> list[str]:
    unique = []
    seen = set()
    for value in values:
        text = text_value(value)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
