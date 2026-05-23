from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def contracts_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "contracts.sqlite3"
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


def test_purchase_contract_tables_initialize_in_sqlite(contracts_client: TestClient) -> None:
    with sqlite3.connect(contracts_client.database_path) as connection:
        contract_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(purchase_contracts)").fetchall()
        }
        item_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(purchase_contract_items)").fetchall()
        }

    assert "contract_no" in contract_columns
    assert "supplier_id" in contract_columns
    assert "total_rmb" in contract_columns
    assert "purchase_contract_id" in item_columns
    assert "amount_rmb" in item_columns
    assert "gross_weight" in item_columns
    assert "packages" in item_columns


def test_admin_can_create_purchase_contract(contracts_client: TestClient) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)

    response = create_contract(contracts_client)

    assert response.status_code == 303
    assert response.headers["location"] == "/contracts/1"
    detail = contracts_client.get("/contracts/1")
    assert "PC-001" in detail.text
    assert "测试供应商" in detail.text


def test_merchandiser_can_create_purchase_contract(contracts_client: TestClient) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)
    create_user(contracts_client, role="merchandiser", username="merch", password="merch-pass")
    contracts_client.post("/logout")
    contracts_client.post("/login", data={"username": "merch", "password": "merch-pass"})

    response = create_contract(
        contracts_client,
        contract_no="PC-MERCH",
        confirm_password="merch-pass",
    )

    assert response.status_code == 303


def test_sales_can_view_but_cannot_create_contract(contracts_client: TestClient) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)
    create_contract(contracts_client)
    create_user(contracts_client, role="sales", username="sales", password="sales-pass")
    contracts_client.post("/logout")
    contracts_client.post("/login", data={"username": "sales", "password": "sales-pass"})

    list_page = contracts_client.get("/contracts")
    new_page = contracts_client.get("/contracts/new", follow_redirects=False)
    create_response = create_contract(
        contracts_client,
        contract_no="PC-SALES",
        confirm_password="sales-pass",
        follow_redirects=False,
    )

    assert list_page.status_code == 200
    assert "PC-001" in list_page.text
    assert "新增采购合同" not in list_page.text
    assert new_page.status_code == 303
    assert new_page.headers["location"] == "/forbidden"
    assert create_response.status_code == 303
    assert create_response.headers["location"] == "/forbidden"


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("contract_no", "", "请填写合同号。"),
        ("supplier_id", "", "请选择供应商。"),
    ],
)
def test_contract_required_validation(
    contracts_client: TestClient,
    field: str,
    value: str,
    expected_error: str,
) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)
    data = contract_data()
    data[field] = value

    response = contracts_client.post("/contracts/new", data=data)

    assert response.status_code == 400
    assert expected_error in response.text


def test_duplicate_contract_no_is_rejected(contracts_client: TestClient) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)
    create_contract(contracts_client)

    response = create_contract(contracts_client)

    assert response.status_code == 400
    assert "合同号已存在。" in response.text


def test_password_confirmation_required_for_create_and_edit(
    contracts_client: TestClient,
) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)

    create_response = create_contract(contracts_client, confirm_password="wrong")

    assert create_response.status_code == 400
    assert "密码确认失败，操作已取消。" in create_response.text

    create_contract(contracts_client)
    edit_response = contracts_client.post(
        "/contracts/1/edit",
        data=contract_data(contract_no="PC-UPDATED", confirm_password="wrong"),
    )

    assert edit_response.status_code == 400
    assert "密码确认失败，操作已取消。" in edit_response.text


def test_contract_item_can_be_added_and_totals_update(contracts_client: TestClient) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)
    seed_product(contracts_client)
    create_contract(contracts_client)

    response = add_contract_item(contracts_client)

    assert response.status_code == 303
    with sqlite3.connect(contracts_client.database_path) as connection:
        item = connection.execute(
            """
            SELECT quantity, unit_price_rmb, amount_rmb, gross_weight, packages, volume
            FROM purchase_contract_items
            WHERE purchase_contract_id = 1
            """
        ).fetchone()
        total = connection.execute(
            "SELECT total_rmb FROM purchase_contracts WHERE id = 1"
        ).fetchone()[0]
    assert item == (3, 12.5, 37.5, 20.0, 2, 0.125)
    assert total == 37.5


def test_contract_can_be_cancelled(contracts_client: TestClient) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)
    create_contract(contracts_client)

    response = contracts_client.post(
        "/contracts/1/cancel",
        data={"confirm_password": "admin-pass"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with sqlite3.connect(contracts_client.database_path) as connection:
        status = connection.execute(
            "SELECT status FROM purchase_contracts WHERE id = 1"
        ).fetchone()[0]
    assert status == "cancelled"


def test_operation_logs_created_for_contract_and_item_actions(
    contracts_client: TestClient,
) -> None:
    bootstrap_admin(contracts_client)
    seed_supplier(contracts_client)
    seed_product(contracts_client)
    create_contract(contracts_client)
    contracts_client.post(
        "/contracts/1/edit",
        data=contract_data(contract_no="PC-UPDATED"),
        follow_redirects=False,
    )
    add_contract_item(contracts_client)

    with sqlite3.connect(contracts_client.database_path) as connection:
        actions = [
            row[0]
            for row in connection.execute(
                "SELECT action_type FROM operation_logs ORDER BY id"
            ).fetchall()
        ]

    assert "purchase_contract_created" in actions
    assert "purchase_contract_updated" in actions
    assert "purchase_contract_item_added" in actions


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


def seed_supplier(client: TestClient) -> None:
    with sqlite3.connect(client.database_path) as connection:
        connection.execute(
            """
            INSERT INTO suppliers (
                id,
                supplier_full_name,
                supplier_short_name,
                supplier_short_name_normalized,
                aliases_text,
                created_by,
                created_at,
                updated_by,
                updated_at
            )
            VALUES (
                1,
                '测试供应商全称',
                '测试供应商',
                '测试供应商',
                '测试供应商',
                'Admin User',
                '2026-05-01T00:00:00+00:00',
                'Admin User',
                '2026-05-01T00:00:00+00:00'
            )
            """
        )
        connection.commit()


def seed_product(client: TestClient) -> None:
    with sqlite3.connect(client.database_path) as connection:
        connection.execute(
            """
            INSERT INTO products (
                id, gts_no, gts_no_normalized, oem, oem_normalized,
                description, chinese_description, hs_code,
                created_by, created_at, updated_by, updated_at
            )
            VALUES (
                1, 'GTSCONTRACT001', 'GTSCONTRACT001', 'OEM-PC-001', 'OEM-PC-001',
                'Shock absorber', '减震器', '870880',
                'Admin User', '2026-05-01T00:00:00+00:00',
                'Admin User', '2026-05-01T00:00:00+00:00'
            )
            """
        )
        connection.commit()


def create_contract(
    client: TestClient,
    *,
    follow_redirects: bool = False,
    **overrides,
):
    return client.post(
        "/contracts/new",
        data=contract_data(**overrides),
        follow_redirects=follow_redirects,
    )


def contract_data(**overrides) -> dict[str, str]:
    data = {
        "contract_no": "PC-001",
        "supplier_id": "1",
        "status": "draft",
        "notes": "测试采购合同",
        "confirm_password": "admin-pass",
    }
    data.update({key: str(value) for key, value in overrides.items()})
    return data


def add_contract_item(client: TestClient, **overrides):
    data = {
        "product_id": "1",
        "quotation_item_id": "",
        "gts_no": "",
        "oem": "",
        "description_cn": "",
        "description_en": "",
        "quantity": "3",
        "unit": "pc",
        "unit_price_rmb": "12.50",
        "gross_weight": "20",
        "packages": "2",
        "volume": "0.125",
        "notes": "测试明细",
        "confirm_password": "admin-pass",
    }
    data.update({key: str(value) for key, value in overrides.items()})
    return client.post("/contracts/1/items/add", data=data, follow_redirects=False)
