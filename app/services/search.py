from sqlite3 import Connection, Row
from typing import Any

from app.services.normalization import normalize_gts_no, normalize_oem


SEARCH_FIELDS = {
    "gts_no": "p.gts_no_normalized",
    "oem": "p.oem_normalized",
    "description": "p.description",
    "chinese_description": "p.chinese_description",
    "factory": "q.factory",
}


def search_catalogue(
    connection: Connection,
    *,
    field: str,
    query: str,
    limit: int = 100,
) -> tuple[list[Row], list[str]]:
    clean_query = query.strip()
    if not clean_query:
        return [], []

    warnings: list[str] = []
    selected_field = SEARCH_FIELDS.get(field, "p.gts_no_normalized")

    if field == "gts_no":
        search_value, warnings = normalize_gts_no(clean_query)
    elif field == "oem":
        search_value, warnings = normalize_oem(clean_query)
    else:
        search_value = clean_query

    if not search_value:
        return [], warnings

    rows = connection.execute(
        f"""
        SELECT
            p.id AS product_id,
            p.gts_no AS product_gts_no,
            p.oem AS product_oem,
            p.description AS product_description,
            p.chinese_description AS product_chinese_description,
            p.hs_code AS product_hs_code,
            q.id AS quotation_item_id,
            q.factory,
            q.unit_price,
            q.packaging,
            q.expected_delivery,
            q.comment,
            q.updated_by,
            q.updated_at,
            CASE
                WHEN {selected_field} = ? THEN 0
                WHEN {selected_field} LIKE ? THEN 1
                ELSE 2
            END AS search_rank,
            ABS(LENGTH({selected_field}) - LENGTH(?)) AS length_gap
        FROM products p
        LEFT JOIN quotation_items q ON q.product_id = p.id
        WHERE {selected_field} LIKE ?
        ORDER BY search_rank ASC, length_gap ASC, p.updated_at DESC, q.updated_at DESC, p.id DESC, q.id DESC
        LIMIT ?
        """,
        (search_value, f"{search_value}%", search_value, f"%{search_value}%", limit),
    ).fetchall()
    if rows and rows[0]["search_rank"] == 0:
        return [row for row in rows if row["search_rank"] == 0], warnings
    return rows, warnings


def group_search_results(rows: list[Row]) -> list[dict[str, Any]]:
    grouped_results: list[dict[str, Any]] = []
    products_by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        product_id = int(row["product_id"])
        product = products_by_id.get(product_id)
        if not product:
            product = {
                "product_id": product_id,
                "gts_no": row["product_gts_no"],
                "oem": row["product_oem"],
                "description": row["product_description"],
                "chinese_description": row["product_chinese_description"],
                "hs_code": row["product_hs_code"],
                "quotations": [],
            }
            products_by_id[product_id] = product
            grouped_results.append(product)

        if row["quotation_item_id"] is not None:
            product["quotations"].append(
                {
                    "quotation_item_id": row["quotation_item_id"],
                    "factory": row["factory"],
                    "unit_price": row["unit_price"],
                    "packaging": row["packaging"],
                    "expected_delivery": row["expected_delivery"],
                    "comment": row["comment"],
                    "updated_by": row["updated_by"],
                    "updated_at": row["updated_at"],
                }
            )
    return grouped_results
