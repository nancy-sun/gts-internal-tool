from __future__ import annotations

import sqlite3
from sqlite3 import Connection, Row
from typing import Any

from app.services.operation_logging import create_operation_log, utc_now_text


SUPPLIER_FIELDS = (
    "supplier_name",
    "contact_person",
    "phone",
    "wechat",
    "city",
    "province",
    "product_scope",
    "factory_or_trader",
    "quality_level",
    "price_level",
    "notes",
)


def normalize_supplier_name(value: Any) -> str:
    if value is None:
        return ""
    return "".join(
        character.upper()
        for character in str(value).strip()
        if character.isalnum()
    )


def list_suppliers(
    connection: Connection,
    *,
    query: str = "",
    limit: int = 200,
) -> list[Row]:
    clean_query = query.strip()
    if not clean_query:
        return connection.execute(
            """
            SELECT *
            FROM suppliers
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    normalized_query = normalize_supplier_name(clean_query)
    like_query = f"%{clean_query}%"
    normalized_like_query = f"%{normalized_query}%"
    return connection.execute(
        """
        SELECT *
        FROM suppliers
        WHERE supplier_name_normalized LIKE ?
           OR supplier_name LIKE ?
           OR city LIKE ?
           OR product_scope LIKE ?
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (
            normalized_like_query,
            like_query,
            like_query,
            like_query,
            limit,
        ),
    ).fetchall()


def get_supplier(connection: Connection, supplier_id: int) -> Row | None:
    return connection.execute(
        "SELECT * FROM suppliers WHERE id = ?",
        (supplier_id,),
    ).fetchone()


def find_supplier_by_name(connection: Connection, supplier_name: str) -> Row | None:
    normalized_name = normalize_supplier_name(supplier_name)
    if not normalized_name:
        return None
    try:
        return connection.execute(
            """
            SELECT *
            FROM suppliers
            WHERE supplier_name_normalized = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (normalized_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None


def supplier_link_available(connection: Connection) -> bool:
    supplier_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(suppliers)").fetchall()
    }
    if not supplier_columns:
        return False
    quotation_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(quotation_items)").fetchall()
    }
    return "supplier_id" in quotation_columns


def create_supplier(
    connection: Connection,
    *,
    values: dict[str, Any],
    operator_name: str,
) -> int:
    supplier_name = _text(values.get("supplier_name"))
    now = utc_now_text()
    cursor = connection.execute(
        """
        INSERT INTO suppliers (
            supplier_name,
            supplier_name_normalized,
            contact_person,
            phone,
            wechat,
            city,
            province,
            product_scope,
            factory_or_trader,
            quality_level,
            price_level,
            notes,
            created_by,
            created_at,
            updated_by,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            supplier_name,
            normalize_supplier_name(supplier_name),
            _text(values.get("contact_person")),
            _text(values.get("phone")),
            _text(values.get("wechat")),
            _text(values.get("city")),
            _text(values.get("province")),
            _text(values.get("product_scope")),
            _text(values.get("factory_or_trader")),
            _text(values.get("quality_level")),
            _text(values.get("price_level")),
            _text(values.get("notes")),
            operator_name,
            now,
            operator_name,
            now,
        ),
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="create_supplier",
        row_count=1,
        note=f"供应商={supplier_name}",
    )
    return int(cursor.lastrowid)


def update_supplier(
    connection: Connection,
    *,
    supplier_id: int,
    values: dict[str, Any],
    operator_name: str,
) -> None:
    supplier_name = _text(values.get("supplier_name"))
    now = utc_now_text()
    connection.execute(
        """
        UPDATE suppliers
        SET supplier_name = ?,
            supplier_name_normalized = ?,
            contact_person = ?,
            phone = ?,
            wechat = ?,
            city = ?,
            province = ?,
            product_scope = ?,
            factory_or_trader = ?,
            quality_level = ?,
            price_level = ?,
            notes = ?,
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            supplier_name,
            normalize_supplier_name(supplier_name),
            _text(values.get("contact_person")),
            _text(values.get("phone")),
            _text(values.get("wechat")),
            _text(values.get("city")),
            _text(values.get("province")),
            _text(values.get("product_scope")),
            _text(values.get("factory_or_trader")),
            _text(values.get("quality_level")),
            _text(values.get("price_level")),
            _text(values.get("notes")),
            operator_name,
            now,
            supplier_id,
        ),
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="edit_supplier",
        row_count=1,
        note=f"供应商={supplier_name}",
    )


def supplier_form_values(form_values: dict[str, Any] | Row | None = None) -> dict[str, str]:
    source = form_values or {}
    return {
        field: _text(source[field] if isinstance(source, Row) and field in source.keys() else source.get(field))
        for field in SUPPLIER_FIELDS
    }


def validate_supplier_values(values: dict[str, Any], operator_name: str) -> list[str]:
    errors = []
    if not operator_name.strip():
        errors.append("请填写操作人。")
    if not _text(values.get("supplier_name")):
        errors.append("请填写供应商名称。")
    return errors


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
