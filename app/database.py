import re
import sqlite3
from collections.abc import Iterator, Mapping
from typing import Any

from app.config import get_settings

QUOTATION_REAL_COLUMNS = {
    "item_per_package",
    "packages",
    "weight_per_package",
    "gross_weight",
    "length",
    "width",
    "height",
    "measurements_volume",
}


POSTGRES_ID_TABLES = {
    "products",
    "suppliers",
    "supplier_aliases",
    "quotation_items",
    "operation_logs",
    "users",
}


class CompatRow(Mapping):
    def __init__(self, values: dict[str, Any], order: list[str]) -> None:
        self._values = values
        self._order = order

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[self._order[key]]
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._order)

    def __len__(self) -> int:
        return len(self._order)

    def __eq__(self, other) -> bool:
        if isinstance(other, tuple):
            return tuple(self[index] for index in range(len(self))) == other
        return super().__eq__(other)

    def keys(self):
        return self._order


class CompatCursor:
    def __init__(self, rows: list[CompatRow] | None = None, lastrowid: int | None = None) -> None:
        self._rows = rows or []
        self.lastrowid = lastrowid

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    def fetchall(self):
        rows = self._rows
        self._rows = []
        return rows


class PostgresConnection:
    is_postgres = True

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires psycopg. Install requirements.txt first."
            ) from exc
        self._connection = psycopg.connect(normalize_psycopg_url(database_url))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type:
            self._connection.rollback()
        else:
            self._connection.commit()
        self.close()

    def close(self) -> None:
        self._connection.close()

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def execute(self, sql: str, params: Any = None) -> CompatCursor:
        pragma_result = self._execute_pragma(sql)
        if pragma_result is not None:
            return pragma_result

        converted_sql = convert_sqlite_placeholders(sql)
        converted_sql, returns_id = add_returning_id_if_needed(converted_sql)
        with self._connection.cursor() as cursor:
            cursor.execute(converted_sql, tuple(params or ()))
            if cursor.description:
                columns = [column.name for column in cursor.description]
                tuples = cursor.fetchall()
                rows = [CompatRow(dict(zip(columns, row)), columns) for row in tuples]
                lastrowid = rows[0][0] if returns_id and rows else None
                if returns_id:
                    rows = []
                return CompatCursor(rows, lastrowid=lastrowid)
        return CompatCursor()

    def executescript(self, script: str) -> None:
        for statement in split_sql_script(script):
            self.execute(statement)

    def _execute_pragma(self, sql: str) -> CompatCursor | None:
        match = re.match(r"\s*PRAGMA\s+table_info\((\w+)\)\s*$", sql, re.IGNORECASE)
        if not match:
            return None
        table_name = match.group(1)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
            rows = []
            order = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
            for index, (column_name, data_type) in enumerate(cursor.fetchall()):
                rows.append(
                    CompatRow(
                        {
                            "cid": index,
                            "name": column_name,
                            "type": data_type,
                            "notnull": 0,
                            "dflt_value": None,
                            "pk": 0,
                        },
                        order,
                    )
                )
        return CompatCursor(rows)


def convert_sqlite_placeholders(sql: str) -> str:
    result = []
    in_single = False
    in_double = False
    for char in sql:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        if char == "?" and not in_single and not in_double:
            result.append("%s")
        else:
            result.append(char)
    return "".join(result)


def add_returning_id_if_needed(sql: str) -> tuple[str, bool]:
    if re.search(r"\bRETURNING\b", sql, re.IGNORECASE):
        return sql, False
    match = re.match(r"\s*INSERT\s+INTO\s+(\w+)\b", sql, re.IGNORECASE)
    if not match:
        return sql, False
    table_name = match.group(1).lower()
    if table_name not in POSTGRES_ID_TABLES:
        return sql, False
    return f"{sql.rstrip()} RETURNING id", True


def split_sql_script(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def normalize_psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def get_connection():
    settings = get_settings()
    if settings.database_backend == "postgresql":
        return PostgresConnection(settings.database_url)
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_file, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database() -> None:
    if get_settings().database_backend == "postgresql":
        initialize_postgres_database()
        return
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
                item_per_package REAL,
                packages REAL,
                weight_per_package REAL,
                gross_weight REAL,
                length REAL,
                width REAL,
                height REAL,
                measurements_volume REAL,
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
                user_id INTEGER,
                action_time TEXT NOT NULL,
                operator_name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                file_name TEXT,
                row_count INTEGER,
                note TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_operation_logs_action_time
            ON operation_logs(action_time);

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'sales', 'merchandiser')),
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        ensure_column(connection, "operation_logs", "user_id", "INTEGER")
        ensure_column(connection, "products", "hs_code", "TEXT")
        ensure_column(connection, "quotation_items", "supplier_id", "INTEGER")
        migrate_quotation_numeric_columns(connection)
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


def initialize_postgres_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'sales', 'merchandiser')),
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
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

            CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_short_name_normalized_unique
            ON suppliers(supplier_short_name_normalized)
            WHERE supplier_short_name_normalized IS NOT NULL
              AND supplier_short_name_normalized != '';

            CREATE TABLE IF NOT EXISTS supplier_aliases (
                id SERIAL PRIMARY KEY,
                supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
                alias_name TEXT NOT NULL,
                alias_name_normalized TEXT NOT NULL,
                alias_type TEXT,
                source TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_supplier_aliases_normalized
            ON supplier_aliases(alias_name_normalized);

            CREATE INDEX IF NOT EXISTS idx_supplier_aliases_supplier_id
            ON supplier_aliases(supplier_id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_supplier_aliases_supplier_alias_unique
            ON supplier_aliases(supplier_id, alias_name_normalized);

            CREATE TABLE IF NOT EXISTS quotation_items (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id),
                supplier_id INTEGER REFERENCES suppliers(id),
                no TEXT,
                gts_no TEXT,
                gts_no_normalized TEXT,
                description TEXT,
                oem TEXT,
                oem_normalized TEXT,
                factory TEXT,
                chinese_description TEXT,
                quantity INTEGER,
                unit TEXT,
                unit_price NUMERIC(12,2),
                total_price NUMERIC(14,2),
                item_per_package NUMERIC(10,2),
                packages INTEGER,
                weight_per_package NUMERIC(10,2),
                gross_weight NUMERIC(10,2),
                length NUMERIC(10,2),
                width NUMERIC(10,2),
                height NUMERIC(10,2),
                measurements_volume NUMERIC(10,3),
                packaging TEXT,
                expected_delivery TEXT,
                comment TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_quotation_items_product_id
            ON quotation_items(product_id);

            CREATE INDEX IF NOT EXISTS idx_quotation_items_updated_at
            ON quotation_items(updated_at);

            CREATE TABLE IF NOT EXISTS operation_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
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


def migrate_quotation_numeric_columns(connection: sqlite3.Connection) -> None:
    columns = connection.execute("PRAGMA table_info(quotation_items)").fetchall()
    if not columns:
        return
    column_types = {row["name"]: (row["type"] or "").upper() for row in columns}
    if all(column_types.get(column) == "REAL" for column in QUOTATION_REAL_COLUMNS):
        return

    rows = connection.execute("SELECT * FROM quotation_items ORDER BY id").fetchall()
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("ALTER TABLE quotation_items RENAME TO quotation_items_old_numeric")
    connection.executescript(
        """
        CREATE TABLE quotation_items (
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
            item_per_package REAL,
            packages REAL,
            weight_per_package REAL,
            gross_weight REAL,
            length REAL,
            width REAL,
            height REAL,
            measurements_volume REAL,
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
        """
    )
    insert_columns = [
        "id",
        "product_id",
        "supplier_id",
        "no",
        "gts_no",
        "gts_no_normalized",
        "description",
        "oem",
        "oem_normalized",
        "factory",
        "chinese_description",
        "quantity",
        "unit",
        "unit_price",
        "total_price",
        "item_per_package",
        "packages",
        "weight_per_package",
        "gross_weight",
        "length",
        "width",
        "height",
        "measurements_volume",
        "packaging",
        "expected_delivery",
        "comment",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    ]
    placeholders = ", ".join("?" for _ in insert_columns)
    for row in rows:
        values = []
        for column in insert_columns:
            value = row[column] if column in row.keys() else None
            if column in QUOTATION_REAL_COLUMNS:
                value = _parse_numeric_value(value)
            values.append(value)
        connection.execute(
            f"""
            INSERT INTO quotation_items ({", ".join(insert_columns)})
            VALUES ({placeholders})
            """,
            values,
        )
    connection.execute("DROP TABLE quotation_items_old_numeric")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quotation_items_product_id
        ON quotation_items(product_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quotation_items_updated_at
        ON quotation_items(updated_at)
        """
    )
    connection.execute("PRAGMA foreign_keys = ON")


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


def _parse_numeric_value(value: Any) -> float | None:
    if value in ("", None):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d*\.?\d+", str(value).replace(",", ""))
    if not match:
        return None
    return float(match.group(0))
