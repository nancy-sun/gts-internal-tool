import sqlite3

from app.services.search import search_catalogue


def test_search_gts_matches_partial_suffix_and_orders_by_relevance():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    insert_product(connection, 1, "GTSTEST001", "GTSTEST001", "2026-01-01T00:00:00+00:00")
    insert_product(connection, 2, "ABC001", "ABC001", "2026-01-02T00:00:00+00:00")
    insert_quotation(connection, 1, 1, "2026-01-01T00:00:00+00:00")
    insert_quotation(connection, 2, 2, "2026-01-02T00:00:00+00:00")

    rows, warnings = search_catalogue(connection, field="gts_no", query="001")

    assert warnings == []
    assert [row["product_gts_no"] for row in rows] == ["ABC001", "GTSTEST001"]


def test_search_gts_returns_only_exact_match_products_when_exact_exists():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    insert_product(connection, 1, "GTSTEST001", "GTSTEST001", "2026-01-01T00:00:00+00:00")
    insert_product(connection, 2, "TEST001-ALT", "TEST001ALT", "2026-01-02T00:00:00+00:00")
    insert_quotation(connection, 1, 1, "2026-01-01T00:00:00+00:00")
    insert_quotation(connection, 2, 2, "2026-01-02T00:00:00+00:00")

    rows, _ = search_catalogue(connection, field="gts_no", query="gtstest001")

    assert [row["product_gts_no"] for row in rows] == ["GTSTEST001"]


def test_search_oem_uses_normalized_partial_matching():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    insert_product(
        connection,
        1,
        "GTS-1",
        "GTS1",
        "2026-01-01T00:00:00+00:00",
        oem="5010-064-551",
        oem_normalized="5010064551",
    )
    insert_quotation(connection, 1, 1, "2026-01-01T00:00:00+00:00")

    rows, warnings = search_catalogue(connection, field="oem", query="064 551")

    assert warnings == []
    assert [row["product_oem"] for row in rows] == ["5010-064-551"]


def test_search_chinese_description_and_factory_use_text_contains_matching():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    insert_product(
        connection,
        1,
        "GTS-1",
        "GTS1",
        "2026-01-01T00:00:00+00:00",
        chinese_description="后视镜总成",
    )
    insert_quotation(
        connection,
        1,
        1,
        "2026-01-01T00:00:00+00:00",
        factory="欧达工厂",
    )

    chinese_rows, _ = search_catalogue(connection, field="chinese_description", query="后视镜")
    factory_rows, _ = search_catalogue(connection, field="factory", query="欧达")

    assert [row["product_gts_no"] for row in chinese_rows] == ["GTS-1"]
    assert [row["factory"] for row in factory_rows] == ["欧达工厂"]


def initialize_test_schema(connection: sqlite3.Connection) -> None:
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
            factory TEXT,
            unit_price REAL,
            packaging TEXT,
            expected_delivery TEXT,
            comment TEXT,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def insert_product(
    connection: sqlite3.Connection,
    product_id: int,
    gts_no: str,
    gts_no_normalized: str,
    updated_at: str,
    oem: str | None = None,
    oem_normalized: str | None = None,
    chinese_description: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, oem, oem_normalized, chinese_description,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'Tester', ?, 'Tester', ?)
        """,
        (
            product_id,
            gts_no,
            gts_no_normalized,
            oem,
            oem_normalized,
            chinese_description,
            updated_at,
            updated_at,
        ),
    )


def insert_quotation(
    connection: sqlite3.Connection,
    quotation_id: int,
    product_id: int,
    updated_at: str,
    factory: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO quotation_items (
            id, product_id, factory, updated_by, updated_at
        )
        VALUES (?, ?, ?, 'Tester', ?)
        """,
        (quotation_id, product_id, factory, updated_at),
    )
