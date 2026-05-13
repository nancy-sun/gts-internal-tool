import sqlite3

from app.routes.upload import preview_has_errors, preview_has_warnings
from app.services.excel_parser import ParsedQuotationRow
from app.services.import_full_quotation import build_import_preview, import_preview_rows
from app.services.operation_logging import utc_now_text


class CountingConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.select_count = 0

    def execute(self, sql: str, parameters=()):
        if sql.lstrip().upper().startswith("SELECT"):
            self.select_count += 1
        return self.connection.execute(sql, parameters)


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
    previous_note = f"Alice {now[:10]}"

    assert preview[0]["quotation_warnings"] == [
        f"PCS ({previous_note}) => SET",
    ]
    assert preview[0]["quotation_changes"] == [
        {
            "field": "factory",
            "label": "工厂",
            "existing": "Factory A",
            "incoming": "Factory B",
            "previous_source": previous_note,
            "existing_with_source": f"Factory A ({previous_note})",
            "message": f"Factory A ({previous_note}) => Factory B",
        },
        {
            "field": "unit",
            "label": "单位",
            "existing": "PCS",
            "incoming": "SET",
            "previous_source": previous_note,
            "existing_with_source": f"PCS ({previous_note})",
            "message": f"PCS ({previous_note}) => SET",
        },
        {
            "field": "unit_price",
            "label": "价格",
            "existing": "¥10.00",
            "incoming": "¥12.50",
            "previous_source": previous_note,
            "existing_with_source": f"¥10.00 ({previous_note})",
            "message": f"¥10.00 ({previous_note}) => ¥12.50",
        },
    ]
    assert [choice["field"] for choice in preview[0]["required_choices"]] == [
        "factory",
        "unit_price",
    ]
    assert preview_has_warnings(preview) is True
    assert preview_has_errors(preview) is False


def test_build_import_preview_uses_batch_lookups_for_repeated_products():
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
    parsed_rows = [
        ParsedQuotationRow(
            row_number=row_number,
            values={
                "gts_no": "GTS0001",
                "gts_no_normalized": "GTS0001",
                "oem": "",
                "oem_normalized": "",
                "description": "",
                "chinese_description": "",
                "factory": "Factory A",
                "unit": "PCS",
                "unit_price": 10,
            },
            warnings=[],
            errors=[],
        )
        for row_number in (4, 5, 6)
    ]
    counting_connection = CountingConnection(connection)

    preview = build_import_preview(counting_connection, parsed_rows)

    assert [row["matched_product"]["id"] for row in preview] == [1, 1, 1]
    assert counting_connection.select_count == 2


def test_build_import_preview_adds_previous_source_to_required_oem_choice_and_product_changes():
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
        VALUES (1, 'GTS0001', 'GTS0001', 'OEM-OLD', 'OEMOLD',
                'Old description', 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    parsed_row = ParsedQuotationRow(
        row_number=4,
        values={
            "gts_no": "GTS0001",
            "gts_no_normalized": "GTS0001",
            "oem": "OEM-NEW",
            "oem_normalized": "OEMNEW",
            "description": "New description",
            "chinese_description": "",
            "factory": "Factory A",
            "unit": "PCS",
            "unit_price": 10,
        },
        warnings=[],
        errors=[],
    )

    preview = build_import_preview(connection, [parsed_row])

    previous_note = f"Alice {now[:10]}"
    assert preview[0]["required_choices"][0] == {
        "field": "oem",
        "label": "OEM",
        "existing": "OEM-OLD",
        "incoming": "OEM-NEW",
        "previous_source": previous_note,
        "existing_with_source": f"OEM-OLD ({previous_note})",
        "message": f"OEM-OLD ({previous_note}) => OEM-NEW",
    }
    assert preview[0]["product_changes"][0] == {
        "field": "description",
        "existing": "Old description",
        "incoming": "New description",
        "previous_source": previous_note,
        "existing_with_source": f"Old description ({previous_note})",
    }


def test_build_import_preview_requires_choices_for_gts_oem_factory_and_price_changes():
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
        VALUES (1, 'GTS-OLD', 'GTSOLD', 'OEM-OLD', 'OEMOLD',
                'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id, gts_no, gts_no_normalized, factory, unit, unit_price,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS-OLD', 'GTSOLD', 'Factory A', 'PCS', 10,
                'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    parsed_row = ParsedQuotationRow(
        row_number=4,
        values={
            "gts_no": "GTS-NEW",
            "gts_no_normalized": "GTSNEW",
            "oem": "OEM-OLD",
            "oem_normalized": "OEMOLD",
            "factory": "Factory B",
            "unit": "PCS",
            "unit_price": 12,
        },
        warnings=[],
        errors=[],
    )

    preview = build_import_preview(connection, [parsed_row])

    assert [choice["field"] for choice in preview[0]["required_choices"]] == [
        "gts_no",
        "factory",
        "unit_price",
    ]


def test_import_preview_rows_requires_old_new_choice_before_importing_changed_key_fields():
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
        VALUES (1, 'GTSTEST014', 'GTSTEST014', '7482541385', '7482541385',
                'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    preview_rows = [
        {
            "row_number": 17,
            "errors": [],
            "required_choices": [
                {
                    "field": "oem",
                    "existing": "7482541385",
                    "incoming": "1482541385",
                }
            ],
            "values": {
                "gts_no": "GTSTEST014",
                "gts_no_normalized": "GTSTEST014",
                "oem": "1482541385",
                "oem_normalized": "1482541385",
                "factory": "鼎佳",
                "unit": "pc",
                "unit_price": 600,
            },
        }
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Nancy Sun",
        file_name="missing-choice.xlsx",
        selected_updates=set(),
        required_choices={},
    )

    assert result["failed_rows"] == 1
    assert result["inserted_items"] == 0


def test_import_preview_rows_updates_required_oem_choice_even_when_quote_is_duplicate():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    old_timestamp = "2026-01-01T00:00:00+00:00"
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, oem, oem_normalized,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTSTEST014', 'GTSTEST014', '7482541385', '7482541385',
                'Alice', ?, 'Alice', ?)
        """,
        (old_timestamp, old_timestamp),
    )
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id, gts_no, gts_no_normalized, oem, oem_normalized,
            factory, unit, unit_price, created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTSTEST014', 'GTSTEST014', '7482541385', '7482541385',
                '鼎佳', 'pc', 600, 'Alice', ?, 'Alice', ?)
        """,
        (old_timestamp, old_timestamp),
    )
    preview_rows = [
        {
            "row_number": 17,
            "errors": [],
            "required_choices": [
                {
                    "field": "oem",
                    "existing": "7482541385",
                    "incoming": "1482541385",
                }
            ],
            "values": {
                "gts_no": "GTSTEST014",
                "gts_no_normalized": "GTSTEST014",
                "oem": "1482541385",
                "oem_normalized": "1482541385",
                "factory": "鼎佳",
                "unit": "pc",
                "unit_price": 600,
            },
        }
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Nancy Sun",
        file_name="required-choice.xlsx",
        selected_updates=set(),
        required_choices={(17, "oem"): "new"},
    )

    product = connection.execute("SELECT * FROM products WHERE id = 1").fetchone()
    item_count = connection.execute("SELECT COUNT(*) AS c FROM quotation_items").fetchone()["c"]
    quotation_item = connection.execute(
        "SELECT updated_by, updated_at FROM quotation_items WHERE id = 1"
    ).fetchone()
    assert result["updated_products"] == 1
    assert result["confirmed_duplicates"] == 1
    assert item_count == 1
    assert product["oem"] == "1482541385"
    assert product["oem_normalized"] == "1482541385"
    assert quotation_item["updated_by"] == "Nancy Sun"
    assert quotation_item["updated_at"] != old_timestamp


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
        "GTS 和 OEM 匹配到不同产品，需要人工确认。"
    ]


def test_import_preview_rows_refreshes_exact_duplicate_quotation_item():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    old_timestamp = "2026-01-01T00:00:00+00:00"
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, oem, oem_normalized, description,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTSTEST001', 'GTSTEST001', '5010225393', '5010225393',
                'Existing description', 'Alice', ?, 'Alice', ?)
        """,
        (old_timestamp, old_timestamp),
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
        (old_timestamp, old_timestamp),
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
    quotation_item = connection.execute(
        "SELECT updated_by, updated_at FROM quotation_items WHERE id = 1"
    ).fetchone()
    assert result["inserted_items"] == 0
    assert result["updated_products"] == 0
    assert result["confirmed_duplicates"] == 1
    assert item_count == 1
    assert product["description"] == "Existing description"
    assert quotation_item["updated_by"] == "Bob"
    assert quotation_item["updated_at"] != old_timestamp


def test_import_preview_rows_refreshes_duplicate_when_same_gts_factory_unit_and_price_with_different_oem():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    old_timestamp = "2026-01-01T00:00:00+00:00"
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, oem, oem_normalized,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTSTEST014', 'GTSTEST014', '7482541385', '7482541385',
                'Alice', ?, 'Alice', ?)
        """,
        (old_timestamp, old_timestamp),
    )
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id, gts_no, gts_no_normalized, oem, oem_normalized,
            factory, unit, unit_price, created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTSTEST014', 'GTSTEST014', '7482541385', '7482541385',
                '鼎佳', 'pc', 600, 'Alice', ?, 'Alice', ?)
        """,
        (old_timestamp, old_timestamp),
    )
    preview_rows = [
        {
            "row_number": 17,
            "errors": [],
            "values": {
                "gts_no": "GTSTEST014",
                "gts_no_normalized": "GTSTEST014",
                "oem": "1482541385",
                "oem_normalized": "1482541385",
                "factory": "鼎佳",
                "unit": "pc",
                "unit_price": 600,
            },
        }
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Nancy Sun",
        file_name="duplicate-oem.xlsx",
        selected_updates=set(),
    )

    item_count = connection.execute("SELECT COUNT(*) AS c FROM quotation_items").fetchone()["c"]
    quotation_item = connection.execute(
        "SELECT updated_by, updated_at FROM quotation_items WHERE id = 1"
    ).fetchone()
    assert result["inserted_items"] == 0
    assert result["confirmed_duplicates"] == 1
    assert item_count == 1
    assert quotation_item["updated_by"] == "Nancy Sun"
    assert quotation_item["updated_at"] != old_timestamp


def test_import_preview_rows_imports_unit_warning_without_required_choice():
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
            "quotation_changes": [{"field": "unit", "message": "PCS => SET"}],
            "values": {
                "gts_no": "GTS0001",
                "gts_no_normalized": "GTS0001",
                "oem": "",
                "oem_normalized": "",
                "factory": "Factory A",
                "unit": "SET",
                "unit_price": 10,
            },
        }
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Bob",
        file_name="unit-warning.xlsx",
        selected_updates=set(),
    )

    item_count = connection.execute("SELECT COUNT(*) AS c FROM quotation_items").fetchone()["c"]
    latest_unit = connection.execute(
        "SELECT unit FROM quotation_items ORDER BY id DESC LIMIT 1"
    ).fetchone()["unit"]
    assert result["inserted_items"] == 1
    assert item_count == 2
    assert latest_unit == "SET"


def test_import_preview_rows_applies_required_old_price_choice_and_refreshes_duplicate():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    old_timestamp = "2026-01-01T00:00:00+00:00"
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'GTS0001', 'Alice', ?, 'Alice', ?)
        """,
        (old_timestamp, old_timestamp),
    )
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id, gts_no, gts_no_normalized, factory, unit, unit_price,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'GTS0001', 'Factory A', 'PCS', 10, 'Alice', ?, 'Alice', ?)
        """,
        (old_timestamp, old_timestamp),
    )
    preview_rows = [
        {
            "row_number": 4,
            "errors": [],
            "required_choices": [
                {
                    "field": "unit_price",
                    "existing": "¥10.00",
                    "incoming": "¥12.50",
                }
            ],
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
        required_choices={(4, "unit_price"): "old"},
    )

    item_count = connection.execute("SELECT COUNT(*) AS c FROM quotation_items").fetchone()["c"]
    latest_price = connection.execute(
        "SELECT unit_price FROM quotation_items ORDER BY id DESC LIMIT 1"
    ).fetchone()["unit_price"]
    quotation_item = connection.execute(
        "SELECT updated_by, updated_at FROM quotation_items WHERE id = 1"
    ).fetchone()
    assert result["inserted_items"] == 0
    assert result["confirmed_duplicates"] == 1
    assert item_count == 1
    assert latest_price == 10
    assert quotation_item["updated_by"] == "Bob"
    assert quotation_item["updated_at"] != old_timestamp


def test_import_preview_rows_updates_only_selected_product_fields():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_test_schema(connection)
    now = utc_now_text()
    connection.execute(
        """
        INSERT INTO products (
            id, gts_no, gts_no_normalized, description, chinese_description,
            created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'GTS0001', 'Old English', '旧品名', 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    preview_rows = [
        {
            "row_number": 4,
            "errors": [],
            "quotation_changes": [],
            "values": {
                "gts_no": "GTS0001",
                "gts_no_normalized": "GTS0001",
                "oem": "",
                "oem_normalized": "",
                "description": "New English",
                "chinese_description": "新品名",
                "factory": "Factory A",
                "unit": "PCS",
                "unit_price": 10,
            },
        }
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Bob",
        file_name="product_update.xlsx",
        selected_updates={(4, "chinese_description")},
    )

    product = connection.execute("SELECT * FROM products WHERE id = 1").fetchone()
    log = connection.execute("SELECT * FROM operation_logs ORDER BY id DESC LIMIT 1").fetchone()
    assert result["updated_products"] == 1
    assert result["inserted_items"] == 1
    assert product["description"] == "Old English"
    assert product["chinese_description"] == "新品名"
    assert product["updated_by"] == "Bob"
    assert log["action_type"] == "upload_full_quotation"
    assert log["row_count"] == 1


def test_import_preview_rows_returns_post_upload_audit_summary():
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
        VALUES (1, 'GTS0001', 'GTS0001', 'OEM1', 'OEM1', 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id, gts_no, gts_no_normalized, oem, oem_normalized,
            factory, unit, unit_price, created_by, created_at, updated_by, updated_at
        )
        VALUES (1, 'GTS0001', 'GTS0001', 'OEM1', 'OEM1',
                'Factory A', 'pc', 10, 'Alice', ?, 'Alice', ?)
        """,
        (now, now),
    )
    preview_rows = [
        {
            "row_number": 4,
            "errors": [],
            "required_choices": [
                {
                    "field": "factory",
                    "label": "工厂",
                    "existing": "Factory A",
                    "incoming": "Factory B",
                },
                {
                    "field": "unit_price",
                    "label": "价格",
                    "existing": "¥10.00",
                    "incoming": "¥12.50",
                },
            ],
            "values": {
                "gts_no": "GTS0001",
                "gts_no_normalized": "GTS0001",
                "oem": "OEM1",
                "oem_normalized": "OEM1",
                "factory": "Factory B",
                "unit": "pc",
                "unit_price": 12.5,
            },
        },
        {
            "row_number": 5,
            "errors": [],
            "values": {
                "gts_no": "GTS0001",
                "gts_no_normalized": "GTS0001",
                "oem": "OEM1",
                "oem_normalized": "OEM1",
                "factory": "Factory A",
                "unit": "pc",
                "unit_price": 10,
            },
        },
        {
            "row_number": 6,
            "errors": ["工厂不能为空。"],
            "values": {},
        },
    ]

    result = import_preview_rows(
        connection,
        preview_rows=preview_rows,
        operator_name="Bob",
        file_name="audit.xlsx",
        selected_updates=set(),
        required_choices={(4, "factory"): "new", (4, "unit_price"): "new"},
    )

    assert result["inserted_items"] == 1
    assert result["confirmed_duplicates"] == 1
    assert result["failed_rows"] == 1
    assert result["audit"]["changes"] == [
        {
            "row_number": 4,
            "field": "factory",
            "label": "工厂",
            "existing": "Factory A",
            "incoming": "Factory B",
            "decision": "使用新值",
        },
        {
            "row_number": 4,
            "field": "unit_price",
            "label": "价格",
            "existing": "¥10.00",
            "incoming": "¥12.50",
            "decision": "使用新值",
        },
    ]
    assert result["audit"]["duplicates"] == [
        {
            "row_number": 5,
            "gts_no": "GTS0001",
            "oem": "OEM1",
            "factory": "Factory A",
            "unit": "pc",
            "unit_price": "¥10.00",
        }
    ]
    assert result["audit"]["failed"] == [
        {"row_number": 6, "message": "工厂不能为空。"}
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
