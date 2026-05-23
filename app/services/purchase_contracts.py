from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from sqlite3 import Connection, Row
from typing import Any

from app.services.operation_logging import create_operation_log, utc_now_text
from app.services.suppliers import supplier_display_name


CONTRACT_STATUSES = ("draft", "confirmed", "sent", "completed", "cancelled")
CONTRACT_STATUS_LABELS = {
    "draft": "草稿",
    "confirmed": "已确认",
    "sent": "已发送",
    "completed": "已完成",
    "cancelled": "已取消",
}
MANAGE_PURCHASE_CONTRACT_ROLES = {"admin", "merchandiser"}


def can_manage_purchase_contracts(user: Row | None) -> bool:
    return bool(user and user["role"] in MANAGE_PURCHASE_CONTRACT_ROLES)


def contract_status_label(status: str | None) -> str:
    return CONTRACT_STATUS_LABELS.get(str(status or ""), str(status or ""))


def contract_form_values(raw: dict[str, Any] | None = None) -> dict[str, str]:
    raw = raw or {}
    return {
        "contract_no": _clean_text(raw.get("contract_no")),
        "supplier_id": _clean_text(raw.get("supplier_id")),
        "status": _clean_text(raw.get("status")) or "draft",
        "notes": _clean_text(raw.get("notes")),
    }


def contract_values_from_db(contract: Row | None) -> dict[str, str]:
    if not contract:
        return contract_form_values()
    return contract_form_values(dict(contract))


def item_form_values(raw: dict[str, Any] | None = None) -> dict[str, str]:
    raw = raw or {}
    return {
        "product_id": _clean_text(raw.get("product_id")),
        "quotation_item_id": _clean_text(raw.get("quotation_item_id")),
        "gts_no": _clean_text(raw.get("gts_no")),
        "oem": _clean_text(raw.get("oem")),
        "description_cn": _clean_text(raw.get("description_cn")),
        "description_en": _clean_text(raw.get("description_en")),
        "quantity": _clean_text(raw.get("quantity")),
        "unit": _clean_text(raw.get("unit")),
        "unit_price_rmb": _clean_text(raw.get("unit_price_rmb")),
        "gross_weight": _clean_text(raw.get("gross_weight")),
        "packages": _clean_text(raw.get("packages")),
        "volume": _clean_text(raw.get("volume")),
        "notes": _clean_text(raw.get("notes")),
    }


def list_purchase_contracts(
    connection: Connection,
    *,
    query: str = "",
    status: str = "all",
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = []
    clean_query = query.strip()
    if clean_query:
        like_query = f"%{clean_query}%"
        conditions.append(
            """
            (
                lower(pc.contract_no) LIKE lower(?)
                OR lower(COALESCE(s.supplier_full_name, '')) LIKE lower(?)
                OR lower(COALESCE(s.supplier_short_name, '')) LIKE lower(?)
                OR lower(COALESCE(s.aliases_text, '')) LIKE lower(?)
            )
            """
        )
        params.extend([like_query] * 4)
    if status in CONTRACT_STATUSES:
        conditions.append("pc.status = ?")
        params.append(status)
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = connection.execute(
        f"""
        SELECT
            pc.*,
            s.supplier_full_name,
            s.supplier_short_name,
            COUNT(pci.id) AS item_count
        FROM purchase_contracts pc
        JOIN suppliers s ON s.id = pc.supplier_id
        LEFT JOIN purchase_contract_items pci ON pci.purchase_contract_id = pc.id
        {where_sql}
        GROUP BY
            pc.id,
            s.supplier_full_name,
            s.supplier_short_name
        ORDER BY pc.updated_at DESC, pc.id DESC
        """,
        params,
    ).fetchall()
    return [_contract_display_row(row) for row in rows]


def get_purchase_contract(connection: Connection, contract_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
            pc.*,
            s.supplier_full_name,
            s.supplier_short_name,
            s.aliases_text
        FROM purchase_contracts pc
        JOIN suppliers s ON s.id = pc.supplier_id
        WHERE pc.id = ?
        """,
        (contract_id,),
    ).fetchone()
    return _contract_display_row(row) if row else None


def get_purchase_contract_item(connection: Connection, item_id: int) -> Row | None:
    return connection.execute(
        "SELECT * FROM purchase_contract_items WHERE id = ?",
        (item_id,),
    ).fetchone()


def list_purchase_contract_items(connection: Connection, contract_id: int) -> list[Row]:
    return connection.execute(
        """
        SELECT *
        FROM purchase_contract_items
        WHERE purchase_contract_id = ?
        ORDER BY id
        """,
        (contract_id,),
    ).fetchall()


def list_contract_options(connection: Connection) -> tuple[list[Row], list[Row]]:
    suppliers = connection.execute(
        """
        SELECT id, supplier_full_name, supplier_short_name, aliases_text
        FROM suppliers
        ORDER BY supplier_short_name, supplier_full_name, id
        """
    ).fetchall()
    products = connection.execute(
        """
        SELECT id, gts_no, oem, description, chinese_description
        FROM products
        ORDER BY COALESCE(gts_no, ''), id
        """
    ).fetchall()
    return suppliers, products


def validate_contract_values(
    connection: Connection,
    values: dict[str, str],
    *,
    contract_id: int | None = None,
) -> list[str]:
    errors = []
    if not values["contract_no"]:
        errors.append("请填写合同号。")
    if not _get_supplier(connection, _to_int(values["supplier_id"])):
        errors.append("请选择供应商。")
    if values["status"] not in CONTRACT_STATUSES:
        errors.append("请选择有效的合同状态。")
    duplicate = connection.execute(
        """
        SELECT id
        FROM purchase_contracts
        WHERE contract_no = ?
          AND (? IS NULL OR id != ?)
        LIMIT 1
        """,
        (values["contract_no"], contract_id, contract_id),
    ).fetchone()
    if duplicate:
        errors.append("合同号已存在。")
    return errors


def create_purchase_contract(
    connection: Connection,
    *,
    values: dict[str, str],
    user_id: int | None,
    operator_name: str,
) -> int:
    now = utc_now_text()
    cursor = connection.execute(
        """
        INSERT INTO purchase_contracts (
            contract_no,
            supplier_id,
            status,
            currency,
            total_rmb,
            notes,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, 'RMB', 0, ?, ?, ?, ?, ?)
        """,
        (
            values["contract_no"],
            int(values["supplier_id"]),
            values["status"],
            values["notes"],
            user_id,
            user_id,
            now,
            now,
        ),
    )
    contract_id = int(cursor.lastrowid)
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="purchase_contract_created",
        note=_contract_log_note(connection, contract_id),
    )
    return contract_id


def update_purchase_contract(
    connection: Connection,
    *,
    contract_id: int,
    values: dict[str, str],
    user_id: int | None,
    operator_name: str,
) -> None:
    connection.execute(
        """
        UPDATE purchase_contracts
        SET contract_no = ?,
            supplier_id = ?,
            status = ?,
            notes = ?,
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            values["contract_no"],
            int(values["supplier_id"]),
            values["status"],
            values["notes"],
            user_id,
            utc_now_text(),
            contract_id,
        ),
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="purchase_contract_updated",
        note=_contract_log_note(connection, contract_id),
    )


def cancel_purchase_contract(
    connection: Connection,
    *,
    contract_id: int,
    user_id: int | None,
    operator_name: str,
) -> None:
    connection.execute(
        """
        UPDATE purchase_contracts
        SET status = 'cancelled',
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (user_id, utc_now_text(), contract_id),
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="purchase_contract_cancelled",
        note=_contract_log_note(connection, contract_id),
    )


def validate_item_values(values: dict[str, str]) -> list[str]:
    errors = []
    if values["quantity"] and _positive_int(values["quantity"]) is None:
        errors.append("数量必须是正整数。")
    if values["unit_price_rmb"] and _nonnegative_decimal(values["unit_price_rmb"]) is None:
        errors.append("人民币单价必须大于或等于 0。")
    if values["packages"] and _nonnegative_int(values["packages"]) is None:
        errors.append("件数必须大于或等于 0。")
    if values["gross_weight"] and _nonnegative_decimal(values["gross_weight"]) is None:
        errors.append("毛重必须大于或等于 0。")
    if values["volume"] and _nonnegative_decimal(values["volume"]) is None:
        errors.append("体积必须大于或等于 0。")
    return errors


def add_purchase_contract_item(
    connection: Connection,
    *,
    contract_id: int,
    values: dict[str, str],
    operator_name: str,
) -> int:
    contract = get_purchase_contract(connection, contract_id)
    prepared = prepare_item_values(connection, contract, values)
    now = utc_now_text()
    cursor = connection.execute(
        """
        INSERT INTO purchase_contract_items (
            purchase_contract_id,
            product_id,
            quotation_item_id,
            supplier_id,
            gts_no,
            oem,
            description_cn,
            description_en,
            quantity,
            unit,
            unit_price_rmb,
            amount_rmb,
            gross_weight,
            packages,
            volume,
            notes,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contract_id,
            prepared["product_id"],
            prepared["quotation_item_id"],
            prepared["supplier_id"],
            prepared["gts_no"],
            prepared["oem"],
            prepared["description_cn"],
            prepared["description_en"],
            prepared["quantity"],
            prepared["unit"],
            prepared["unit_price_rmb"],
            prepared["amount_rmb"],
            prepared["gross_weight"],
            prepared["packages"],
            prepared["volume"],
            prepared["notes"],
            now,
            now,
        ),
    )
    item_id = int(cursor.lastrowid)
    recalculate_contract_total(connection, contract_id)
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="purchase_contract_item_added",
        note=_contract_log_note(connection, contract_id),
    )
    return item_id


def update_purchase_contract_item(
    connection: Connection,
    *,
    contract_id: int,
    item_id: int,
    values: dict[str, str],
    operator_name: str,
) -> None:
    contract = get_purchase_contract(connection, contract_id)
    prepared = prepare_item_values(connection, contract, values)
    connection.execute(
        """
        UPDATE purchase_contract_items
        SET product_id = ?,
            quotation_item_id = ?,
            supplier_id = ?,
            gts_no = ?,
            oem = ?,
            description_cn = ?,
            description_en = ?,
            quantity = ?,
            unit = ?,
            unit_price_rmb = ?,
            amount_rmb = ?,
            gross_weight = ?,
            packages = ?,
            volume = ?,
            notes = ?,
            updated_at = ?
        WHERE id = ?
          AND purchase_contract_id = ?
        """,
        (
            prepared["product_id"],
            prepared["quotation_item_id"],
            prepared["supplier_id"],
            prepared["gts_no"],
            prepared["oem"],
            prepared["description_cn"],
            prepared["description_en"],
            prepared["quantity"],
            prepared["unit"],
            prepared["unit_price_rmb"],
            prepared["amount_rmb"],
            prepared["gross_weight"],
            prepared["packages"],
            prepared["volume"],
            prepared["notes"],
            utc_now_text(),
            item_id,
            contract_id,
        ),
    )
    recalculate_contract_total(connection, contract_id)
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="purchase_contract_item_updated",
        note=_contract_log_note(connection, contract_id),
    )


def delete_purchase_contract_item(
    connection: Connection,
    *,
    contract_id: int,
    item_id: int,
    operator_name: str,
) -> None:
    connection.execute(
        """
        DELETE FROM purchase_contract_items
        WHERE id = ?
          AND purchase_contract_id = ?
        """,
        (item_id, contract_id),
    )
    recalculate_contract_total(connection, contract_id)
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="purchase_contract_item_deleted",
        note=_contract_log_note(connection, contract_id),
    )


def prepare_item_values(
    connection: Connection,
    contract: dict[str, Any] | None,
    values: dict[str, str],
) -> dict[str, Any]:
    product = _get_product(connection, _to_int(values["product_id"]))
    quotation = latest_quotation_for_contract_supplier(
        connection,
        product_id=int(product["id"]) if product else None,
        supplier_id=int(contract["supplier_id"]) if contract else None,
    )
    quantity = _positive_int(values["quantity"])
    unit_price = _nonnegative_decimal(values["unit_price_rmb"])
    resolved_unit_price = (
        unit_price if unit_price is not None else _decimal_from_row(quotation, "unit_price")
    )
    amount = (
        _money(quantity * resolved_unit_price)
        if quantity is not None and resolved_unit_price is not None
        else None
    )
    return {
        "product_id": int(product["id"]) if product else None,
        "quotation_item_id": _to_int(values["quotation_item_id"]),
        "supplier_id": int(contract["supplier_id"]) if contract else None,
        "gts_no": values["gts_no"] or _row_text(product, "gts_no") or _row_text(quotation, "gts_no"),
        "oem": values["oem"] or _row_text(product, "oem") or _row_text(quotation, "oem"),
        "description_cn": (
            values["description_cn"]
            or _row_text(product, "chinese_description")
            or _row_text(quotation, "chinese_description")
        ),
        "description_en": (
            values["description_en"]
            or _row_text(product, "description")
            or _row_text(quotation, "description")
        ),
        "quantity": quantity,
        "unit": values["unit"] or _row_text(quotation, "unit"),
        "unit_price_rmb": resolved_unit_price,
        "amount_rmb": amount,
        "gross_weight": _nonnegative_decimal(values["gross_weight"])
        if values["gross_weight"]
        else _decimal_from_row(quotation, "gross_weight"),
        "packages": _nonnegative_int(values["packages"])
        if values["packages"]
        else _int_from_row(quotation, "packages"),
        "volume": _nonnegative_decimal(values["volume"])
        if values["volume"]
        else _decimal_from_row(quotation, "measurements_volume"),
        "notes": values["notes"],
    }


def latest_quotation_for_contract_supplier(
    connection: Connection,
    *,
    product_id: int | None,
    supplier_id: int | None,
) -> Row | None:
    if not product_id or not supplier_id:
        return None
    return connection.execute(
        """
        SELECT *
        FROM quotation_items
        WHERE product_id = ?
          AND supplier_id = ?
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        (product_id, supplier_id),
    ).fetchone()


def recalculate_contract_total(connection: Connection, contract_id: int) -> None:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(amount_rmb), 0) AS total
        FROM purchase_contract_items
        WHERE purchase_contract_id = ?
        """,
        (contract_id,),
    ).fetchone()
    total = _money(row["total"] if row else 0)
    connection.execute(
        """
        UPDATE purchase_contracts
        SET total_rmb = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (total, utc_now_text(), contract_id),
    )


def _contract_display_row(row: Row) -> dict[str, Any]:
    values = dict(row)
    values["supplier_display_name"] = supplier_display_name(values)
    values["status_label"] = contract_status_label(values.get("status"))
    return values


def _contract_log_note(connection: Connection, contract_id: int) -> str:
    contract = get_purchase_contract(connection, contract_id)
    if not contract:
        return ""
    return f"{contract['contract_no']} / {contract['supplier_display_name']}"


def _get_supplier(connection: Connection, supplier_id: int | None) -> Row | None:
    if not supplier_id:
        return None
    return connection.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()


def _get_product(connection: Connection, product_id: int | None) -> Row | None:
    if not product_id:
        return None
    return connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def _row_text(row: Row | None, key: str) -> str:
    if not row:
        return ""
    try:
        return _clean_text(row[key])
    except (KeyError, IndexError):
        return ""


def _decimal_from_row(row: Row | None, key: str) -> float | None:
    if not row:
        return None
    try:
        return _nonnegative_decimal(row[key])
    except (KeyError, IndexError):
        return None


def _int_from_row(row: Row | None, key: str) -> int | None:
    if not row:
        return None
    try:
        return _nonnegative_int(row[key])
    except (KeyError, IndexError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _positive_int(value: Any) -> int | None:
    number = _to_int(value)
    return number if number is not None and number > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    number = _to_int(value)
    return number if number is not None and number >= 0 else None


def _nonnegative_decimal(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return float(number) if number >= 0 else None


def _money(value: Any) -> float:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        number = Decimal("0")
    return float(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
