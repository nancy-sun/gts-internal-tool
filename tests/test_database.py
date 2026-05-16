import sqlite3
from pathlib import Path


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
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(suppliers)").fetchall()
        }

    assert {
        "id",
        "supplier_name",
        "supplier_name_normalized",
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
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    }.issubset(supplier_columns)
    assert "supplier_id" in quotation_columns
    assert "idx_suppliers_supplier_name_normalized" in indexes
    get_settings.cache_clear()
