import sqlite3

from app.config import get_settings


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_file)
    connection.row_factory = sqlite3.Row
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

            CREATE TABLE IF NOT EXISTS quotation_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
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
                FOREIGN KEY(product_id) REFERENCES products(id)
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
