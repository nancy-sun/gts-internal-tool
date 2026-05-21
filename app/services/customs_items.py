from __future__ import annotations

from sqlite3 import Connection, Row
from typing import Any

from app.services.operation_logging import create_operation_log, utc_now_text


UNIT_SOURCES = (
    "quantity",
    "gross_weight",
    "net_weight",
    "volume",
    "package_count",
    "manual",
)

UNIT_SOURCE_LABELS = {
    "quantity": "数量",
    "gross_weight": "毛重",
    "net_weight": "净重",
    "volume": "体积",
    "package_count": "件数",
    "manual": "手动填写",
}

DECIMAL_PLACE_OPTIONS = (0, 1, 2, 3)


def can_manage_customs_master_data(user: Row | None) -> bool:
    return bool(user and user["role"] in {"admin", "merchandiser"})


def unit_source_label(value: str | None) -> str:
    return UNIT_SOURCE_LABELS.get(str(value or ""), str(value or ""))


def customs_item_form_values(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "customs_name_cn": _clean_text(raw.get("customs_name_cn")),
        "customs_name_en": _clean_text(raw.get("customs_name_en")),
        "hs_code": _clean_text(raw.get("hs_code")),
        "unit_1": _clean_text(raw.get("unit_1")),
        "unit_1_source": _clean_text(raw.get("unit_1_source")),
        "unit_1_decimal_places": _clean_decimal_text(
            raw.get("unit_1_decimal_places"),
            default="0",
        ),
        "unit_2": _clean_text(raw.get("unit_2")),
        "unit_2_source": _clean_text(raw.get("unit_2_source")),
        "unit_2_decimal_places": _clean_decimal_text(raw.get("unit_2_decimal_places")),
        "declaration_element_template": _clean_text(raw.get("declaration_element_template")),
        "notes": _clean_text(raw.get("notes")),
    }


def customs_item_values_from_db(item: Row | None) -> dict[str, Any]:
    if not item:
        return customs_item_form_values()
    values = customs_item_form_values(dict(item))
    values["unit_1_decimal_places"] = str(item["unit_1_decimal_places"])
    values["unit_2_decimal_places"] = (
        "" if item["unit_2_decimal_places"] is None else str(item["unit_2_decimal_places"])
    )
    return values


def list_customs_items(
    connection: Connection,
    *,
    query: str = "",
    status: str = "active",
) -> list[Row]:
    conditions = []
    params: list[Any] = []
    clean_query = query.strip()
    if clean_query:
        conditions.append("(lower(customs_name_cn) LIKE lower(?) OR lower(hs_code) LIKE lower(?))")
        like_query = f"%{clean_query}%"
        params.extend([like_query, like_query])
    if status == "active":
        conditions.append("is_active = 1")
    elif status == "inactive":
        conditions.append("is_active = 0")
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return connection.execute(
        f"""
        SELECT *
        FROM customs_items
        {where_sql}
        ORDER BY is_active DESC, updated_at DESC, id DESC
        """,
        params,
    ).fetchall()


def get_customs_item(connection: Connection, item_id: int) -> Row | None:
    return connection.execute(
        "SELECT * FROM customs_items WHERE id = ?",
        (item_id,),
    ).fetchone()


def create_customs_item(
    connection: Connection,
    *,
    values: dict[str, Any],
    user_id: int | None,
    operator_name: str,
) -> int:
    now = utc_now_text()
    cursor = connection.execute(
        """
        INSERT INTO customs_items (
            customs_name_cn,
            customs_name_en,
            hs_code,
            unit_1,
            unit_1_source,
            unit_1_decimal_places,
            unit_2,
            unit_2_source,
            unit_2_decimal_places,
            declaration_element_template,
            notes,
            is_active,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """,
        (
            values["customs_name_cn"],
            values["customs_name_en"],
            values["hs_code"],
            values["unit_1"],
            values["unit_1_source"],
            int(values["unit_1_decimal_places"]),
            values["unit_2"] or None,
            values["unit_2_source"] or None,
            _optional_decimal_places(values["unit_2_decimal_places"]),
            values["declaration_element_template"],
            values["notes"],
            user_id,
            user_id,
            now,
            now,
        ),
    )
    item_id = int(cursor.lastrowid)
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="customs_item_created",
        note=customs_item_log_note(values),
    )
    return item_id


def update_customs_item(
    connection: Connection,
    *,
    item_id: int,
    values: dict[str, Any],
    user_id: int | None,
    operator_name: str,
) -> None:
    connection.execute(
        """
        UPDATE customs_items
        SET customs_name_cn = ?,
            customs_name_en = ?,
            hs_code = ?,
            unit_1 = ?,
            unit_1_source = ?,
            unit_1_decimal_places = ?,
            unit_2 = ?,
            unit_2_source = ?,
            unit_2_decimal_places = ?,
            declaration_element_template = ?,
            notes = ?,
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            values["customs_name_cn"],
            values["customs_name_en"],
            values["hs_code"],
            values["unit_1"],
            values["unit_1_source"],
            int(values["unit_1_decimal_places"]),
            values["unit_2"] or None,
            values["unit_2_source"] or None,
            _optional_decimal_places(values["unit_2_decimal_places"]),
            values["declaration_element_template"],
            values["notes"],
            user_id,
            utc_now_text(),
            item_id,
        ),
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="customs_item_updated",
        note=customs_item_log_note(values),
    )


def set_customs_item_active(
    connection: Connection,
    *,
    item_id: int,
    is_active: bool,
    user_id: int | None,
    operator_name: str,
) -> None:
    item = get_customs_item(connection, item_id)
    connection.execute(
        """
        UPDATE customs_items
        SET is_active = ?,
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (1 if is_active else 0, user_id, utc_now_text(), item_id),
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="customs_item_activated" if is_active else "customs_item_deactivated",
        note=customs_item_log_note(item or {}),
    )


def validate_customs_item_values(
    connection: Connection,
    values: dict[str, Any],
    *,
    item_id: int | None = None,
) -> list[str]:
    errors = []
    if not values["customs_name_cn"]:
        errors.append("请填写报关中文品名。")
    if not values["hs_code"]:
        errors.append("请填写 HS Code。")
    if not values["unit_1"]:
        errors.append("请填写第一单位。")
    if not values["unit_1_source"]:
        errors.append("请选择第一单位来源。")
    elif values["unit_1_source"] not in UNIT_SOURCES:
        errors.append("请选择有效的第一单位来源。")
    if not valid_decimal_places(values["unit_1_decimal_places"]):
        errors.append("第一单位小数位必须是 0、1、2 或 3。")

    has_unit_2 = bool(values["unit_2"])
    has_unit_2_source = bool(values["unit_2_source"])
    if has_unit_2 and not has_unit_2_source:
        errors.append("填写第二单位时必须选择第二单位来源。")
    if has_unit_2_source and not has_unit_2:
        errors.append("选择第二单位来源时必须填写第二单位。")
    if has_unit_2_source and values["unit_2_source"] not in UNIT_SOURCES:
        errors.append("请选择有效的第二单位来源。")
    if has_unit_2 and not valid_decimal_places(values["unit_2_decimal_places"]):
        errors.append("第二单位小数位必须是 0、1、2 或 3。")

    if values["customs_name_cn"] and values["hs_code"]:
        duplicate = find_duplicate_active_item(
            connection,
            customs_name_cn=values["customs_name_cn"],
            hs_code=values["hs_code"],
            item_id=item_id,
        )
        if duplicate:
            errors.append("已存在相同 HS Code 和报关中文品名的启用记录。")
    return errors


def find_duplicate_active_item(
    connection: Connection,
    *,
    customs_name_cn: str,
    hs_code: str,
    item_id: int | None = None,
) -> Row | None:
    params: list[Any] = [customs_name_cn.strip(), hs_code.strip()]
    exclude_sql = ""
    if item_id is not None:
        exclude_sql = "AND id != ?"
        params.append(item_id)
    return connection.execute(
        f"""
        SELECT *
        FROM customs_items
        WHERE customs_name_cn = ?
          AND hs_code = ?
          AND is_active = 1
          {exclude_sql}
        LIMIT 1
        """,
        params,
    ).fetchone()


def valid_decimal_places(value: Any) -> bool:
    try:
        return int(str(value)) in DECIMAL_PLACE_OPTIONS
    except (TypeError, ValueError):
        return False


def customs_item_log_note(values: Any) -> str:
    if hasattr(values, "keys"):
        name = values["customs_name_cn"] if "customs_name_cn" in values.keys() else ""
        hs_code = values["hs_code"] if "hs_code" in values.keys() else ""
    else:
        name = ""
        hs_code = ""
    return f"{name} / {hs_code}".strip(" /")


def _optional_decimal_places(value: Any) -> int | None:
    if value in ("", None):
        return None
    return int(value)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_decimal_text(value: Any, *, default: str = "") -> str:
    cleaned = _clean_text(value)
    return cleaned if cleaned else default
