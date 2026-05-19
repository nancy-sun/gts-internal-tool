from __future__ import annotations

from sqlite3 import Connection, Row

from app.services.operation_logging import create_operation_log, utc_now_text
from app.services.passwords import hash_password, verify_password


VALID_ROLES = ("admin", "sales", "merchandiser")


def count_users(connection: Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def get_user(connection: Connection, user_id: int) -> Row | None:
    return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_username(connection: Connection, username: str) -> Row | None:
    return connection.execute(
        "SELECT * FROM users WHERE lower(username) = lower(?)",
        (username.strip(),),
    ).fetchone()


def list_users(connection: Connection) -> list[Row]:
    return connection.execute(
        """
        SELECT *
        FROM users
        ORDER BY is_active DESC, lower(username)
        """
    ).fetchall()


def create_user(
    connection: Connection,
    *,
    username: str,
    display_name: str,
    role: str,
    password: str,
    must_change_password: bool = False,
) -> tuple[int | None, list[str]]:
    errors = validate_user_values(
        connection,
        username=username,
        display_name=display_name,
        role=role,
        password=password,
    )
    if errors:
        return None, errors
    now = utc_now_text()
    cursor = connection.execute(
        """
        INSERT INTO users (
            username,
            display_name,
            role,
            password_hash,
            is_active,
            must_change_password,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            username.strip(),
            display_name.strip(),
            role,
            hash_password(password),
            1 if must_change_password else 0,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid), []


def update_user(
    connection: Connection,
    *,
    user_id: int,
    username: str,
    display_name: str,
    role: str,
    must_change_password: bool,
    operator_name: str,
) -> list[str]:
    current_user = get_user(connection, user_id)
    if not current_user:
        return ["找不到用户。"]
    errors = validate_user_values(
        connection,
        username=username,
        display_name=display_name,
        role=role,
        user_id=user_id,
    )
    if errors:
        return errors
    role_changed = current_user["role"] != role
    connection.execute(
        """
        UPDATE users
        SET username = ?,
            display_name = ?,
            role = ?,
            must_change_password = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            username.strip(),
            display_name.strip(),
            role,
            1 if must_change_password else 0,
            utc_now_text(),
            user_id,
        ),
    )
    if role_changed:
        create_operation_log(
            connection,
            operator_name=operator_name,
            action_type="user_role_changed",
            note=f"{current_user['username']}: {current_user['role']} -> {role}",
        )
    return []


def reset_user_password(
    connection: Connection,
    *,
    user_id: int,
    password: str,
    must_change_password: bool,
) -> list[str]:
    if not get_user(connection, user_id):
        return ["找不到用户。"]
    if not password:
        return ["请填写新密码。"]
    connection.execute(
        """
        UPDATE users
        SET password_hash = ?,
            must_change_password = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (hash_password(password), 1 if must_change_password else 0, utc_now_text(), user_id),
    )
    return []


def change_user_password(
    connection: Connection,
    *,
    user_id: int,
    new_password: str,
) -> list[str]:
    if not get_user(connection, user_id):
        return ["找不到用户。"]
    if not new_password:
        return ["请填写新密码。"]
    connection.execute(
        """
        UPDATE users
        SET password_hash = ?,
            must_change_password = 0,
            updated_at = ?
        WHERE id = ?
        """,
        (hash_password(new_password), utc_now_text(), user_id),
    )
    return []


def set_user_active(connection: Connection, *, user_id: int, is_active: bool) -> list[str]:
    if not get_user(connection, user_id):
        return ["找不到用户。"]
    connection.execute(
        """
        UPDATE users
        SET is_active = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (1 if is_active else 0, utc_now_text(), user_id),
    )
    return []


def delete_user_and_detach_logs(connection: Connection, *, user_id: int) -> list[str]:
    if not get_user(connection, user_id):
        return ["找不到用户。"]
    connection.execute(
        "UPDATE operation_logs SET user_id = NULL WHERE user_id = ?",
        (user_id,),
    )
    connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return []


def update_last_login(connection: Connection, user_id: int) -> None:
    connection.execute(
        "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
        (utc_now_text(), utc_now_text(), user_id),
    )


def validate_user_values(
    connection: Connection,
    *,
    username: str,
    display_name: str,
    role: str,
    password: str | None = None,
    user_id: int | None = None,
) -> list[str]:
    errors = []
    username = username.strip()
    display_name = display_name.strip()
    if not username:
        errors.append("请填写用户名。")
    if not display_name:
        errors.append("请填写显示名称。")
    if role not in VALID_ROLES:
        errors.append("请选择有效角色。")
    if password is not None and not password:
        errors.append("请填写密码。")
    existing = get_user_by_username(connection, username) if username else None
    if existing and (user_id is None or int(existing["id"]) != user_id):
        errors.append("用户名已存在。")
    return errors


def verify_user_password(user: Row, password: str) -> bool:
    return verify_password(password, user["password_hash"])
