from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def customs_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "customs.sqlite3"
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("ENABLE_LEGACY_ACCESS_CODE", "false")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    client = TestClient(create_app())
    client.database_path = database_path
    return client


def test_customs_items_table_initializes_in_sqlite(customs_client: TestClient) -> None:
    with sqlite3.connect(customs_client.database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(customs_items)").fetchall()
        }

    assert "customs_name_cn" in columns
    assert "unit_1_source" in columns
    assert "unit_2_source" in columns
    assert "declaration_element_template" in columns


def test_admin_can_create_customs_item(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)

    response = create_customs_item(customs_client)

    assert response.status_code == 303
    assert response.headers["location"] == "/customs/items/1"
    detail = customs_client.get("/customs/items/1")
    assert "减震器" in detail.text
    assert "毛重" in detail.text


def test_merchandiser_can_create_customs_item(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)
    create_user(customs_client, role="merchandiser", username="merch", password="merch-pass")
    customs_client.post("/logout")
    customs_client.post("/login", data={"username": "merch", "password": "merch-pass"})

    response = create_customs_item(
        customs_client,
        customs_name_cn="支架",
        hs_code="8302",
        confirm_password="merch-pass",
    )

    assert response.status_code == 303
    assert customs_client.get(response.headers["location"]).status_code == 200


def test_sales_can_view_but_cannot_create(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)
    create_customs_item(customs_client)
    create_user(customs_client, role="sales", username="sales", password="sales-pass")
    customs_client.post("/logout")
    customs_client.post("/login", data={"username": "sales", "password": "sales-pass"})

    list_page = customs_client.get("/customs/items")
    blocked_new = customs_client.get("/customs/items/new", follow_redirects=False)
    blocked_create = create_customs_item(customs_client, follow_redirects=False)

    assert list_page.status_code == 200
    assert "减震器" in list_page.text
    assert "新增报关资料" not in list_page.text
    assert blocked_new.status_code == 303
    assert blocked_new.headers["location"] == "/forbidden"
    assert blocked_create.status_code == 303
    assert blocked_create.headers["location"] == "/forbidden"


def test_old_hs_code_get_routes_redirect_to_customs(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)

    home_response = customs_client.get("/hs-codes", follow_redirects=False)
    upload_response = customs_client.get("/hs-codes/upload", follow_redirects=False)
    generate_response = customs_client.get("/hs-codes/generate", follow_redirects=False)
    report_response = customs_client.get("/hs-codes/report", follow_redirects=False)

    assert home_response.status_code == 303
    assert home_response.headers["location"] == "/customs"
    assert upload_response.status_code == 303
    assert upload_response.headers["location"] == "/customs/upload"
    assert generate_response.status_code == 303
    assert generate_response.headers["location"] == "/customs/export"
    assert report_response.status_code == 303
    assert report_response.headers["location"] == "/customs/export"


def test_customs_center_links_master_upload_and_export(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)

    response = customs_client.get("/customs")

    assert response.status_code == 200
    assert 'href="/customs/items"' in response.text
    assert 'href="/customs/upload"' in response.text
    assert 'href="/customs/export"' in response.text
    assert "报关资料库" in response.text


def test_create_requires_password_confirmation(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)

    response = create_customs_item(customs_client, confirm_password="wrong")

    assert response.status_code == 400
    assert "密码确认失败，操作已取消。" in response.text


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("customs_name_cn", "", "请填写报关中文品名。"),
        ("hs_code", "", "请填写 HS Code。"),
        ("unit_1", "", "请填写第一单位。"),
        ("unit_1_source", "", "请选择第一单位来源。"),
    ],
)
def test_required_validation_blocks_create(
    customs_client: TestClient,
    field: str,
    value: str,
    expected_error: str,
) -> None:
    bootstrap_admin(customs_client)
    data = customs_item_data()
    data[field] = value

    response = customs_client.post("/customs/items/new", data=data)

    assert response.status_code == 400
    assert expected_error in response.text


def test_validation_blocks_unit_2_without_source(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)
    data = customs_item_data(unit_2="千克", unit_2_source="", unit_2_decimal_places="2")

    response = customs_client.post("/customs/items/new", data=data)

    assert response.status_code == 400
    assert "填写第二单位时必须选择第二单位来源。" in response.text


def test_validation_blocks_unit_2_source_without_unit(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)
    data = customs_item_data(unit_2="", unit_2_source="gross_weight", unit_2_decimal_places="2")

    response = customs_client.post("/customs/items/new", data=data)

    assert response.status_code == 400
    assert "选择第二单位来源时必须填写第二单位。" in response.text


def test_one_unit_gross_weight_item_can_be_saved(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)

    response = create_customs_item(
        customs_client,
        customs_name_cn="滤清器",
        hs_code="8421",
        unit_1="千克",
        unit_1_source="gross_weight",
        unit_1_decimal_places="2",
        unit_2="",
        unit_2_source="",
        unit_2_decimal_places="",
    )

    assert response.status_code == 303
    with sqlite3.connect(customs_client.database_path) as connection:
        row = connection.execute(
            "SELECT unit_1, unit_1_source, unit_2 FROM customs_items WHERE customs_name_cn = ?",
            ("滤清器",),
        ).fetchone()
    assert row == ("千克", "gross_weight", None)


def test_two_unit_item_can_be_saved(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)

    response = create_customs_item(
        customs_client,
        customs_name_cn="水泵",
        hs_code="8413",
        unit_1="台",
        unit_1_source="quantity",
        unit_1_decimal_places="0",
        unit_2="千克",
        unit_2_source="gross_weight",
        unit_2_decimal_places="2",
    )

    assert response.status_code == 303
    detail = customs_client.get(response.headers["location"])
    assert "台 / 数量 / 0 位小数" in detail.text
    assert "千克 / 毛重 / 2 位小数" in detail.text


def test_wrong_password_blocks_edit(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)
    create_customs_item(customs_client)
    data = customs_item_data(customs_name_cn="减震器更新", confirm_password="wrong")

    response = customs_client.post("/customs/items/1/edit", data=data)

    assert response.status_code == 400
    assert "密码确认失败，操作已取消。" in response.text


def test_update_and_toggle_write_operation_logs(customs_client: TestClient) -> None:
    bootstrap_admin(customs_client)
    create_customs_item(customs_client)

    update_response = customs_client.post(
        "/customs/items/1/edit",
        data=customs_item_data(customs_name_cn="减震器更新"),
        follow_redirects=False,
    )
    toggle_response = customs_client.post(
        "/customs/items/1/toggle-active",
        data={"confirm_password": "admin-pass"},
        follow_redirects=False,
    )

    assert update_response.status_code == 303
    assert toggle_response.status_code == 303
    with sqlite3.connect(customs_client.database_path) as connection:
        actions = [
            row[0]
            for row in connection.execute(
                "SELECT action_type FROM operation_logs ORDER BY id"
            ).fetchall()
        ]
    assert "customs_item_created" in actions
    assert "customs_item_updated" in actions
    assert "customs_item_deactivated" in actions


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


def create_user(
    client: TestClient,
    *,
    role: str,
    username: str,
    password: str,
) -> None:
    response = client.post(
        "/admin/users/new",
        data={
            "username": username,
            "display_name": username.title(),
            "role": role,
            "new_password": password,
            "new_password_confirm": password,
            "admin_confirm_password": "admin-pass",
        },
    )
    assert response.status_code == 200


def create_customs_item(
    client: TestClient,
    *,
    follow_redirects: bool = False,
    **overrides,
):
    return client.post(
        "/customs/items/new",
        data=customs_item_data(**overrides),
        follow_redirects=follow_redirects,
    )


def customs_item_data(**overrides) -> dict[str, str]:
    data = {
        "customs_name_cn": "减震器",
        "customs_name_en": "Shock absorber",
        "hs_code": "870880",
        "unit_1": "千克",
        "unit_1_source": "gross_weight",
        "unit_1_decimal_places": "2",
        "unit_2": "",
        "unit_2_source": "",
        "unit_2_decimal_places": "",
        "declaration_element_template": "品名：{customs_name_cn}\n用途：汽车用",
        "notes": "测试",
        "confirm_password": "admin-pass",
    }
    data.update({key: str(value) for key, value in overrides.items()})
    return data
