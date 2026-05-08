import sqlite3

from app.routes.upload import preview_has_errors, preview_has_warnings
from app.services.excel_parser import ParsedQuotationRow
from app.services.import_full_quotation import build_import_preview
from app.services.operation_logging import utc_now_text


def test_build_import_preview_adds_warnings_for_changed_latest_factory_unit_and_price():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    now = utc_now_text()
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'GTS0001', 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id, gts_no, factory, unit, unit_price,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'Factory A', 'PCS', 10, 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    parsed_row = ParsedQuotationRow(
        row_number=4,
        values={
            "gts_no": "GTS0001",
            "gts_no_normalized": "GTS0001",
            "oem": "",
            "oem_normalized": "",
            "description": "",
            "chinese_description": "",
            "factory": "Factory B",
            "unit": "SET",
            "unit_price": 12.5,
        },
        warnings=[],
        errors=[],
    )

    preview = build_import_preview(connection, [parsed_row])

    assert preview[0]["quotation_warnings"] == [
        "Factory review: this upload adds a new factory for GTS0001: Factory A -> Factory B. Please double-check before importing.",
        "Unit review: this upload adds a new unit for GTS0001: PCS -> SET. Please double-check before importing.",
        "Price review: this upload adds a new price for GTS0001: ¥10.00 -> ¥12.50. Please double-check before importing."
    ]
    assert preview_has_warnings(preview) is True
    assert preview_has_errors(preview) is False


def test_preview_has_errors_is_true_for_gts_oem_product_conflict():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    now = utc_now_text()
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, oem, oem_normalized,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'GTS0001', 'OEM-A', 'OEMA', 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, oem, oem_normalized,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (2, 'GTS0002', 'GTS0002', 'OEM-B', 'OEMB', 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    parsed_row = ParsedQuotationRow(
        row_number=4,
        values={
            "gts_no": "GTS0001",
            "gts_no_normalized": "GTS0001",
            "oem": "OEM-B",
            "oem_normalized": "OEMB",
        },
        warnings=[],
        errors=[],
    )

    preview = build_import_preview(connection, [parsed_row])

    assert preview_has_errors(preview) is True
    assert preview[0]["errors"] == [
        "GTS No. and OEM match different products. Manual review required."
    ]


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
