import sqlite3

from app.services.operation_logging import create_operation_log, list_operation_logs


def test_create_operation_log_inserts_manager_visible_row():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_time TEXT NOT NULL,
            operator_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            file_name TEXT,
            row_count INTEGER,
            note TEXT
        )
        """
    )

    create_operation_log(
        connection,
        operator_name="Alice",
        action_type="upload_full_quotation",
        file_name="quotation.xlsx",
        row_count=2,
        note="ok",
    )

    rows = list_operation_logs(connection)
    assert len(rows) == 1
    assert rows[0]["operator_name"] == "Alice"
    assert rows[0]["action_type"] == "upload_full_quotation"
    assert rows[0]["row_count"] == 2
