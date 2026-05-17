import re
import sqlite3
from typing import Any

from app.config import get_settings


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_file, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gts_no TEXT,
                gts_no_normalized TEXT,
                oem TEXT,
                oem_normalized TEXT,
                description TEXT,
                chinese_description TEXT,
                hs_code TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_products_gts_no_normalized
            ON products(gts_no_normalized);

            CREATE INDEX IF NOT EXISTS idx_products_oem_normalized
            ON products(oem_normalized);

            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_full_name TEXT,
                supplier_short_name TEXT,
                supplier_short_name_normalized TEXT,
                aliases_text TEXT,
                contact_person TEXT,
                phone TEXT,
                wechat TEXT,
                city TEXT,
                province TEXT,
                product_scope TEXT,
                factory_or_trader TEXT,
                quality_level TEXT,
                price_level TEXT,
                quality_rating INTEGER,
                price_rating INTEGER,
                cooperation_rating INTEGER,
                cooperation_notes TEXT,
                notes TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supplier_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL,
                alias_name TEXT NOT NULL,
                alias_name_normalized TEXT NOT NULL,
                alias_type TEXT,
                source TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_supplier_aliases_normalized
            ON supplier_aliases(alias_name_normalized);

            CREATE INDEX IF NOT EXISTS idx_supplier_aliases_supplier_id
            ON supplier_aliases(supplier_id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_supplier_aliases_supplier_alias_unique
            ON supplier_aliases(supplier_id, alias_name_normalized);

            CREATE TABLE IF NOT EXISTS quotation_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                supplier_id INTEGER,
                no TEXT,
                gts_no TEXT,
                gts_no_normalized TEXT,
                description TEXT,
                oem TEXT,
                oem_normalized TEXT,
                factory TEXT,
                chinese_description TEXT,
                quantity REAL,
                unit TEXT,
                unit_price REAL,
                total_price REAL,
                item_per_package TEXT,
                packages TEXT,
                weight_per_package TEXT,
                gross_weight TEXT,
                length TEXT,
                width TEXT,
                height TEXT,
                measurements_volume TEXT,
                packaging TEXT,
                expected_delivery TEXT,
                comment TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id),
                FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_quotation_items_product_id
            ON quotation_items(product_id);

            CREATE INDEX IF NOT EXISTS idx_quotation_items_updated_at
            ON quotation_items(updated_at);

            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_time TEXT NOT NULL,
                operator_name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                file_name TEXT,
                row_count INTEGER,
                note TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_operation_logs_action_time
            ON operation_logs(action_time);
            """
        )
        ensure_column(connection, "products", "hs_code", "TEXT")
        ensure_column(connection, "quotation_items", "supplier_id", "INTEGER")
        ensure_column(connection, "suppliers", "supplier_full_name", "TEXT")
        ensure_column(connection, "suppliers", "supplier_short_name", "TEXT")
        ensure_column(connection, "suppliers", "supplier_short_name_normalized", "TEXT")
        ensure_column(connection, "suppliers", "aliases_text", "TEXT")
        ensure_column(connection, "suppliers", "quality_rating", "INTEGER")
        ensure_column(connection, "suppliers", "price_rating", "INTEGER")
        ensure_column(connection, "suppliers", "cooperation_rating", "INTEGER")
        ensure_column(connection, "suppliers", "cooperation_notes", "TEXT")
        migrate_supplier_name_columns(connection)
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_short_name_normalized_unique
            ON suppliers(supplier_short_name_normalized)
            WHERE supplier_short_name_normalized IS NOT NULL
              AND supplier_short_name_normalized != ''
            """
        )


def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )


def migrate_supplier_name_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(suppliers)").fetchall()
    }
    has_legacy_name = "supplier_name" in columns
    has_legacy_normalized = "supplier_name_normalized" in columns

    rows = connection.execute("SELECT * FROM suppliers ORDER BY id").fetchall()
    used_short_names: set[str] = set()
    for row in rows:
        legacy_name = row["supplier_name"] if has_legacy_name else ""
        full_name = _text(row["supplier_full_name"]) or _text(legacy_name)
        short_name = _text(row["supplier_short_name"]) or full_name or f"供应商{row['id']}"
        short_name = _unique_short_name(short_name, row["id"], used_short_names)
        normalized_short_name = _normalize_supplier_name(short_name)
        used_short_names.add(normalized_short_name)
        aliases_text = _merge_alias_text(
            row["aliases_text"],
            legacy_name,
            full_name,
            short_name,
        )
        connection.execute(
            """
            UPDATE suppliers
            SET supplier_full_name = ?,
                supplier_short_name = ?,
                supplier_short_name_normalized = ?,
                aliases_text = ?
            WHERE id = ?
            """,
            (full_name, short_name, normalized_short_name, aliases_text, row["id"]),
        )
        _insert_legacy_supplier_alias(
            connection,
            supplier_id=row["id"],
            legacy_name=legacy_name,
            full_name=full_name,
            short_name=short_name,
            operator_name=row["updated_by"],
            timestamp=row["updated_at"],
        )

    if has_legacy_normalized:
        connection.execute("DROP INDEX IF EXISTS idx_suppliers_supplier_name_normalized")
        connection.execute("ALTER TABLE suppliers DROP COLUMN supplier_name_normalized")
    if has_legacy_name:
        connection.execute("ALTER TABLE suppliers DROP COLUMN supplier_name")


def _insert_legacy_supplier_alias(
    connection: sqlite3.Connection,
    *,
    supplier_id: int,
    legacy_name: Any,
    full_name: str,
    short_name: str,
    operator_name: Any,
    timestamp: Any,
) -> None:
    alias_name = _text(legacy_name)
    normalized = _normalize_supplier_name(alias_name)
    if not normalized:
        return
    if normalized in {
        _normalize_supplier_name(full_name),
        _normalize_supplier_name(short_name),
    }:
        return
    existing = connection.execute(
        """
        SELECT id
        FROM supplier_aliases
        WHERE supplier_id = ?
          AND alias_name_normalized = ?
        """,
        (supplier_id, normalized),
    ).fetchone()
    if existing:
        return
    now = _text(timestamp)
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
        VALUES (?, ?, ?, 'manual', 'aliases_text', ?, ?, ?)
        """,
        (supplier_id, alias_name, normalized, _text(operator_name), now, now),
    )


def _merge_alias_text(
    current_aliases: Any,
    legacy_name: Any,
    full_name: str,
    short_name: str,
) -> str:
    aliases = _split_aliases(current_aliases)
    legacy_alias = _text(legacy_name)
    normalized_legacy = _normalize_supplier_name(legacy_alias)
    if normalized_legacy and normalized_legacy not in {
        _normalize_supplier_name(full_name),
        _normalize_supplier_name(short_name),
    }:
        aliases.append(legacy_alias)

    cleaned_aliases = []
    seen = set()
    for alias in aliases:
        normalized = _normalize_supplier_name(alias)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned_aliases.append(alias)
    return "，".join(cleaned_aliases)


def _split_aliases(value: Any) -> list[str]:
    aliases = []
    for alias in re.split(r"[，,]", _text(value)):
        clean_alias = _collapse_spaces(alias)
        if clean_alias:
            aliases.append(clean_alias)
    return aliases


def _unique_short_name(short_name: str, supplier_id: int, used: set[str]) -> str:
    candidate = short_name
    normalized = _normalize_supplier_name(candidate)
    if not normalized or normalized not in used:
        return candidate
    candidate = f"{short_name}-{supplier_id}"
    normalized = _normalize_supplier_name(candidate)
    while normalized in used:
        candidate = f"{candidate}-{supplier_id}"
        normalized = _normalize_supplier_name(candidate)
    return candidate


def _normalize_supplier_name(value: Any) -> str:
    text = _collapse_spaces(value).lower()
    text = re.sub(r"[，,。.;；:：、/\\|()\[\]{}<>《》\"'`~!！?？@#$%^&*_+=-]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _collapse_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
