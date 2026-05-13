from __future__ import annotations

from sqlite3 import Connection, Row


def build_data_quality_report(connection: Connection) -> dict[str, list[Row]]:
    return {
        "missing_hs_code": fetch_products_missing_field(connection, "hs_code"),
        "missing_oem": fetch_products_missing_field(connection, "oem"),
        "missing_description": fetch_products_missing_field(connection, "description"),
        "without_quotation": fetch_products_without_quotation(connection),
    }


def fetch_products_missing_field(connection: Connection, field: str) -> list[Row]:
    if field not in {"hs_code", "oem", "description"}:
        raise ValueError("Unsupported data quality field")
    return connection.execute(
        f"""
        SELECT
            id,
            gts_no,
            oem,
            description,
            chinese_description,
            hs_code,
            updated_by,
            updated_at
        FROM products
        WHERE {field} IS NULL
           OR TRIM({field}) = ''
        ORDER BY updated_at DESC, id DESC
        """
    ).fetchall()


def fetch_products_without_quotation(connection: Connection) -> list[Row]:
    return connection.execute(
        """
        SELECT
            p.id,
            p.gts_no,
            p.oem,
            p.description,
            p.chinese_description,
            p.hs_code,
            p.updated_by,
            p.updated_at
        FROM products p
        LEFT JOIN quotation_items q ON q.product_id = p.id
        WHERE q.id IS NULL
        ORDER BY p.updated_at DESC, p.id DESC
        """
    ).fetchall()
