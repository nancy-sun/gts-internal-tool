import sqlite3
from pathlib import Path


def test_supplier_edit_password_defaults_to_product_edit_password(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SHARED_ACCESS_CODE", "test-access-code")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "product-password")
    monkeypatch.delenv("SUPPLIER_EDIT_PASSWORD", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "settings.sqlite3"))

    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.supplier_edit_password == "product-password"
    get_settings.cache_clear()


def test_supplier_edit_password_env_overrides_product_edit_password(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SHARED_ACCESS_CODE", "test-access-code")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "product-password")
    monkeypatch.setenv("SUPPLIER_EDIT_PASSWORD", "supplier-password")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "settings.sqlite3"))

    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.supplier_edit_password == "supplier-password"
    get_settings.cache_clear()


def test_initialize_database_creates_suppliers_and_optional_supplier_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "gts.sqlite3"
    monkeypatch.setenv("SHARED_ACCESS_CODE", "test-access-code")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "55123511")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    from app.config import get_settings
    from app.database import initialize_database

    get_settings.cache_clear()
    initialize_database()

    with sqlite3.connect(database_path) as connection:
        supplier_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(suppliers)").fetchall()
        }
        quotation_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(quotation_items)").fetchall()
        }
        quotation_column_types = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA table_info(quotation_items)").fetchall()
        }
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(suppliers)").fetchall()
        }

    assert {
        "id",
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
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    }.issubset(supplier_columns)
    assert "supplier_name" not in supplier_columns
    assert "supplier_name_normalized" not in supplier_columns
    assert "supplier_id" in quotation_columns
    for column in (
        "item_per_package",
        "packages",
        "weight_per_package",
        "gross_weight",
        "length",
        "width",
        "height",
        "measurements_volume",
    ):
        assert quotation_column_types[column] == "REAL"
    assert "idx_suppliers_short_name_normalized_unique" in indexes
    alias_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(supplier_aliases)").fetchall()
    }
    assert {
        "id",
        "supplier_id",
        "alias_name",
        "alias_name_normalized",
        "alias_type",
        "source",
        "created_by",
        "created_at",
        "updated_at",
    }.issubset(alias_columns)
    get_settings.cache_clear()


def test_initialize_database_migrates_legacy_supplier_name_to_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setenv("SHARED_ACCESS_CODE", "test-access-code")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "55123511")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_name TEXT NOT NULL,
                supplier_name_normalized TEXT,
                supplier_full_name TEXT,
                supplier_short_name TEXT,
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
            CREATE INDEX idx_suppliers_supplier_name_normalized
            ON suppliers(supplier_name_normalized);
            INSERT INTO suppliers (
                supplier_name,
                supplier_name_normalized,
                supplier_full_name,
                supplier_short_name,
                aliases_text,
                created_by,
                created_at,
                updated_by,
                updated_at
            )
            VALUES (
                'Old Factory Name',
                'oldfactoryname',
                'New Full Name',
                'New Short',
                '',
                'Nancy',
                '2026-05-17T00:00:00+00:00',
                'Nancy',
                '2026-05-17T00:00:00+00:00'
            );
            """
        )

    from app.config import get_settings
    from app.database import initialize_database

    get_settings.cache_clear()
    initialize_database()

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(suppliers)").fetchall()
        }
        supplier = connection.execute("SELECT * FROM suppliers WHERE id = 1").fetchone()
        alias = connection.execute(
            """
            SELECT alias_name, source
            FROM supplier_aliases
            WHERE supplier_id = 1
              AND alias_name = 'Old Factory Name'
            """
        ).fetchone()

    assert "supplier_name" not in columns
    assert "supplier_name_normalized" not in columns
    assert supplier["supplier_full_name"] == "New Full Name"
    assert supplier["supplier_short_name"] == "New Short"
    assert supplier["aliases_text"] == "Old Factory Name"
    assert alias["source"] == "aliases_text"
    get_settings.cache_clear()


def test_initialize_database_migrates_quotation_numeric_columns_to_real(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "legacy-quotation.sqlite3"
    monkeypatch.setenv("SHARED_ACCESS_CODE", "test-access-code")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "55123511")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gts_no TEXT,
                gts_no_normalized TEXT,
                oem TEXT,
                oem_normalized TEXT,
                description TEXT,
                chinese_description TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
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
                updated_at TEXT NOT NULL
            );
            INSERT INTO products (id, created_by, created_at, updated_by, updated_at)
            VALUES (1, 'Nancy', '2026-01-01', 'Nancy', '2026-01-01');
            INSERT INTO quotation_items (
                id, product_id, item_per_package, packages, weight_per_package,
                gross_weight, length, width, height, measurements_volume,
                created_by, created_at, updated_by, updated_at
            )
            VALUES (
                1, 1, '12/CTN', '2', '5 kg', '10 kg', '10', '20',
                '30', '0.06 CBM', 'Nancy', '2026-01-01', 'Nancy', '2026-01-01'
            );
            """
        )

    from app.config import get_settings
    from app.database import initialize_database

    get_settings.cache_clear()
    initialize_database()

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        column_types = {
            row["name"]: row["type"]
            for row in connection.execute("PRAGMA table_info(quotation_items)").fetchall()
        }
        row = connection.execute(
            """
            SELECT item_per_package, packages, weight_per_package, gross_weight,
                   length, width, height, measurements_volume
            FROM quotation_items
            WHERE id = 1
            """
        ).fetchone()

    assert column_types["item_per_package"] == "REAL"
    assert row["item_per_package"] == 12
    assert row["packages"] == 2
    assert row["weight_per_package"] == 5
    assert row["gross_weight"] == 10
    assert row["measurements_volume"] == 0.06
    get_settings.cache_clear()
