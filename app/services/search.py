from sqlite3 import Connection, Row

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
            q.id AS quotation_item_id,
            q.factory,
            q.unit_price,
            q.packaging,
            q.expected_delivery,
            q.comment,
            q.updated_by,
            q.updated_at
        FROM products p
        LEFT JOIN quotation_items q ON q.product_id = p.id
        WHERE {selected_field} LIKE ?
        ORDER BY p.updated_at DESC, q.updated_at DESC, p.id DESC, q.id DESC
        LIMIT ?
        """,
        (f"%{search_value}%", limit),
    ).fetchall()
    return rows, warnings
