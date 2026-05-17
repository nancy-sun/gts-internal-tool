from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
from sqlite3 import Connection, Row
from typing import Any

from app.services.operation_logging import create_operation_log, utc_now_text


SUPPLIER_FIELDS = (
    "supplier_full_name",
    "supplier_short_name",
    "supplier_short_name_normalized",
    "aliases_text",
    "contact_person",
    "phone",
    "wechat",
    "city",
    "province",
    "product_scope",
    "factory_or_trader",
    "quality_level",
    "price_level",
    "quality_rating",
    "price_rating",
    "cooperation_rating",
    "cooperation_notes",
    "notes",
)
RATING_FIELDS = ("quality_rating", "price_rating", "cooperation_rating")
ALIASES_TEXT_SEPARATOR = "，"


@dataclass(frozen=True)
class SupplierMatchResult:
    status: str
    suppliers: list[Row]

    @property
    def supplier(self) -> Row | None:
        return self.suppliers[0] if len(self.suppliers) == 1 else None


def split_supplier_aliases(text: str) -> list[str]:
    aliases = []
    seen = set()
    for alias in re.split(r"[，,]", text or ""):
        clean_alias = _collapse_spaces(alias)
        if not clean_alias:
            continue
        normalized_alias = normalize_supplier_name(clean_alias)
        dedupe_key = normalized_alias or clean_alias
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        aliases.append(clean_alias)
    return aliases


def clean_aliases_text(text: str) -> str:
    return ALIASES_TEXT_SEPARATOR.join(split_supplier_aliases(text))


def normalize_supplier_name(value: Any) -> str:
    if value is None:
        return ""
    text = _collapse_spaces(value).lower()
    text = re.sub(r"[，,。.;；:：、/\\|()\[\]{}<>《》\"'`~!！?？@#$%^&*_+=-]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
        SELECT DISTINCT s.*
        FROM suppliers s
        LEFT JOIN supplier_aliases a ON a.supplier_id = s.id
        WHERE s.supplier_full_name LIKE ?
           OR s.supplier_short_name LIKE ?
           OR s.supplier_short_name_normalized LIKE ?
           OR s.city LIKE ?
           OR s.product_scope LIKE ?
           OR a.alias_name_normalized LIKE ?
           OR a.alias_name LIKE ?
        ORDER BY s.updated_at DESC, s.id DESC
        LIMIT ?
        """,
        (
            like_query,
            like_query,
            normalized_like_query,
            like_query,
            like_query,
            normalized_like_query,
            like_query,
            limit,
        ),
    ).fetchall()


def get_supplier(connection: Connection, supplier_id: int) -> Row | None:
    return connection.execute(
        "SELECT * FROM suppliers WHERE id = ?",
        (supplier_id,),
    ).fetchone()


def match_supplier_by_name(connection: Connection, supplier_name: str) -> SupplierMatchResult:
    normalized_name = normalize_supplier_name(supplier_name)
    if not normalized_name or not supplier_link_available(connection):
        return SupplierMatchResult(status="unmatched", suppliers=[])

    rows = connection.execute(
        """
        SELECT DISTINCT s.*
        FROM suppliers s
        LEFT JOIN supplier_aliases a ON a.supplier_id = s.id
        WHERE a.alias_name_normalized = ?
           OR lower(trim(COALESCE(s.supplier_full_name, ''))) = ?
           OR lower(trim(COALESCE(s.supplier_short_name, ''))) = ?
           OR s.supplier_short_name_normalized = ?
        ORDER BY s.updated_at DESC, s.id DESC
        """,
        (normalized_name, normalized_name, normalized_name, normalized_name),
    ).fetchall()
    if len(rows) == 1:
        return SupplierMatchResult(status="matched", suppliers=rows)
    if len(rows) > 1:
        return SupplierMatchResult(status="ambiguous", suppliers=rows)
    return SupplierMatchResult(status="unmatched", suppliers=[])


def find_supplier_by_name(connection: Connection, supplier_name: str) -> Row | None:
    try:
        match = match_supplier_by_name(connection, supplier_name)
    except sqlite3.OperationalError:
        return None
    return match.supplier if match.status == "matched" else None


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
    alias_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(supplier_aliases)").fetchall()
    }
    return "supplier_id" in quotation_columns and bool(alias_columns)


def create_supplier(
    connection: Connection,
    *,
    values: dict[str, Any],
    operator_name: str,
) -> int:
    now = utc_now_text()
    prepared = prepare_supplier_values(values)
    cursor = connection.execute(
        """
        INSERT INTO suppliers (
            supplier_full_name,
            supplier_short_name,
            supplier_short_name_normalized,
            aliases_text,
            contact_person,
            phone,
            wechat,
            city,
            province,
            product_scope,
            factory_or_trader,
            quality_level,
            price_level,
            quality_rating,
            price_rating,
            cooperation_rating,
            cooperation_notes,
            notes,
            created_by,
            created_at,
            updated_by,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prepared["supplier_full_name"],
            prepared["supplier_short_name"],
            prepared["supplier_short_name_normalized"],
            prepared["aliases_text"],
            prepared["contact_person"],
            prepared["phone"],
            prepared["wechat"],
            prepared["city"],
            prepared["province"],
            prepared["product_scope"],
            prepared["factory_or_trader"],
            prepared["quality_level"],
            prepared["price_level"],
            prepared["quality_rating"],
            prepared["price_rating"],
            prepared["cooperation_rating"],
            prepared["cooperation_notes"],
            prepared["notes"],
            operator_name,
            now,
            operator_name,
            now,
        ),
    )
    supplier_id = int(cursor.lastrowid)
    sync_supplier_aliases(connection, supplier_id, operator_name)
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="create_supplier",
        row_count=1,
        note=f"供应商={supplier_display_name(prepared)}",
    )
    return supplier_id


def update_supplier(
    connection: Connection,
    *,
    supplier_id: int,
    values: dict[str, Any],
    operator_name: str,
) -> None:
    old_supplier = get_supplier(connection, supplier_id)
    old_ratings = supplier_ratings(old_supplier)
    now = utc_now_text()
    prepared = prepare_supplier_values(values)
    connection.execute(
        """
        UPDATE suppliers
        SET supplier_full_name = ?,
            supplier_short_name = ?,
            supplier_short_name_normalized = ?,
            aliases_text = ?,
            contact_person = ?,
            phone = ?,
            wechat = ?,
            city = ?,
            province = ?,
            product_scope = ?,
            factory_or_trader = ?,
            quality_level = ?,
            price_level = ?,
            quality_rating = ?,
            price_rating = ?,
            cooperation_rating = ?,
            cooperation_notes = ?,
            notes = ?,
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            prepared["supplier_full_name"],
            prepared["supplier_short_name"],
            prepared["supplier_short_name_normalized"],
            prepared["aliases_text"],
            prepared["contact_person"],
            prepared["phone"],
            prepared["wechat"],
            prepared["city"],
            prepared["province"],
            prepared["product_scope"],
            prepared["factory_or_trader"],
            prepared["quality_level"],
            prepared["price_level"],
            prepared["quality_rating"],
            prepared["price_rating"],
            prepared["cooperation_rating"],
            prepared["cooperation_notes"],
            prepared["notes"],
            operator_name,
            now,
            supplier_id,
        ),
    )
    sync_supplier_aliases(connection, supplier_id, operator_name)
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="edit_supplier",
        row_count=1,
        note=f"供应商={supplier_display_name(prepared)}",
    )
    if old_ratings != supplier_ratings(get_supplier(connection, supplier_id)):
        create_operation_log(
            connection,
            operator_name=operator_name,
            action_type="supplier_rating_changed",
            row_count=1,
            note=f"供应商={supplier_display_name(prepared)}",
        )


def supplier_form_values(form_values: dict[str, Any] | Row | None = None) -> dict[str, Any]:
    source = form_values or {}
    values = {}
    for field in SUPPLIER_FIELDS:
        value = source[field] if isinstance(source, Row) and field in source.keys() else source.get(field)
        if field in RATING_FIELDS:
            values[field] = "" if value in ("", None) else int(value)
        else:
            values[field] = _text(value)
    values["aliases_text"] = clean_aliases_text(values.get("aliases_text") or "")
    values["supplier_short_name_normalized"] = normalize_supplier_name(values.get("supplier_short_name"))
    return values


def supplier_form_values_from_db(connection: Connection, supplier: Row) -> dict[str, Any]:
    values = supplier_form_values(supplier)
    if not values.get("aliases_text"):
        aliases = connection.execute(
            """
            SELECT alias_name
            FROM supplier_aliases
            WHERE supplier_id = ?
              AND source = 'aliases_text'
            ORDER BY id
            """,
            (supplier["id"],),
        ).fetchall()
        values["aliases_text"] = ALIASES_TEXT_SEPARATOR.join(row["alias_name"] for row in aliases)
    return values


def validate_supplier_values(values: dict[str, Any], operator_name: str) -> list[str]:
    errors = []
    if not operator_name.strip():
        errors.append("请填写操作人。")
    if not _text(values.get("supplier_full_name")):
        errors.append("请填写供应商全称。")
    if not _text(values.get("supplier_short_name")):
        errors.append("请填写供应商简称。")
    for field in RATING_FIELDS:
        try:
            parse_rating(values.get(field))
        except ValueError:
            errors.append(f"{rating_label(field)}必须为空或 1-5。")
    return errors


def prepare_supplier_values(values: dict[str, Any]) -> dict[str, Any]:
    prepared = {}
    for field in SUPPLIER_FIELDS:
        prepared[field] = values.get(field)
    prepared["aliases_text"] = clean_aliases_text(_text(prepared.get("aliases_text")))
    for field in RATING_FIELDS:
        prepared[field] = parse_rating(prepared.get(field))
    for field in SUPPLIER_FIELDS:
        if field not in RATING_FIELDS:
            prepared[field] = _text(prepared.get(field))
    prepared["supplier_short_name_normalized"] = normalize_supplier_name(prepared["supplier_short_name"])
    return prepared


def supplier_display_name(values: dict[str, Any] | Row) -> str:
    return _text(values["supplier_short_name"]) or _text(values["supplier_full_name"])


def parse_rating(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        rating = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid rating") from exc
    if rating not in {1, 2, 3, 4, 5}:
        raise ValueError("Invalid rating")
    return rating


def rating_label(field: str) -> str:
    return {
        "quality_rating": "质量评分",
        "price_rating": "价格评分",
        "cooperation_rating": "配合评分",
    }.get(field, field)


def rating_display(value: Any) -> str:
    return "未评分" if value in ("", None) else str(value)


def validate_supplier_short_name_unique(
    connection: Connection,
    supplier_short_name: str,
    supplier_id: int | None = None,
) -> list[str]:
    normalized = normalize_supplier_name(supplier_short_name)
    if not normalized:
        return []
    params: list[Any] = [normalized]
    supplier_filter = ""
    if supplier_id is not None:
        supplier_filter = " AND id != ?"
        params.append(supplier_id)
    existing = connection.execute(
        f"""
        SELECT id
        FROM suppliers
        WHERE supplier_short_name_normalized = ?
        {supplier_filter}
        LIMIT 1
        """,
        params,
    ).fetchone()
    if existing:
        return ["供应商简称已存在，请使用唯一简称。"]
    return []


def sync_supplier_aliases(connection: Connection, supplier_id: int, operator_name: str) -> None:
    supplier = get_supplier(connection, supplier_id)
    if not supplier:
        return
    now = utc_now_text()
    connection.execute(
        "DELETE FROM supplier_aliases WHERE supplier_id = ? AND source = 'aliases_text'",
        (supplier_id,),
    )
    alias_specs = []
    for source, field, alias_type in (
        ("full_name", "supplier_full_name", "full_name"),
        ("short_name", "supplier_short_name", "short_name"),
    ):
        alias = _text(supplier[field]) if field in supplier.keys() else ""
        if alias:
            alias_specs.append((alias, alias_type, source))
    alias_specs.extend(
        (alias, "manual", "aliases_text")
        for alias in split_supplier_aliases(supplier["aliases_text"] or "")
    )

    seen = set()
    synced_count = 0
    for alias_name, alias_type, source in alias_specs:
        normalized = normalize_supplier_name(alias_name)
        if not normalized:
            continue
        key = (source, normalized)
        if key in seen:
            continue
        seen.add(key)
        existing = connection.execute(
            """
            SELECT id, source
            FROM supplier_aliases
            WHERE supplier_id = ?
              AND alias_name_normalized = ?
            """,
            (supplier_id, normalized),
        ).fetchone()
        if existing:
            if source == "aliases_text" and existing["source"] != "aliases_text":
                continue
            connection.execute(
                """
                UPDATE supplier_aliases
                SET alias_name = ?,
                    alias_type = ?,
                    source = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (alias_name, alias_type, source, now, existing["id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO supplier_aliases (
                    supplier_id,
                    alias_name,
                    alias_name_normalized,
                    alias_type,
                    source,
                    created_by,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    supplier_id,
                    alias_name,
                    normalized,
                    alias_type,
                    source,
                    operator_name,
                    now,
                    now,
                ),
            )
        synced_count += 1
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="supplier_aliases_synced",
        row_count=synced_count,
        note=f"供应商ID={supplier_id}",
    )


def add_alias_text_alias(connection: Connection, supplier_id: int, alias_name: str) -> None:
    supplier = get_supplier(connection, supplier_id)
    if not supplier:
        return
    aliases = split_supplier_aliases(supplier["aliases_text"] or "")
    normalized_existing = {normalize_supplier_name(alias) for alias in aliases}
    if normalize_supplier_name(alias_name) not in normalized_existing:
        aliases.append(_collapse_spaces(alias_name))
    connection.execute(
        "UPDATE suppliers SET aliases_text = ? WHERE id = ?",
        (ALIASES_TEXT_SEPARATOR.join(aliases), supplier_id),
    )


def supplier_ratings(supplier: Row | None) -> tuple[Any, Any, Any]:
    if not supplier:
        return (None, None, None)
    return (
        supplier["quality_rating"] if "quality_rating" in supplier.keys() else None,
        supplier["price_rating"] if "price_rating" in supplier.keys() else None,
        supplier["cooperation_rating"] if "cooperation_rating" in supplier.keys() else None,
    )


def _collapse_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
