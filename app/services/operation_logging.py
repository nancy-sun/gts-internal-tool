from datetime import datetime, timezone
from sqlite3 import Connection, Row


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_operation_log(
    connection: Connection,
    *,
    operator_name: str,
    action_type: str,
    file_name: str | None = None,
    row_count: int | None = None,
    note: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO operation_logs (
            action_time,
            operator_name,
            action_type,
            file_name,
            row_count,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now_text(),
            operator_name.strip(),
            action_type,
            file_name,
            row_count,
            note,
        ),
    )


def list_operation_logs(connection: Connection, limit: int = 200) -> list[Row]:
    return connection.execute(
        """
        SELECT
            id,
            action_time,
            operator_name,
            action_type,
            file_name,
            row_count,
            note
        FROM operation_logs
        ORDER BY action_time DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
