from __future__ import annotations

from sqlite3 import Connection, Row
from typing import Any

from app.services.normalization import normalize_gts_no
from app.services.operation_logging import create_operation_log, utc_now_text


MANAGE_CUSTOMS_MAPPING_ROLES = {"admin", "merchandiser"}
CUSTOMS_MISSING_FIELDS = {
    "hs_code": "缺少 HS Code",
    "declaration_element_template": "缺少申报要素模板",
}
QUOTATION_SOURCE_FIELDS = {"gross_weight", "packages"}


def can_manage_customs_mapping(user: Row | None) -> bool:
    return bool(user and user["role"] in MANAGE_CUSTOMS_MAPPING_ROLES)


def mapping_form_values(raw: dict[str, Any] | None = None) -> dict[str, str]:
    raw = raw or {}
    return {
        "product_id": _clean_text(raw.get("product_id")),
        "customs_item_id": _clean_text(raw.get("customs_item_id")),
        "part_no_for_declaration": _clean_text(raw.get("part_no_for_declaration")),
        "model_for_declaration": _clean_text(raw.get("model_for_declaration")),
        "material": _clean_text(raw.get("material")),
        "brand": _clean_text(raw.get("brand")),
        "declaration_notes": _clean_text(raw.get("declaration_notes")),
    }


def mapping_values_from_db(mapping: Row | None) -> dict[str, str]:
    if not mapping:
        return mapping_form_values()
    return mapping_form_values(dict(mapping))


def list_mapping_options(connection: Connection) -> tuple[list[Row], list[Row]]:
    products = connection.execute(
        """
        SELECT id, gts_no, oem, description, chinese_description
        FROM products
        ORDER BY COALESCE(gts_no, ''), id
        """
    ).fetchall()
    customs_items = connection.execute(
        """
        SELECT id, customs_name_cn, hs_code, unit_1, unit_2
        FROM customs_items
        WHERE is_active = 1
        ORDER BY customs_name_cn, hs_code, id
        """
    ).fetchall()
    return products, customs_items


def list_product_customs_mappings(connection: Connection, *, query: str = "") -> list[Row]:
    conditions = []
    params: list[Any] = []
    clean_query = query.strip()
    if clean_query:
        like_query = f"%{clean_query}%"
        conditions.append(
            """
            (
                lower(p.gts_no) LIKE lower(?)
                OR lower(p.oem) LIKE lower(?)
                OR lower(p.description) LIKE lower(?)
                OR lower(p.chinese_description) LIKE lower(?)
                OR lower(ci.customs_name_cn) LIKE lower(?)
                OR lower(ci.hs_code) LIKE lower(?)
            )
            """
        )
        params.extend([like_query] * 6)
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return connection.execute(
        f"""
        SELECT
            pcm.*,
            p.gts_no AS product_gts_no,
            p.oem AS product_oem,
            p.description AS product_description,
            p.chinese_description AS product_chinese_description,
            ci.customs_name_cn,
            ci.hs_code,
            ci.unit_1,
            ci.unit_1_source,
            ci.unit_2,
            ci.unit_2_source
        FROM product_customs_mappings pcm
        JOIN products p ON p.id = pcm.product_id
        JOIN customs_items ci ON ci.id = pcm.customs_item_id
        {where_sql}
        ORDER BY pcm.updated_at DESC, pcm.id DESC
        """,
        params,
    ).fetchall()


def get_product_customs_mapping(connection: Connection, mapping_id: int) -> Row | None:
    return connection.execute(
        """
        SELECT
            pcm.*,
            p.gts_no AS product_gts_no,
            p.oem AS product_oem,
            p.description AS product_description,
            ci.customs_name_cn,
            ci.hs_code
        FROM product_customs_mappings pcm
        JOIN products p ON p.id = pcm.product_id
        JOIN customs_items ci ON ci.id = pcm.customs_item_id
        WHERE pcm.id = ?
        """,
        (mapping_id,),
    ).fetchone()


def get_product_customs_mapping_by_product(connection: Connection, product_id: int) -> Row | None:
    return connection.execute(
        "SELECT * FROM product_customs_mappings WHERE product_id = ?",
        (product_id,),
    ).fetchone()


def validate_mapping_values(connection: Connection, values: dict[str, str]) -> list[str]:
    errors = []
    product = _get_product(connection, _to_int(values["product_id"]))
    customs_item = _get_customs_item(connection, _to_int(values["customs_item_id"]))
    if not product:
        errors.append("请选择产品。")
    if not customs_item:
        errors.append("请选择报关资料。")
    return errors


def upsert_product_customs_mapping(
    connection: Connection,
    *,
    values: dict[str, str],
    user_id: int | None,
    operator_name: str,
) -> tuple[int, str]:
    now = utc_now_text()
    product_id = int(values["product_id"])
    customs_item_id = int(values["customs_item_id"])
    product = _get_product(connection, product_id)
    existing = get_product_customs_mapping_by_product(connection, product_id)
    if existing:
        connection.execute(
            """
            UPDATE product_customs_mappings
            SET gts_no = ?,
                customs_item_id = ?,
                part_no_for_declaration = ?,
                model_for_declaration = ?,
                material = ?,
                brand = ?,
                declaration_notes = ?,
                updated_by = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                product["gts_no"] if product else "",
                customs_item_id,
                values["part_no_for_declaration"],
                values["model_for_declaration"],
                values["material"],
                values["brand"],
                values["declaration_notes"],
                user_id,
                now,
                existing["id"],
            ),
        )
        mapping_id = int(existing["id"])
        action_type = "product_customs_mapping_updated"
    else:
        cursor = connection.execute(
            """
            INSERT INTO product_customs_mappings (
                product_id,
                gts_no,
                customs_item_id,
                part_no_for_declaration,
                model_for_declaration,
                material,
                brand,
                declaration_notes,
                created_by,
                updated_by,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                product["gts_no"] if product else "",
                customs_item_id,
                values["part_no_for_declaration"],
                values["model_for_declaration"],
                values["material"],
                values["brand"],
                values["declaration_notes"],
                user_id,
                user_id,
                now,
                now,
            ),
        )
        mapping_id = int(cursor.lastrowid)
        action_type = "product_customs_mapping_created"

    customs_item = _get_customs_item(connection, customs_item_id)
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type=action_type,
        note=_mapping_log_note(product, customs_item),
    )
    return mapping_id, action_type


def build_missing_customs_report(connection: Connection) -> dict[str, list[dict[str, Any]]]:
    mapped_rows = mapped_products(connection)
    return {
        "without_mapping": products_without_mapping(connection),
        "missing_hs_code": mapped_items_missing_field(mapped_rows, "hs_code"),
        "missing_declaration_template": mapped_items_missing_field(
            mapped_rows,
            "declaration_element_template",
        ),
        "gross_weight_issues": unit_source_issues(
            connection,
            mapped_rows,
            source="gross_weight",
        ),
        "package_count_issues": unit_source_issues(
            connection,
            mapped_rows,
            source="package_count",
        ),
        "net_weight_issues": net_weight_issues(connection, mapped_rows),
        "manual_source_warnings": manual_source_warnings(mapped_rows),
    }


def products_without_mapping(connection: Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT p.id, p.gts_no, p.oem, p.description, p.chinese_description
        FROM products p
        LEFT JOIN product_customs_mappings pcm ON pcm.product_id = p.id
        WHERE pcm.id IS NULL
        ORDER BY p.updated_at DESC, p.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def mapped_items_missing_field(
    mapped_rows: list[Row],
    field_name: str,
) -> list[dict[str, Any]]:
    issue = CUSTOMS_MISSING_FIELDS.get(field_name)
    if not issue:
        raise ValueError("Unsupported customs missing field")
    return [
        _issue_row(row, issue)
        for row in mapped_rows
        if not _clean_text(row[field_name])
    ]


def unit_source_issues(
    connection: Connection,
    mapped_rows: list[Row],
    *,
    source: str,
) -> list[dict[str, Any]]:
    rows = [
        row for row in mapped_rows
        if source in _row_unit_sources(row)
    ]
    issues = []
    for row in rows:
        if source == "gross_weight":
            gross_weight = get_latest_gross_weight_for_product(
                connection,
                row["product_id"],
                row["product_gts_no"],
            )
            if gross_weight is None:
                issues.append(_issue_row(row, "缺少毛重"))
        elif source == "package_count":
            packages = get_latest_packages_for_product(
                connection,
                row["product_id"],
                row["product_gts_no"],
            )
            if packages is None:
                issues.append(_issue_row(row, "缺少件数"))
    return issues


def net_weight_issues(connection: Connection, mapped_rows: list[Row]) -> list[dict[str, Any]]:
    rows = [
        row for row in mapped_rows
        if "net_weight" in _row_unit_sources(row)
    ]
    issues = []
    for row in rows:
        gross_weight = get_latest_gross_weight_for_product(
            connection,
            row["product_id"],
            row["product_gts_no"],
        )
        packages = get_latest_packages_for_product(
            connection,
            row["product_id"],
            row["product_gts_no"],
        )
        if gross_weight is None:
            issues.append(_issue_row(row, "净重缺少毛重"))
            continue
        if packages is None:
            issues.append(_issue_row(row, "净重缺少件数"))
            continue
        if gross_weight - packages <= 0:
            issues.append(_issue_row(row, "净重计算错误：毛重 - 件数 必须大于 0。"))
    return issues


def manual_source_warnings(mapped_rows: list[Row]) -> list[dict[str, Any]]:
    return [
        _issue_row(row, "后续报关批次需要手动填写单位数量")
        for row in mapped_rows
        if "manual" in _row_unit_sources(row)
    ]


def mapped_products(connection: Connection) -> list[Row]:
    return connection.execute(
        """
        SELECT
            pcm.id AS mapping_id,
            p.id AS product_id,
            p.gts_no AS product_gts_no,
            p.oem AS product_oem,
            p.description AS product_description,
            ci.id AS customs_item_id,
            ci.customs_name_cn,
            ci.hs_code,
            ci.unit_1,
            ci.unit_1_source,
            ci.unit_2,
            ci.unit_2_source,
            ci.declaration_element_template
        FROM product_customs_mappings pcm
        JOIN products p ON p.id = pcm.product_id
        JOIN customs_items ci ON ci.id = pcm.customs_item_id
        ORDER BY p.gts_no, p.id
        """
    ).fetchall()


def get_latest_gross_weight_for_product(
    connection: Connection,
    product_id: int,
    gts_no: str | None,
) -> float | None:
    return _latest_positive_quotation_value(connection, product_id, gts_no, "gross_weight")


def get_latest_packages_for_product(
    connection: Connection,
    product_id: int,
    gts_no: str | None,
) -> float | None:
    return _latest_positive_quotation_value(connection, product_id, gts_no, "packages")


def _latest_positive_quotation_value(
    connection: Connection,
    product_id: int,
    gts_no: str | None,
    column_name: str,
) -> float | None:
    if column_name not in QUOTATION_SOURCE_FIELDS:
        raise ValueError("Unsupported quotation source field")
    normalized_gts, _ = normalize_gts_no(_clean_text(gts_no))
    row = connection.execute(
        f"""
        SELECT {column_name} AS value
        FROM quotation_items
        WHERE product_id = ?
           OR (? != '' AND gts_no_normalized = ?)
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (product_id, normalized_gts, normalized_gts),
    ).fetchone()
    return _positive_number(row["value"] if row else None)


def _row_unit_sources(row: Row) -> set[str]:
    return {
        source
        for source in (row["unit_1_source"], row["unit_2_source"])
        if source
    }


def _issue_row(row: Row, issue: str) -> dict[str, Any]:
    return {
        "mapping_id": row["mapping_id"],
        "product_id": row["product_id"],
        "gts_no": row["product_gts_no"],
        "oem": row["product_oem"],
        "description": row["product_description"],
        "customs_item_id": row["customs_item_id"],
        "customs_name_cn": row["customs_name_cn"],
        "hs_code": row["hs_code"],
        "unit_1": row["unit_1"],
        "unit_1_source": row["unit_1_source"],
        "unit_2": row["unit_2"],
        "unit_2_source": row["unit_2_source"],
        "issue": issue,
    }


def _mapping_log_note(product: Row | None, customs_item: Row | None) -> str:
    gts_no = product["gts_no"] if product else ""
    customs_name = customs_item["customs_name_cn"] if customs_item else ""
    hs_code = customs_item["hs_code"] if customs_item else ""
    return f"{gts_no} -> {customs_name} / {hs_code}".strip(" /")


def _get_product(connection: Connection, product_id: int | None) -> Row | None:
    if not product_id:
        return None
    return connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def _get_customs_item(connection: Connection, customs_item_id: int | None) -> Row | None:
    if not customs_item_id:
        return None
    return connection.execute(
        "SELECT * FROM customs_items WHERE id = ?",
        (customs_item_id,),
    ).fetchone()


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
