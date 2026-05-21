from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.passwords import hash_password, verify_password


ACCESS_CODE = "test-access-code"


@pytest.fixture()
def auth_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "auth-users.sqlite3"
    monkeypatch.setenv("SHARED_ACCESS_CODE", ACCESS_CODE)
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "55123511")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    client = TestClient(create_app())
    client.database_path = database_path
    return client


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password_hash = hash_password("secret-password")

    assert password_hash != "secret-password"
    assert verify_password("secret-password", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_setup_admin_works_once_and_login_logout_flow(auth_client: TestClient) -> None:
    login_redirect = auth_client.get("/login", follow_redirects=False)
    assert login_redirect.status_code == 303
    assert login_redirect.headers["location"] == "/setup-admin"

    setup_response = auth_client.post(
        "/setup-admin",
        data={
            "username": "admin",
            "display_name": "Admin User",
            "password": "admin-pass",
            "confirm_password": "admin-pass",
        },
        follow_redirects=False,
    )
    assert setup_response.status_code == 303
    assert setup_response.headers["location"] == "/"

    disabled_setup = auth_client.get("/setup-admin", follow_redirects=False)
    assert disabled_setup.status_code == 303
    assert disabled_setup.headers["location"] == "/login"

    logout_response = auth_client.post("/logout", follow_redirects=False)
    assert logout_response.status_code == 303
    login_page = auth_client.get("/login")
    assert "没有账号请联系管理员创建账号" in login_page.text

    bad_login = auth_client.post(
        "/login",
        data={"username": "admin", "password": "wrong"},
    )
    assert bad_login.status_code == 401

    login_response = auth_client.post(
        "/login",
        data={"username": "admin", "password": "admin-pass"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303


def test_admin_shortcut_and_not_found_pages_are_handled(auth_client: TestClient) -> None:
    unauthenticated_missing = auth_client.get("/not-a-real-page", follow_redirects=False)
    assert unauthenticated_missing.status_code == 303
    assert unauthenticated_missing.headers["location"] == "/login"

    bootstrap_admin(auth_client)

    admin_shortcut = auth_client.get("/admin", follow_redirects=False)
    assert admin_shortcut.status_code == 303
    assert admin_shortcut.headers["location"] == "/admin/users"

    missing_page = auth_client.get("/not-a-real-page")
    assert missing_page.status_code == 404
    assert "页面不存在" in missing_page.text
    assert '{"detail":"Not Found"}' not in missing_page.text


def test_admin_can_manage_users_and_non_admin_cannot(auth_client: TestClient) -> None:
    bootstrap_admin(auth_client)
    admin_page = auth_client.get("/admin/users")
    assert "管理员" in admin_page.text

    blocked_create = auth_client.post(
        "/admin/users/new",
        data={
            "username": "blocked",
            "display_name": "Blocked User",
            "role": "sales",
            "new_password": "blocked-pass",
            "new_password_confirm": "blocked-pass",
            "admin_confirm_password": "wrong",
        },
    )
    assert blocked_create.status_code == 400
    assert "密码确认失败" in blocked_create.text

    create_response = auth_client.post(
        "/admin/users/new",
        data={
            "username": "sales1",
            "display_name": "Sales One",
            "role": "sales",
            "new_password": "sales-pass",
            "new_password_confirm": "sales-pass",
            "admin_confirm_password": "admin-pass",
            "must_change_password": "1",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303
    assert create_response.headers["location"] == "/admin/users"
    create_list_page = auth_client.get("/admin/users")
    assert "已新增用户：Sales One" in create_list_page.text
    assert 'role="status"' in create_list_page.text
    edit_page = auth_client.get("/admin/users/2/edit")
    assert "业务员" in edit_page.text
    assert "跟单" in edit_page.text
    assert ">sales<" not in edit_page.text
    assert ">merchandiser<" not in edit_page.text

    blocked_edit = auth_client.post(
        "/admin/users/2/edit",
        data={
            "username": "sales-renamed",
            "display_name": "Sales Renamed",
            "role": "merchandiser",
            "admin_confirm_password": "wrong",
        },
    )
    assert blocked_edit.status_code == 400
    assert "密码确认失败" in blocked_edit.text

    edit_response = auth_client.post(
        "/admin/users/2/edit",
        data={
            "username": "sales-renamed",
            "display_name": "Sales Renamed",
            "role": "merchandiser",
            "admin_confirm_password": "admin-pass",
        },
        follow_redirects=False,
    )
    assert edit_response.status_code == 303
    user_list = auth_client.get("/admin/users")
    assert "跟单" in user_list.text
    assert "merchandiser</td>" not in user_list.text
    assert 'action="/admin/users/2/toggle-active"' not in user_list.text
    assert 'action="/admin/users/2/delete"' not in user_list.text
    edit_page = auth_client.get("/admin/users/2/edit")
    assert 'action="/admin/users/2/status"' in edit_page.text
    assert 'action="/admin/users/2/toggle-active"' not in edit_page.text
    assert 'action="/admin/users/2/delete"' not in edit_page.text
    assert edit_page.text.count('id="status_admin_confirm_password"') == 1
    assert "历史记录会保留操作人姓名" in edit_page.text
    assert "data-user-delete-confirmation" in edit_page.text
    assert "data-user-delete-button disabled" in edit_page.text

    deactivate_response = auth_client.post(
        "/admin/users/2/status",
        data={"admin_confirm_password": "admin-pass", "status_action": "toggle_active"},
        follow_redirects=False,
    )
    assert deactivate_response.status_code == 303

    auth_client.post("/logout")
    inactive_login = auth_client.post(
        "/login",
        data={"username": "sales-renamed", "password": "sales-pass"},
    )
    assert inactive_login.status_code == 401

    auth_client.post("/login", data={"username": "admin", "password": "admin-pass"})
    blocked_toggle = auth_client.post(
        "/admin/users/2/status",
        data={"admin_confirm_password": "wrong", "status_action": "toggle_active"},
    )
    assert blocked_toggle.status_code == 400
    assert "密码确认失败" in blocked_toggle.text
    auth_client.post(
        "/admin/users/2/status",
        data={"admin_confirm_password": "admin-pass", "status_action": "toggle_active"},
    )
    auth_client.post("/logout")
    auth_client.post("/login", data={"username": "sales-renamed", "password": "sales-pass"})
    forbidden_response = auth_client.get("/admin/users")
    assert forbidden_response.status_code == 403


def test_must_change_password_is_enforced(auth_client: TestClient) -> None:
    bootstrap_admin(auth_client)
    auth_client.post(
        "/admin/users/new",
        data={
            "username": "temp",
            "display_name": "Temp User",
            "role": "sales",
            "new_password": "temp-pass",
            "new_password_confirm": "temp-pass",
            "admin_confirm_password": "admin-pass",
            "must_change_password": "1",
        },
    )
    auth_client.post("/logout")
    auth_client.post("/login", data={"username": "temp", "password": "temp-pass"})

    upload_response = auth_client.get("/upload", follow_redirects=False)
    assert upload_response.status_code == 303
    assert upload_response.headers["location"] == "/change-password"

    wrong_change = auth_client.post(
        "/change-password",
        data={
            "current_password": "wrong",
            "new_password": "new-temp-pass",
            "confirm_password": "new-temp-pass",
        },
    )
    assert wrong_change.status_code == 400
    assert "当前密码不正确" in wrong_change.text

    change_response = auth_client.post(
        "/change-password",
        data={
            "current_password": "temp-pass",
            "new_password": "new-temp-pass",
            "confirm_password": "new-temp-pass",
        },
        follow_redirects=False,
    )
    assert change_response.status_code == 303

    with sqlite3.connect(auth_client.database_path) as connection:
        must_change = connection.execute(
            "SELECT must_change_password FROM users WHERE username = 'temp'"
        ).fetchone()[0]
    assert must_change == 0
    assert auth_client.get("/upload").status_code == 200


def test_business_pages_require_login_and_noindex_headers(auth_client: TestClient) -> None:
    for path in (
        "/",
        "/upload",
        "/generate",
        "/search",
        "/suppliers",
        "/hs-codes/upload",
        "/logs",
        "/maintenance",
        "/admin/users",
    ):
        response = auth_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"

    robots_response = auth_client.get("/robots.txt")
    assert robots_response.status_code == 200
    assert "Disallow: /" in robots_response.text
    assert robots_response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"


def test_legacy_access_code_is_disabled_by_default_and_cannot_access_admin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHARED_ACCESS_CODE", ACCESS_CODE)
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "legacy-disabled.sqlite3"))
    monkeypatch.setenv("ENABLE_LEGACY_ACCESS_CODE", "false")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    client = TestClient(create_app())
    bootstrap_admin(client)
    client.post("/logout")

    disabled_login = client.post("/login", data={"access_code": ACCESS_CODE})
    assert disabled_login.status_code == 401

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "legacy-enabled.sqlite3"))
    monkeypatch.setenv("ENABLE_LEGACY_ACCESS_CODE", "true")
    get_settings.cache_clear()
    legacy_client = TestClient(create_app())
    bootstrap_admin(legacy_client)
    legacy_client.post("/logout")

    legacy_login = legacy_client.post(
        "/login",
        data={"access_code": ACCESS_CODE},
        follow_redirects=False,
    )
    assert legacy_login.status_code == 303
    home_response = legacy_client.get("/")
    assert home_response.status_code == 200
    assert "当前为临时访问模式" in home_response.text
    admin_response = legacy_client.get("/admin/users")
    assert admin_response.status_code == 403
    get_settings.cache_clear()


def test_delete_user_rules_and_operation_log_user_id(auth_client: TestClient) -> None:
    bootstrap_admin(auth_client)
    auth_client.post(
        "/admin/users/new",
        data={
            "username": "unused",
            "display_name": "Unused User",
            "role": "sales",
            "new_password": "unused-pass",
            "new_password_confirm": "unused-pass",
            "admin_confirm_password": "admin-pass",
        },
    )
    auth_client.post(
        "/admin/users/new",
        data={
            "username": "logged",
            "display_name": "Logged User",
            "role": "sales",
            "new_password": "logged-pass",
            "new_password_confirm": "logged-pass",
            "admin_confirm_password": "admin-pass",
        },
    )

    with sqlite3.connect(auth_client.database_path) as connection:
        connection.execute(
            """
            INSERT INTO operation_logs (
                user_id, action_time, operator_name, action_type
            )
            VALUES (3, '2026-01-01T00:00:00+00:00', 'Logged User', 'test')
            """
        )

    delete_self = auth_client.post(
        "/admin/users/1/status",
        data={
            "admin_confirm_password": "admin-pass",
            "status_action": "delete",
            "confirm_delete": "1",
        },
    )
    assert delete_self.status_code == 400
    assert "不能删除当前登录账号" in delete_self.text

    missing_confirmation = auth_client.post(
        "/admin/users/3/status",
        data={"admin_confirm_password": "admin-pass", "status_action": "delete"},
    )
    assert missing_confirmation.status_code == 400
    assert "请先确认" in missing_confirmation.text

    wrong_password = auth_client.post(
        "/admin/users/2/status",
        data={
            "admin_confirm_password": "wrong",
            "status_action": "delete",
            "confirm_delete": "1",
        },
    )
    assert wrong_password.status_code == 400
    assert "密码确认失败" in wrong_password.text

    delete_unused = auth_client.post(
        "/admin/users/2/status",
        data={
            "admin_confirm_password": "admin-pass",
            "status_action": "delete",
            "confirm_delete": "1",
        },
        follow_redirects=False,
    )
    assert delete_unused.status_code == 303

    delete_logged = auth_client.post(
        "/admin/users/3/status",
        data={
            "admin_confirm_password": "admin-pass",
            "status_action": "delete",
            "confirm_delete": "1",
        },
        follow_redirects=False,
    )
    assert delete_logged.status_code == 303

    with sqlite3.connect(auth_client.database_path) as connection:
        user_ids = [row[0] for row in connection.execute("SELECT id FROM users").fetchall()]
        retained_log = connection.execute(
            "SELECT user_id, operator_name FROM operation_logs WHERE action_type = 'test'"
        ).fetchone()
        deleted_log = connection.execute(
            """
            SELECT user_id, operator_name, note
            FROM operation_logs
            WHERE action_type = 'user_deleted'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        log_user_ids = [
            row[0]
            for row in connection.execute(
                "SELECT user_id FROM operation_logs WHERE action_type = 'user_created'"
            ).fetchall()
        ]
    assert 2 not in user_ids
    assert 3 not in user_ids
    assert retained_log == (None, "Logged User")
    assert deleted_log == (1, "Admin User", "logged / Logged User")
    assert log_user_ids
    assert all(user_id == 1 for user_id in log_user_ids)


def test_admin_reset_password_requires_admin_password(auth_client: TestClient) -> None:
    bootstrap_admin(auth_client)
    auth_client.post(
        "/admin/users/new",
        data={
            "username": "reset-user",
            "display_name": "Reset User",
            "role": "sales",
            "new_password": "old-pass",
            "new_password_confirm": "old-pass",
            "admin_confirm_password": "admin-pass",
        },
    )

    blocked_reset = auth_client.post(
        "/admin/users/2/reset-password",
        data={
            "new_password": "new-pass",
            "new_password_confirm": "new-pass",
            "admin_confirm_password": "wrong",
        },
    )
    assert blocked_reset.status_code == 400
    assert "密码确认失败" in blocked_reset.text

    reset_response = auth_client.post(
        "/admin/users/2/reset-password",
        data={
            "new_password": "new-pass",
            "new_password_confirm": "new-pass",
            "admin_confirm_password": "admin-pass",
        },
        follow_redirects=False,
    )
    assert reset_response.status_code == 303

    auth_client.post("/logout")
    assert auth_client.post(
        "/login",
        data={"username": "reset-user", "password": "old-pass"},
    ).status_code == 401
    assert auth_client.post(
        "/login",
        data={"username": "reset-user", "password": "new-pass"},
        follow_redirects=False,
    ).status_code == 303


def bootstrap_admin(client: TestClient) -> None:
    response = client.post(
        "/setup-admin",
        data={
            "username": "admin",
            "display_name": "Admin User",
            "password": "admin-pass",
            "confirm_password": "admin-pass",
        },
    )
    assert response.status_code == 200
