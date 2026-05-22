from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def mapping_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "product-customs.sqlite3"
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


def test_product_customs_mappings_table_initializes(mapping_client: TestClient) -> None:
    with sqlite3.connect(mapping_client.database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(product_customs_mappings)").fetchall()
        }

    assert "product_id" in columns
    assert "customs_item_id" in columns
    assert "part_no_for_declaration" in columns


def test_admin_can_create_product_customs_mapping(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client)

    response = create_mapping(mapping_client)

    assert response.status_code == 303
    page = mapping_client.get("/customs/mappings")
    assert "GTSCUSTOMS001" in page.text
    assert "减震器" in page.text
    assert "870880" in page.text


def test_merchandiser_can_create_mapping(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client)
    create_user(mapping_client, role="merchandiser", username="merch", password="merch-pass")
    mapping_client.post("/logout")
    mapping_client.post("/login", data={"username": "merch", "password": "merch-pass"})

    response = create_mapping(mapping_client, confirm_password="merch-pass")

    assert response.status_code == 303


def test_sales_can_view_but_cannot_create_mapping(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client)
    create_mapping(mapping_client)
    create_user(mapping_client, role="sales", username="sales", password="sales-pass")
    mapping_client.post("/logout")
    mapping_client.post("/login", data={"username": "sales", "password": "sales-pass"})

    list_page = mapping_client.get("/customs/mappings")
    new_page = mapping_client.get("/customs/mappings/new", follow_redirects=False)
    create_response = create_mapping(mapping_client, confirm_password="sales-pass", follow_redirects=False)

    assert list_page.status_code == 200
    assert "GTSCUSTOMS001" in list_page.text
    assert "新增映射" not in list_page.text
    assert new_page.status_code == 303
    assert new_page.headers["location"] == "/forbidden"
    assert create_response.status_code == 303
    assert create_response.headers["location"] == "/forbidden"


def test_mapping_create_requires_password_confirmation(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client)

    response = create_mapping(mapping_client, confirm_password="wrong")

    assert response.status_code == 400
    assert "密码确认失败，操作已取消。" in response.text


def test_remapping_same_product_updates_existing_mapping(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, customs_name_cn="减震器", hs_code="870880")
    create_customs_item(mapping_client, customs_name_cn="水泵", hs_code="8413")
    create_mapping(mapping_client, customs_item_id="1")

    response = create_mapping(mapping_client, customs_item_id="2")

    assert response.status_code == 303
    with sqlite3.connect(mapping_client.database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM product_customs_mappings").fetchone()[0]
        customs_item_id = connection.execute(
            "SELECT customs_item_id FROM product_customs_mappings WHERE product_id = 1"
        ).fetchone()[0]
    assert count == 1
    assert customs_item_id == 2


def test_missing_page_shows_products_without_mapping(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)

    response = mapping_client.get("/customs/missing")

    assert response.status_code == 200
    assert "未建立报关映射的产品" in response.text
    assert "GTSCUSTOMS001" in response.text


def test_missing_page_shows_gross_weight_issue(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, unit_1_source="gross_weight")
    create_mapping(mapping_client)

    response = mapping_client.get("/customs/missing")

    assert "缺少毛重" in response.text


def test_missing_page_shows_package_count_issue(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, unit_1="件", unit_1_source="package_count")
    create_mapping(mapping_client)

    response = mapping_client.get("/customs/missing")

    assert "缺少件数" in response.text


def test_missing_page_shows_net_weight_missing_gross_weight(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, unit_1="千克", unit_1_source="net_weight")
    create_mapping(mapping_client)
    seed_quotation(mapping_client, packages=2, gross_weight=None)

    response = mapping_client.get("/customs/missing")

    assert "净重缺少毛重" in response.text


def test_missing_page_shows_net_weight_missing_packages(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, unit_1="千克", unit_1_source="net_weight")
    create_mapping(mapping_client)
    seed_quotation(mapping_client, packages=None, gross_weight=10)

    response = mapping_client.get("/customs/missing")

    assert "净重缺少件数" in response.text


def test_missing_page_shows_net_weight_invalid_result(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, unit_1="千克", unit_1_source="net_weight")
    create_mapping(mapping_client)
    seed_quotation(mapping_client, packages=3, gross_weight=2)

    response = mapping_client.get("/customs/missing")

    assert "净重计算错误：毛重 - 件数 必须大于 0。" in response.text


def test_missing_page_shows_missing_declaration_template(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, declaration_element_template="")
    create_mapping(mapping_client)

    response = mapping_client.get("/customs/missing")

    assert "缺少申报要素模板" in response.text


def test_mapping_create_and_update_write_operation_logs(mapping_client: TestClient) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, customs_name_cn="减震器", hs_code="870880")
    create_customs_item(mapping_client, customs_name_cn="水泵", hs_code="8413")

    create_mapping(mapping_client, customs_item_id="1")
    create_mapping(mapping_client, customs_item_id="2")

    with sqlite3.connect(mapping_client.database_path) as connection:
        actions = [
            row[0]
            for row in connection.execute(
                "SELECT action_type FROM operation_logs ORDER BY id"
            ).fetchall()
        ]
    assert "product_customs_mapping_created" in actions
    assert "product_customs_mapping_updated" in actions


def test_search_displays_mapping_hs_code_before_legacy_product_hs_code(
    mapping_client: TestClient,
) -> None:
    bootstrap_admin(mapping_client)
    seed_product(mapping_client)
    create_customs_item(mapping_client, hs_code="CUSTOMS-HS")
    create_mapping(mapping_client)

    response = mapping_client.get("/search", params={"field": "gts_no", "q": "GTSCUSTOMS001"})

    assert response.status_code == 200
    assert "CUSTOMS-HS" in response.text
    assert "LEGACY-HS" not in response.text


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
                1, 'GTSCUSTOMS001', 'GTSCUSTOMS001', 'OEM001', 'OEM001',
                'Shock absorber', '减震器', 'LEGACY-HS',
                'Admin User', '2026-05-01T00:00:00+00:00',
                'Admin User', '2026-05-01T00:00:00+00:00'
            )
            """
        )
        connection.commit()


def seed_quotation(
    client: TestClient,
    *,
    packages,
    gross_weight,
) -> None:
    with sqlite3.connect(client.database_path) as connection:
        connection.execute(
            """
            INSERT INTO quotation_items (
                id, product_id, gts_no, gts_no_normalized, factory,
                packages, gross_weight,
                created_by, created_at, updated_by, updated_at
            )
            VALUES (
                1, 1, 'GTSCUSTOMS001', 'GTSCUSTOMS001', 'Test Factory',
                ?, ?,
                'Admin User', '2026-05-01T00:00:00+00:00',
                'Admin User', '2026-05-01T00:00:00+00:00'
            )
            """,
            (packages, gross_weight),
        )
        connection.commit()


def create_customs_item(client: TestClient, **overrides):
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
        "declaration_element_template": "品名：{customs_name_cn}",
        "notes": "",
        "confirm_password": "admin-pass",
    }
    data.update({key: "" if value is None else str(value) for key, value in overrides.items()})
    return client.post("/customs/items/new", data=data, follow_redirects=False)


def create_mapping(
    client: TestClient,
    *,
    product_id: str = "1",
    customs_item_id: str = "1",
    confirm_password: str = "admin-pass",
    follow_redirects: bool = False,
):
    return client.post(
        "/customs/mappings/new",
        data={
            "product_id": product_id,
            "customs_item_id": customs_item_id,
            "part_no_for_declaration": "PN-001",
            "model_for_declaration": "Truck",
            "material": "Steel",
            "brand": "No brand",
            "declaration_notes": "测试映射",
            "confirm_password": confirm_password,
        },
        follow_redirects=follow_redirects,
    )
