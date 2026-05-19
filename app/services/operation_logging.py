from datetime import datetime, timezone
from sqlite3 import Connection, Row
from contextvars import ContextVar


current_log_user_id: ContextVar[int | None] = ContextVar("current_log_user_id", default=None)


def set_current_log_user(user_id: int | None):
    return current_log_user_id.set(user_id)


def reset_current_log_user(token) -> None:
    current_log_user_id.reset(token)


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
    user_id: int | None = None,
) -> None:
    resolved_user_id = user_id if user_id is not None else current_log_user_id.get()
    columns = {
        row["name"] if isinstance(row, Row) else row[1]
        for row in connection.execute("PRAGMA table_info(operation_logs)").fetchall()
    }
    if "user_id" not in columns:
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
        return
    connection.execute(
        """
        INSERT INTO operation_logs (
            user_id,
            action_time,
            operator_name,
            action_type,
            file_name,
            row_count,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resolved_user_id,
            utc_now_text(),
            operator_name.strip(),
            action_type,
            file_name,
            row_count,
            note,
        ),
    )


def list_operation_logs(connection: Connection, limit: int = 200) -> list[Row]:
    columns = {
        row["name"] if isinstance(row, Row) else row[1]
        for row in connection.execute("PRAGMA table_info(operation_logs)").fetchall()
    }
    user_id_select = "user_id" if "user_id" in columns else "NULL AS user_id"
    return connection.execute(
        f"""
        SELECT
            id,
            {user_id_select},
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
