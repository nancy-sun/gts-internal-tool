from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection, Row
from typing import Any

from app.services.normalization import normalize_gts_no, normalize_oem
from app.services.operation_logging import create_operation_log, utc_now_text


EDITABLE_PRODUCT_FIELDS = ("gts_no", "oem", "description", "chinese_description", "hs_code")


@dataclass(frozen=True)
class ProductEditResult:
    product: Row | None
    errors: list[str]
    warnings: list[str]


def get_product(connection: Connection, product_id: int) -> Row | None:
    return connection.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (product_id,),
    ).fetchone()


def validate_product_edit(
    connection: Connection,
    *,
    product_id: int,
    values: dict[str, Any],
) -> ProductEditResult:
    product = get_product(connection, product_id)
    errors: list[str] = []
    warnings: list[str] = []
    if not product:
        return ProductEditResult(product=None, errors=["找不到产品。"], warnings=[])

    gts_no = clean_text(values.get("gts_no"))
    oem = clean_text(values.get("oem"))
    gts_no_normalized, gts_warnings = normalize_gts_no(gts_no)
    oem_normalized, oem_warnings = normalize_oem(oem)
    warnings.extend([f"GTS {warning}" for warning in gts_warnings])
    warnings.extend([f"OEM {warning}" for warning in oem_warnings])

    if gts_no_normalized and normalized_value_exists(
        connection,
        product_id=product_id,
        field="gts_no_normalized",
        value=gts_no_normalized,
    ):
        errors.append("这个 GTS 已经属于另一个产品，不能保存。")
    if oem_normalized and normalized_value_exists(
        connection,
        product_id=product_id,
        field="oem_normalized",
        value=oem_normalized,
    ):
        errors.append("这个 OEM 已经属于另一个产品，不能保存。")

    return ProductEditResult(product=product, errors=errors, warnings=warnings)


def update_product(
    connection: Connection,
    *,
    product_id: int,
    values: dict[str, Any],
    operator_name: str,
) -> ProductEditResult:
    validation = validate_product_edit(
        connection,
        product_id=product_id,
        values=values,
    )
    if validation.errors or not validation.product:
        return validation

    gts_no = clean_text(values.get("gts_no"))
    oem = clean_text(values.get("oem"))
    description = clean_text(values.get("description"))
    chinese_description = clean_text(values.get("chinese_description"))
    hs_code = clean_text(values.get("hs_code"))
    gts_no_normalized, _ = normalize_gts_no(gts_no)
    oem_normalized, _ = normalize_oem(oem)
    old_product = validation.product
    changed_fields = list_changed_fields(
        old_product,
        {
            "gts_no": gts_no,
            "oem": oem,
            "description": description,
            "chinese_description": chinese_description,
            "hs_code": hs_code,
        },
    )
    now = utc_now_text()
    connection.execute(
        """
        UPDATE products
        SET
            gts_no = ?,
            gts_no_normalized = ?,
            oem = ?,
            oem_normalized = ?,
            description = ?,
            chinese_description = ?,
            hs_code = ?,
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            gts_no,
            gts_no_normalized,
            oem,
            oem_normalized,
            description,
            chinese_description,
            hs_code,
            operator_name.strip(),
            now,
            product_id,
        ),
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="edit_product",
        file_name=None,
        row_count=1,
        note=format_edit_note(changed_fields),
    )
    return ProductEditResult(
        product=get_product(connection, product_id),
        errors=[],
        warnings=validation.warnings,
    )


def normalized_value_exists(
    connection: Connection,
    *,
    product_id: int,
    field: str,
    value: str,
) -> bool:
    row = connection.execute(
        f"""
        SELECT id
        FROM products
        WHERE {field} = ?
          AND id != ?
        LIMIT 1
        """,
        (value, product_id),
    ).fetchone()
    return row is not None


def list_changed_fields(product: Row, values: dict[str, str]) -> list[str]:
    changed = []
    for field, new_value in values.items():
        old_value = clean_text(product[field])
        if old_value != new_value:
            changed.append(f"{field}: {old_value or '(空)'} => {new_value or '(空)'}")
    return changed


def format_edit_note(changed_fields: list[str]) -> str:
    if not changed_fields:
        return "产品资料未变化。"
    return "修改产品资料: " + "; ".join(changed_fields)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
