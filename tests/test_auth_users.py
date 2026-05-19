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


def test_admin_can_manage_users_and_non_admin_cannot(auth_client: TestClient) -> None:
    bootstrap_admin(auth_client)

    create_response = auth_client.post(
        "/admin/users/new",
        data={
            "username": "sales1",
            "display_name": "Sales One",
            "role": "sales",
            "password": "sales-pass",
            "confirm_password": "sales-pass",
            "must_change_password": "1",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    edit_response = auth_client.post(
        "/admin/users/2/edit",
        data={
            "username": "sales-renamed",
            "display_name": "Sales Renamed",
            "role": "merchandiser",
        },
        follow_redirects=False,
    )
    assert edit_response.status_code == 303

    deactivate_response = auth_client.post(
        "/admin/users/2/toggle-active",
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
    auth_client.post("/admin/users/2/toggle-active")
    auth_client.post("/logout")
    auth_client.post("/login", data={"username": "sales-renamed", "password": "sales-pass"})
    forbidden_response = auth_client.get("/admin/users")
    assert forbidden_response.status_code == 403


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


def test_delete_user_rules_and_operation_log_user_id(auth_client: TestClient) -> None:
    bootstrap_admin(auth_client)
    auth_client.post(
        "/admin/users/new",
        data={
            "username": "unused",
            "display_name": "Unused User",
            "role": "sales",
            "password": "unused-pass",
            "confirm_password": "unused-pass",
        },
    )
    auth_client.post(
        "/admin/users/new",
        data={
            "username": "logged",
            "display_name": "Logged User",
            "role": "sales",
            "password": "logged-pass",
            "confirm_password": "logged-pass",
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
        "/admin/users/1/delete",
        data={"confirm_password": "admin-pass"},
    )
    assert delete_self.status_code == 400
    assert "不能删除当前登录账号" in delete_self.text

    blocked_delete = auth_client.post(
        "/admin/users/3/delete",
        data={"confirm_password": "admin-pass"},
    )
    assert blocked_delete.status_code == 400
    assert "该用户已有操作记录，不能删除" in blocked_delete.text

    wrong_password = auth_client.post(
        "/admin/users/2/delete",
        data={"confirm_password": "wrong"},
    )
    assert wrong_password.status_code == 400
    assert "密码确认失败" in wrong_password.text

    delete_unused = auth_client.post(
        "/admin/users/2/delete",
        data={"confirm_password": "admin-pass"},
        follow_redirects=False,
    )
    assert delete_unused.status_code == 303

    with sqlite3.connect(auth_client.database_path) as connection:
        user_ids = [row[0] for row in connection.execute("SELECT id FROM users").fetchall()]
        log_user_ids = [
            row[0]
            for row in connection.execute(
                "SELECT user_id FROM operation_logs WHERE action_type = 'user_created'"
            ).fetchall()
        ]
    assert 2 not in user_ids
    assert log_user_ids
    assert all(user_id == 1 for user_id in log_user_ids)


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
