import sqlite3

from app.database import initialize_database
from app.services.operation_logging import utc_now_text
from app.services.quotation_generation import (
    GENERATED_COLUMNS,
    build_generation_preview,
    build_output_row,
)
from app.services.request_parser import ParsedRequestRow


def test_generated_columns_include_required_updated_fields():
    labels = [label for _, label in GENERATED_COLUMNS]
    assert labels[-2:] == ["Updated By", "Updated At"]
    assert "Total Price" in labels
    assert labels[4] == "Photo"


def test_build_output_row_recalculates_total_price():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    now = utc_now_text()
    connection.execute(
        """
        INSERT INTO quotation_items (
            id, product_id, unit_price, total_price, updated_by, updated_at,
            created_by, created_at
        )
        VALUES (1, 1, 12.5, 999, 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    candidate = connection.execute("SELECT * FROM quotation_items WHERE id = 1").fetchone()

    output = build_output_row(candidate, 4)

    assert output["quantity"] == 4
    assert output["total_price"] == 50


def test_build_generation_preview_marks_multiple_candidates():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    now = utc_now_text()
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS-1', 'GTS1', 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    for item_id in (1, 2):
        connection.execute(
            """
            INSERT INTO quotation_items (
                id, product_id, unit_price, updated_by, updated_at, created_by, created_at
            )
            VALUES (?, 1, ?, 'Alice', ?, 'Alice', ?)
            """,
            (item_id, item_id * 10, now, now),
        )
    request_row = ParsedRequestRow(
        row_number=4,
        values={"gts_no_normalized": "GTS1", "oem_normalized": "", "gts_no": "GTS-1", "oem": "", "quantity": 1, "comment": ""},
        warnings=[],
        errors=[],
    )

    preview = build_generation_preview(connection, [request_row])

    assert preview[0]["status"] == "multiple_candidates"
    assert preview[0]["candidates"][0]["id"] == 2


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
        """
    )
