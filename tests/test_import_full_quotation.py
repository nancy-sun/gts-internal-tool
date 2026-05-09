import sqlite3

from app.routes.upload import preview_has_errors, preview_has_warnings
from app.services.excel_parser import ParsedQuotationRow
from app.services.import_full_quotation import build_import_preview, import_preview_rows
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
        "Factory A => Factory B",
        "PCS => SET",
        "¥10.00 => ¥12.50",
    ]
    assert preview[0]["quotation_changes"] == [
        {
            "field": "factory",
            "label": "Factory",
            "existing": "Factory A",
            "incoming": "Factory B",
            "message": "Factory A => Factory B",
        },
        {
            "field": "unit",
            "label": "Unit",
            "existing": "PCS",
            "incoming": "SET",
            "message": "PCS => SET",
        },
        {
            "field": "unit_price",
            "label": "Price",
            "existing": "¥10.00",
            "incoming": "¥12.50",
            "message": "¥10.00 => ¥12.50",
        },
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


def test_import_preview_rows_skips_exact_duplicate_quotation_item():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    now = utc_now_text()
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, oem, oem_normalized, description,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTSTEST001', 'GTSTEST001', '5010225393', '5010225393',
                'Existing description', 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id, gts_no, gts_no_normalized, oem, oem_normalized,
            factory, unit, unit_price, created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTSTEST001', 'GTSTEST001', '5010225393', '5010225393',
                '欧达', 'pc', 999, 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    preview_rows = [
        {
            "row_number": 4,
            "errors": [],
            "values": {
                "gts_no": "GTSTEST001",
                "gts_no_normalized": "GTSTEST001",
                "oem": "5010225393",
                "oem_normalized": "5010225393",
                "description": "Should not update",
                "chinese_description": "",
                "factory": "欧达",
                "unit": "pc",
                "unit_price": 999,
            },
        }
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Bob",
        file_name="duplicate.xlsx",
        selected_updates={(4, "description")},
    )

    product = connection.execute("SELECT * FROM products WHERE id = 1").fetchone()
    item_count = connection.execute("SELECT COUNT(*) AS c FROM quotation_items").fetchone()["c"]
    assert result["inserted_items"] == 0
    assert result["updated_products"] == 0
    assert result["skipped_duplicates"] == 1
    assert item_count == 1
    assert product["description"] == "Existing description"


def test_import_preview_rows_skips_unapproved_quotation_change():
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
            product_id, gts_no, gts_no_normalized, factory, unit, unit_price,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'GTS0001', 'Factory A', 'PCS', 10, 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    preview_rows = [
        {
            "row_number": 4,
            "errors": [],
            "quotation_changes": [{"field": "unit_price", "message": "¥10.00 => ¥12.50"}],
            "values": {
                "gts_no": "GTS0001",
                "gts_no_normalized": "GTS0001",
                "oem": "",
                "oem_normalized": "",
                "factory": "Factory A",
                "unit": "PCS",
                "unit_price": 12.5,
            },
        }
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Bob",
        file_name="changed.xlsx",
        selected_updates=set(),
        selected_quotation_changes=set(),
    )

    item_count = connection.execute("SELECT COUNT(*) AS c FROM quotation_items").fetchone()["c"]
    assert result["inserted_items"] == 0
    assert result["skipped_unapproved_changes"] == 1
    assert item_count == 1


def test_import_preview_rows_imports_approved_quotation_change():
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
            product_id, gts_no, gts_no_normalized, factory, unit, unit_price,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'GTS0001', 'Factory A', 'PCS', 10, 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    preview_rows = [
        {
            "row_number": 4,
            "errors": [],
            "quotation_changes": [{"field": "unit_price", "message": "¥10.00 => ¥12.50"}],
            "values": {
                "gts_no": "GTS0001",
                "gts_no_normalized": "GTS0001",
                "oem": "",
                "oem_normalized": "",
                "factory": "Factory A",
                "unit": "PCS",
                "unit_price": 12.5,
            },
        }
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Bob",
        file_name="changed.xlsx",
        selected_updates=set(),
        selected_quotation_changes={4},
    )

    item_count = connection.execute("SELECT COUNT(*) AS c FROM quotation_items").fetchone()["c"]
    latest_price = connection.execute(
        "SELECT unit_price FROM quotation_items ORDER BY id DESC LIMIT 1"
    ).fetchone()["unit_price"]
    assert result["inserted_items"] == 1
    assert result["skipped_unapproved_changes"] == 0
    assert item_count == 2
    assert latest_price == 12.5


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

        CREATE TABLE operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_time TEXT NOT NULL,
            operator_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            file_name TEXT,
            row_count INTEGER,
            note TEXT
        );
        """
    )
