import sqlite3

from app.services.data_quality import build_data_quality_report


def test_build_data_quality_report_lists_each_quality_category():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    insert_product(
        connection,
        1,
        gts_no="GTS-MISSING-HS",
        oem="OEM-1",
        description="Mirror",
        hs_code="",
    )
    insert_product(
        connection,
        2,
        gts_no="GTS-MISSING-OEM",
        oem="",
        description="Lamp",
        hs_code="87089910",
    )
    insert_product(
        connection,
        3,
        gts_no="GTS-MISSING-DESC",
        oem="OEM-3",
        description=None,
        hs_code="87089910",
    )
    insert_product(
        connection,
        4,
        gts_no="GTS-NO-QUOTE",
        oem="OEM-4",
        description="Filter",
        hs_code="87089910",
    )
    insert_quotation(connection, 1, 1)
    insert_quotation(connection, 2, 2)
    insert_quotation(connection, 3, 3)

    report = build_data_quality_report(connection)

    assert [row["gts_no"] for row in report["missing_hs_code"]] == ["GTS-MISSING-HS"]
    assert [row["gts_no"] for row in report["missing_oem"]] == ["GTS-MISSING-OEM"]
    assert [row["gts_no"] for row in report["missing_description"]] == ["GTS-MISSING-DESC"]
    assert [row["gts_no"] for row in report["without_quotation"]] == ["GTS-NO-QUOTE"]


def initialize_test_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gts_no TEXT,
            oem TEXT,
            description TEXT,
            chinese_description TEXT,
            hs_code TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE quotation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL
        );
        """
    )


def insert_product(
    connection: sqlite3.Connection,
    product_id: int,
    *,
    gts_no: str,
    oem: str | None,
    description: str | None,
    hs_code: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, oem, description, chinese_description, hs_code,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (?, ?, ?, ?, '', ?, 'Tester', '2026-01-01T00:00:00+00:00', 'Tester', '2026-01-01T00:00:00+00:00')
        """,
        (product_id, gts_no, oem, description, hs_code),
    )


def insert_quotation(
    connection: sqlite3.Connection,
    quotation_id: int,
    product_id: int,
) -> None:
    connection.execute(
        """
        INSERT INTO quotation_items (id, product_id)
        VALUES (?, ?)
        """,
        (quotation_id, product_id),
    )
