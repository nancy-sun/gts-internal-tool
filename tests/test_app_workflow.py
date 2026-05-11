from __future__ import annotations

import re
import sqlite3
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook


ACCESS_CODE = "test-access-code"


@pytest.fixture()
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "gts-test.sqlite3"
    upload_path = tmp_path / "uploads"
    upload_path.mkdir()

    monkeypatch.setenv("SHARED_ACCESS_CODE", ACCESS_CODE)
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    from app.config import get_settings
    from app.main import create_app
    from app.routes import generate, hs_codes, upload

    get_settings.cache_clear()
    monkeypatch.setattr(upload, "UPLOAD_DIR", upload_path)
    monkeypatch.setattr(generate, "UPLOAD_DIR", upload_path)
    monkeypatch.setattr(hs_codes, "UPLOAD_DIR", upload_path)

    client = TestClient(create_app())
    client.upload_path = upload_path
    login_response = client.post("/login", data={"access_code": ACCESS_CODE})
    assert login_response.status_code == 200
    return client


def test_office_workflow_upload_search_generate_download_and_log(
    app_client: TestClient,
    tmp_path: Path,
) -> None:
    upload_response = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "quotation.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "no": 1,
                            "gts_no": "GTS-TEST-001",
                            "description": "Mirror request source",
                            "oem": "5010 225 393",
                            "factory": "欧达",
                            "chinese_description": "后视镜",
                            "quantity": 2,
                            "unit": "pc",
                            "unit_price": 99,
                            "total_price": 198,
                            "expected_delivery": "25days",
                            "comment": "first upload",
                        }
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert upload_response.status_code == 200
    upload_token = extract_token(upload_response.text)
    stream_response = app_client.get(f"/upload/preview/stream/{upload_token}")
    assert stream_response.status_code == 200
    assert 'event: complete' in stream_response.text
    assert '"has_errors": false' in stream_response.text

    confirm_response = app_client.post("/upload/confirm", data={"token": upload_token})
    assert confirm_response.status_code == 200
    assert "新增产品" in confirm_response.text
    assert not (app_client.upload_path / f"preview_{upload_token}.json").exists()

    search_response = app_client.get("/search", params={"field": "gts_no", "q": "test001"})
    assert search_response.status_code == 200
    assert "GTS-TEST-001" in search_response.text
    assert "¥99.00" in search_response.text
    assert 'href="/products/1/edit"' in search_response.text
    assert "编辑" in search_response.text

    generate_response = app_client.post(
        "/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "request_file": (
                "request.xlsx",
                build_request_workbook(
                    [
                        {
                            "gts_no": "GTSTEST001",
                            "description": "Uploaded request description",
                            "oem": "",
                            "quantity": 3,
                            "unit": "",
                            "comment": "need quote",
                        }
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert generate_response.status_code == 200
    assert_breadcrumb(
        generate_response.text,
        ["首页", "生成报价单", "生成预览"],
    )
    assert "后视镜" in generate_response.text
    assert "pc" in generate_response.text
    assert "欧达" in generate_response.text
    assert "¥99.00" in generate_response.text
    assert "Nancy" in generate_response.text
    assert ">3<" in generate_response.text
    assert "3.0" not in generate_response.text

    generate_token = extract_token(generate_response.text)
    candidate_id = fetch_single_candidate_id(tmp_path / "gts-test.sqlite3")
    download_response = app_client.post(
        "/generate/download",
        data={
            "token": generate_token,
            "include__2": "1",
            "candidate__2": str(candidate_id),
        },
    )

    assert download_response.status_code == 200
    assert not (app_client.upload_path / f"generate_preview_{generate_token}.json").exists()
    workbook = load_workbook(BytesIO(download_response.content))
    worksheet = workbook.active
    assert [worksheet.cell(row=2, column=index).value for index in range(1, 6)] == [
        "No.",
        "GTS No.",
        "Description",
        "OEM",
        "Photo",
    ]
    assert worksheet["B3"].value == "GTS-TEST-001"
    assert worksheet["C3"].value == "Mirror request source"
    assert worksheet["D3"].value == "5010 225 393"
    assert worksheet["G3"].value == "后视镜"
    assert worksheet["H3"].value == 3
    assert worksheet["I3"].value == "pc"
    assert worksheet["J3"].value == 99
    assert worksheet["K3"].value == 297

    logs_response = app_client.get("/logs")
    assert logs_response.status_code == 200
    assert_breadcrumb(logs_response.text, ["首页", "操作记录"])
    assert "上传完整报价单" in logs_response.text
    assert "生成报价单" in logs_response.text


def test_page_breadcrumbs_include_parent_pages(app_client: TestClient) -> None:
    upload_page = app_client.get("/upload")
    assert upload_page.status_code == 200
    assert_breadcrumb(upload_page.text, ["首页", "上传完整报价单"])

    upload_preview = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "breadcrumb-upload.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "gts_no": "GTS-BREAD-001",
                            "oem": "OEM-BREAD",
                            "factory": "Factory A",
                            "unit": "pc",
                            "unit_price": 10,
                        }
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_preview.status_code == 200
    assert_breadcrumb(upload_preview.text, ["首页", "上传完整报价单", "导入预览"])

    upload_token = extract_token(upload_preview.text)
    stream_response = app_client.get(f"/upload/preview/stream/{upload_token}")
    assert stream_response.status_code == 200
    upload_result = app_client.post("/upload/confirm", data={"token": upload_token})
    assert upload_result.status_code == 200
    assert_breadcrumb(upload_result.text, ["首页", "上传完整报价单", "导入结果"])

    generate_page = app_client.get("/generate")
    assert generate_page.status_code == 200
    assert_breadcrumb(generate_page.text, ["首页", "生成报价单"])

    generate_preview = app_client.post(
        "/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "request_file": (
                "breadcrumb-request.xlsx",
                build_request_workbook([{"gts_no": "GTS-BREAD-001", "quantity": 1}]),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert generate_preview.status_code == 200
    assert_breadcrumb(generate_preview.text, ["首页", "生成报价单", "生成预览"])

    search_page = app_client.get("/search")
    assert search_page.status_code == 200
    assert_breadcrumb(search_page.text, ["首页", "查询数据库"])

    logs_page = app_client.get("/logs")
    assert logs_page.status_code == 200
    assert_breadcrumb(logs_page.text, ["首页", "操作记录"])


def test_upload_preview_stream_replaces_loading_rows_one_by_one(app_client: TestClient) -> None:
    upload_response = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "stream-order.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "gts_no": "GTS-STREAM-001",
                            "oem": "OEM-STREAM-001",
                            "factory": "Factory A",
                            "unit": "pc",
                            "unit_price": 10,
                        },
                        {
                            "gts_no": "GTS-STREAM-002",
                            "oem": "OEM-STREAM-002",
                            "factory": "Factory B",
                            "unit": "pc",
                            "unit_price": 20,
                        },
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_response.status_code == 200

    token = extract_token(upload_response.text)
    stream_response = app_client.get(f"/upload/preview/stream/{token}")

    assert stream_response.status_code == 200
    first_loading_index = stream_response.text.index(
        'event: loading\ndata: {"row_number": 4}'
    )
    first_row_index = stream_response.text.index(
        'event: row\ndata: {"row_number": 4'
    )
    second_loading_index = stream_response.text.index(
        'event: loading\ndata: {"row_number": 5}'
    )
    assert first_loading_index < first_row_index < second_loading_index


def test_upload_preview_reports_missing_required_fields(app_client: TestClient) -> None:
    upload_response = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "missing-required.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "no": 1,
                            "gts_no": "GTS-ERR-001",
                            "oem": "OEM-ERR",
                            "factory": "",
                            "unit": "",
                            "unit_price": "",
                        }
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    token = extract_token(upload_response.text)
    stream_response = app_client.get(f"/upload/preview/stream/{token}")
    assert stream_response.status_code == 200
    assert '"has_errors": true' in stream_response.text
    assert "工厂不能为空" in stream_response.text
    assert "单位不能为空" in stream_response.text
    assert "单价不能为空" in stream_response.text

    confirm_response = app_client.post("/upload/confirm", data={"token": token})
    assert confirm_response.status_code == 400
    assert "预览有错误，请修改 Excel 后再导入。" in confirm_response.text


def test_generate_preview_highlights_multiple_candidates_and_shows_comments(
    app_client: TestClient,
) -> None:
    upload_response = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "multiple-candidates.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "no": 1,
                            "gts_no": "GTS-MULTI-001",
                            "oem": "OEM-MULTI",
                            "factory": "Factory A",
                            "quantity": 1,
                            "unit": "pc",
                            "unit_price": 100,
                            "comment": "old stock",
                        },
                        {
                            "no": 2,
                            "gts_no": "GTS-MULTI-001",
                            "oem": "OEM-MULTI",
                            "factory": "Factory B",
                            "quantity": 1,
                            "unit": "pc",
                            "unit_price": 120,
                            "comment": "new stock",
                        },
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    upload_token = extract_token(upload_response.text)
    stream_response = app_client.get(f"/upload/preview/stream/{upload_token}")
    assert '"has_errors": false' in stream_response.text
    confirm_response = app_client.post(
        "/upload/confirm",
        data={"token": upload_token},
    )
    assert confirm_response.status_code == 200

    generate_response = app_client.post(
        "/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "request_file": (
                "request.xlsx",
                build_request_workbook([{"gts_no": "GTSMULTI001"}]),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert generate_response.status_code == 200
    assert 'class="multiple-candidates-row"' in generate_response.text
    assert "candidate-line-review" in generate_response.text
    assert "Factory A" in generate_response.text
    assert "Factory B" in generate_response.text
    assert "old stock" in generate_response.text
    assert "new stock" in generate_response.text


def test_generate_download_allows_missing_quantity_and_leaves_total_blank(
    app_client: TestClient,
    tmp_path: Path,
) -> None:
    upload_response = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "quotation-no-quantity-request.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "no": 1,
                            "gts_no": "GTS-NO-QTY-001",
                            "oem": "OEM-NO-QTY",
                            "factory": "Factory A",
                            "quantity": 1,
                            "unit": "pc",
                            "unit_price": 88,
                            "total_price": 88,
                        }
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    upload_token = extract_token(upload_response.text)
    stream_response = app_client.get(f"/upload/preview/stream/{upload_token}")
    assert '"has_errors": false' in stream_response.text
    confirm_response = app_client.post("/upload/confirm", data={"token": upload_token})
    assert confirm_response.status_code == 200

    generate_response = app_client.post(
        "/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "request_file": (
                "request-no-quantity.xlsx",
                build_request_workbook([{"gts_no": "GTSNOQTY001"}]),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert generate_response.status_code == 200
    assert "未填写数量" in generate_response.text

    generate_token = extract_token(generate_response.text)
    candidate_id = fetch_single_candidate_id(tmp_path / "gts-test.sqlite3")
    download_response = app_client.post(
        "/generate/download",
        data={
            "token": generate_token,
            "include__2": "1",
            "candidate__2": str(candidate_id),
        },
    )

    assert download_response.status_code == 200
    workbook = load_workbook(BytesIO(download_response.content))
    worksheet = workbook.active
    assert worksheet["B3"].value == "GTS-NO-QTY-001"
    assert worksheet["H3"].value is None
    assert worksheet["K3"].value is None


def test_generate_preview_and_download_allow_rows_without_gts_or_oem(
    app_client: TestClient,
) -> None:
    generate_response = app_client.post(
        "/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "request_file": (
                "request-no-identifiers.xlsx",
                build_request_workbook(
                    [
                        {"description": "Only description"},
                        {"quantity": 5, "comment": "No GTS or OEM"},
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert generate_response.status_code == 200
    assert "GTS 和 OEM 都缺失" in generate_response.text
    assert 'class="missing-identifier-row"' in generate_response.text

    generate_token = extract_token(generate_response.text)
    download_response = app_client.post(
        "/generate/download",
        data={
            "token": generate_token,
            "include__2": "1",
            "candidate__2": "-1",
            "include__3": "1",
            "candidate__3": "-1",
        },
    )

    assert download_response.status_code == 200
    workbook = load_workbook(BytesIO(download_response.content))
    worksheet = workbook.active
    assert worksheet["C3"].value == "Only description"
    assert worksheet["H3"].value is None
    assert worksheet["H4"].value == 5
    assert worksheet["V4"].value == "No GTS or OEM"


def test_generate_preview_allows_mixed_valid_and_invalid_request_rows(
    app_client: TestClient,
    tmp_path: Path,
) -> None:
    upload_response = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "quotation-mixed-request.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "no": 1,
                            "gts_no": "GTS-MIXED-001",
                            "oem": "OEM-MIXED",
                            "factory": "Factory A",
                            "quantity": 1,
                            "unit": "pc",
                            "unit_price": 66,
                        }
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    upload_token = extract_token(upload_response.text)
    stream_response = app_client.get(f"/upload/preview/stream/{upload_token}")
    assert '"has_errors": false' in stream_response.text
    confirm_response = app_client.post("/upload/confirm", data={"token": upload_token})
    assert confirm_response.status_code == 200

    generate_response = app_client.post(
        "/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "request_file": (
                "request-mixed.xlsx",
                build_request_workbook(
                    [
                        {"description": "Invalid request row", "quantity": 2},
                        {"gts_no": "GTSMIXED001", "quantity": 4},
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert generate_response.status_code == 200
    assert "GTS 和 OEM 都缺失" in generate_response.text
    assert 'class="missing-identifier-row"' in generate_response.text
    assert "GTS-MIXED-001" in generate_response.text

    generate_token = extract_token(generate_response.text)
    candidate_id = fetch_single_candidate_id(tmp_path / "gts-test.sqlite3")
    download_response = app_client.post(
        "/generate/download",
        data={
            "token": generate_token,
            "include__2": "1",
            "candidate__2": "-1",
            "include__3": "1",
            "candidate__3": str(candidate_id),
        },
    )

    assert download_response.status_code == 200
    workbook = load_workbook(BytesIO(download_response.content))
    worksheet = workbook.active
    assert worksheet["C3"].value == "Invalid request row"
    assert worksheet["H3"].value == 2
    assert worksheet["B4"].value == "GTS-MIXED-001"
    assert worksheet["H4"].value == 4
    assert worksheet.max_row == 4


def test_hs_code_upload_overwrites_search_displays_and_export_keeps_order(
    app_client: TestClient,
) -> None:
    upload_response = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "hs-products.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "gts_no": "GTS-HS-001",
                            "oem": "OEM-HS-001",
                            "factory": "Factory A",
                            "unit": "pc",
                            "unit_price": 10,
                        },
                        {
                            "gts_no": "GTS-HS-002",
                            "oem": "OEM-HS-002",
                            "factory": "Factory B",
                            "unit": "pc",
                            "unit_price": 20,
                        },
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    upload_token = extract_token(upload_response.text)
    app_client.get(f"/upload/preview/stream/{upload_token}")
    confirm_response = app_client.post("/upload/confirm", data={"token": upload_token})
    assert confirm_response.status_code == 200

    hs_upload_response = app_client.post(
        "/hs-codes/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "hs-upload.xlsx",
                build_hs_code_workbook(
                    [
                        {"gts_no": "GTS-HS-001", "hs_code": "87089910"},
                        {"gts_no": "GTS-HS-002", "hs_code": "87089920"},
                    ],
                    hs_header="海关编码",
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert hs_upload_response.status_code == 200
    assert "87089910" in hs_upload_response.text
    hs_token = extract_token(hs_upload_response.text)
    hs_confirm_response = app_client.post("/hs-codes/upload/confirm", data={"token": hs_token})
    assert hs_confirm_response.status_code == 200
    assert "已更新" in hs_confirm_response.text
    assert not (app_client.upload_path / f"hs_upload_preview_{hs_token}.json").exists()

    overwrite_response = app_client.post(
        "/hs-codes/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "hs-overwrite.xlsx",
                build_hs_code_workbook(
                    [{"gts_no": "GTS-HS-001", "hs_code": "87089999"}],
                    hs_header="HS",
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    overwrite_token = extract_token(overwrite_response.text)
    overwrite_confirm = app_client.post(
        "/hs-codes/upload/confirm",
        data={"token": overwrite_token},
    )
    assert overwrite_confirm.status_code == 200

    search_response = app_client.get("/search", params={"field": "gts_no", "q": "GTSHS001"})
    assert search_response.status_code == 200
    assert "87089999" in search_response.text
    assert "87089910" not in search_response.text

    generate_response = app_client.post(
        "/hs-codes/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "hs-request.xlsx",
                build_hs_request_workbook(
                    [
                        {"gts_no": "GTS-HS-002"},
                        {"gts_no": "GTS-HS-001"},
                        {"gts_no": "GTS-HS-MISSING"},
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert generate_response.status_code == 200
    generate_token = extract_token(generate_response.text)
    download_response = app_client.post(
        "/hs-codes/generate/download",
        data={"token": generate_token},
    )
    assert download_response.status_code == 200
    assert not (
        app_client.upload_path / f"hs_generate_preview_{generate_token}.json"
    ).exists()

    workbook = load_workbook(BytesIO(download_response.content))
    worksheet = workbook.active
    assert [worksheet.cell(row=1, column=index).value for index in range(1, 4)] == [
        "GTS",
        "OEM",
        "HS Code",
    ]
    assert [worksheet.cell(row=row, column=1).value for row in range(2, 5)] == [
        "GTS-HS-002",
        "GTS-HS-001",
        "GTS-HS-MISSING",
    ]
    assert worksheet["B2"].value == "OEM-HS-002"
    assert worksheet["C2"].value == "87089920"
    assert worksheet["B3"].value == "OEM-HS-001"
    assert worksheet["C3"].value == "87089999"
    assert worksheet["B4"].value is None
    assert worksheet["C4"].value is None

    logs_response = app_client.get("/logs")
    assert logs_response.status_code == 200
    assert "update_hs_code" in logs_response.text
    assert "generate_hs_code" in logs_response.text


def test_product_edit_updates_current_fields_used_by_quotation_and_hs_exports(
    app_client: TestClient,
    tmp_path: Path,
) -> None:
    upload_response = app_client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "product-edit-source.xlsx",
                build_quotation_workbook(
                    [
                        {
                            "gts_no": "GTS-OLD-001",
                            "description": "Old product description",
                            "oem": "OEM-OLD-001",
                            "factory": "Factory A",
                            "unit": "pc",
                            "unit_price": 99,
                        }
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    upload_token = extract_token(upload_response.text)
    app_client.get(f"/upload/preview/stream/{upload_token}")
    confirm_response = app_client.post("/upload/confirm", data={"token": upload_token})
    assert confirm_response.status_code == 200

    edit_page = app_client.get("/products/1/edit")
    assert edit_page.status_code == 200
    assert "data-product-edit-form" in edit_page.text
    assert 'value="GTS-OLD-001"' in edit_page.text
    assert 'data-original-value="GTS-OLD-001"' in edit_page.text
    assert 'value="OEM-OLD-001"' in edit_page.text
    assert 'value="Old product description"' in edit_page.text
    assert "data-product-edit-submit disabled" in edit_page.text

    bad_password_response = app_client.post(
        "/products/1/edit",
        data={
            "operator_name": "Nancy",
            "gts_no": "GTS-NEW-001",
            "oem": "OEM-NEW-001",
            "description": "New product description",
            "hs_code": "87089999",
            "edit_password": "wrong",
        },
    )
    assert bad_password_response.status_code == 400
    assert "确认密码不正确" in bad_password_response.text
    assert 'value="GTS-NEW-001"' in bad_password_response.text
    assert 'data-original-value="GTS-OLD-001"' in bad_password_response.text

    edit_response = app_client.post(
        "/products/1/edit",
        data={
            "operator_name": "Nancy",
            "gts_no": "GTS-NEW-001",
            "oem": "OEM-NEW-001",
            "description": "New product description",
            "hs_code": "87089999",
            "edit_password": "55123511",
        },
    )
    assert edit_response.status_code == 200
    assert "产品资料已更新" in edit_response.text

    generate_response = app_client.post(
        "/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "request_file": (
                "old-request.xlsx",
                build_request_workbook(
                    [
                        {
                            "gts_no": "GTS-OLD-001",
                            "description": "Request description should not override product",
                            "oem": "OEM-OLD-001",
                            "quantity": 2,
                        }
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert generate_response.status_code == 200
    assert "GTS 已从 GTS-OLD-001 改为 GTS-NEW-001" in generate_response.text
    assert "OEM 已从 OEM-OLD-001 改为 OEM-NEW-001" in generate_response.text

    generate_token = extract_token(generate_response.text)
    candidate_id = fetch_single_candidate_id(tmp_path / "gts-test.sqlite3")
    download_response = app_client.post(
        "/generate/download",
        data={
            "token": generate_token,
            "include__2": "1",
            "candidate__2": str(candidate_id),
        },
    )
    assert download_response.status_code == 200
    workbook = load_workbook(BytesIO(download_response.content))
    worksheet = workbook.active
    assert worksheet["B3"].value == "GTS-NEW-001"
    assert worksheet["C3"].value == "New product description"
    assert worksheet["D3"].value == "OEM-NEW-001"

    hs_generate_response = app_client.post(
        "/hs-codes/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                "old-hs-request.xlsx",
                build_hs_request_workbook([{"gts_no": "GTS-OLD-001"}]),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert hs_generate_response.status_code == 200
    assert "GTS 已从 GTS-OLD-001 改为 GTS-NEW-001" in hs_generate_response.text

    hs_token = extract_token(hs_generate_response.text)
    hs_download_response = app_client.post(
        "/hs-codes/generate/download",
        data={"token": hs_token},
    )
    assert hs_download_response.status_code == 200
    hs_workbook = load_workbook(BytesIO(hs_download_response.content))
    hs_worksheet = hs_workbook.active
    assert hs_worksheet["A2"].value == "GTS-NEW-001"
    assert hs_worksheet["B2"].value == "OEM-NEW-001"
    assert hs_worksheet["C2"].value == "87089999"

    logs_response = app_client.get("/logs")
    assert logs_response.status_code == 200
    assert "编辑产品" in logs_response.text


def test_login_rejects_wrong_shared_access_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHARED_ACCESS_CODE", ACCESS_CODE)
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "auth-test.sqlite3"))

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    client = TestClient(create_app())

    protected_response = client.get("/upload", follow_redirects=False)
    assert protected_response.status_code == 303
    assert protected_response.headers["location"] == "/login"

    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert "操作人" in login_page.text
    assert 'name="operator_name"' in login_page.text

    bad_login_response = client.post("/login", data={"access_code": "wrong-code"})
    assert bad_login_response.status_code == 401
    assert "访问码不正确" in bad_login_response.text


def build_quotation_workbook(rows: list[dict]) -> BytesIO:
    headers = [
        "No.",
        "GTS No.",
        "Description",
        "OEM",
        "Photo",
        "Factory",
        "Chinese Description",
        "Quantity",
        "Unit",
        "Unit Price",
        "Total Price",
        "Item/Package",
        "Packages",
        "Weight / Package",
        "G.W.",
        "Length",
        "Width",
        "Height",
        "Measurements / Volume",
        "Packaging",
        "Expected Delivery",
        "Comment",
    ]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Quotation"
    worksheet["A1"] = "GTS Internal Tool Upload Template"
    for column_index, header in enumerate(headers, start=1):
        worksheet.cell(row=3, column=column_index, value=header)

    field_order = [
        "no",
        "gts_no",
        "description",
        "oem",
        "photo",
        "factory",
        "chinese_description",
        "quantity",
        "unit",
        "unit_price",
        "total_price",
        "item_per_package",
        "packages",
        "weight_per_package",
        "gross_weight",
        "length",
        "width",
        "height",
        "measurements_volume",
        "packaging",
        "expected_delivery",
        "comment",
    ]
    for row_index, row in enumerate(rows, start=4):
        for column_index, field in enumerate(field_order, start=1):
            worksheet.cell(row=row_index, column=column_index, value=row.get(field, ""))
    return workbook_bytes(workbook)


def build_request_workbook(rows: list[dict]) -> BytesIO:
    headers = ["GTS No.", "Description", "OEM", "Quantity", "Unit", "Comment"]
    field_order = ["gts_no", "description", "oem", "quantity", "unit", "comment"]
    workbook = Workbook()
    worksheet = workbook.active
    for column_index, header in enumerate(headers, start=1):
        worksheet.cell(row=1, column=column_index, value=header)
    for row_index, row in enumerate(rows, start=2):
        for column_index, field in enumerate(field_order, start=1):
            worksheet.cell(row=row_index, column=column_index, value=row.get(field, ""))
    return workbook_bytes(workbook)


def build_hs_code_workbook(rows: list[dict], hs_header: str = "HS Code") -> BytesIO:
    workbook = Workbook()
    worksheet = workbook.active
    headers = ["GTS No.", "Description", hs_header, "Comment"]
    for column_index, header in enumerate(headers, start=1):
        worksheet.cell(row=1, column=column_index, value=header)
    for row_index, row in enumerate(rows, start=2):
        worksheet.cell(row=row_index, column=1, value=row.get("gts_no", ""))
        worksheet.cell(row=row_index, column=2, value=row.get("description", ""))
        worksheet.cell(row=row_index, column=3, value=row.get("hs_code", ""))
        worksheet.cell(row=row_index, column=4, value=row.get("comment", ""))
    return workbook_bytes(workbook)


def build_hs_request_workbook(rows: list[dict]) -> BytesIO:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.cell(row=1, column=1, value="GTS")
    for row_index, row in enumerate(rows, start=2):
        worksheet.cell(row=row_index, column=1, value=row.get("gts_no", ""))
    return workbook_bytes(workbook)


def workbook_bytes(workbook: Workbook) -> BytesIO:
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream


def extract_token(html: str) -> str:
    match = re.search(r'name="token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def fetch_single_candidate_id(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT id FROM quotation_items").fetchone()
        assert row is not None
        return int(row[0])


def assert_breadcrumb(html: str, labels: list[str]) -> None:
    match = re.search(
        r'<ol class="breadcrumb-list">(.*?)</ol>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    breadcrumb_text = re.sub(r"<[^>]+>", " ", match.group(1))
    breadcrumb_text = re.sub(r"\s+", " ", breadcrumb_text).strip()
    assert " ".join(labels) == breadcrumb_text
