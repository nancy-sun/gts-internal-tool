from __future__ import annotations

import json
import re
import sqlite3
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook


ACCESS_CODE = "test-access-code"
REAL_FILE_DIR = Path("local_test_files")
REAL_QUOTATION_FILE = REAL_FILE_DIR / "quotation_upload_real_sample.xlsx"
REAL_REQUEST_FILE = REAL_FILE_DIR / "get_quotation_real_sample.xlsx"


@pytest.fixture()
def real_file_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "real-file-regression.sqlite3"
    upload_path = tmp_path / "uploads"
    upload_path.mkdir()

    monkeypatch.setenv("SHARED_ACCESS_CODE", ACCESS_CODE)
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "55123511")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    from app.config import get_settings
    from app.main import create_app
    from app.routes import generate, hs_codes, upload
    from app.services import backup as backup_service

    get_settings.cache_clear()
    monkeypatch.setattr(upload, "UPLOAD_DIR", upload_path)
    monkeypatch.setattr(generate, "UPLOAD_DIR", upload_path)
    monkeypatch.setattr(hs_codes, "UPLOAD_DIR", upload_path)
    monkeypatch.setattr(backup_service, "AUTO_BACKUP_DIR", upload_path / "auto-backups")

    client = TestClient(create_app())
    client.database_path = database_path
    client.upload_path = upload_path
    login_response = client.post(
        "/setup-admin",
        data={
            "username": "admin",
            "display_name": "Nancy",
            "password": "55123511",
            "confirm_password": "55123511",
        },
    )
    assert login_response.status_code == 200
    return client


def test_real_quotation_upload_file_imports_and_generates_quote(
    real_file_client: TestClient,
) -> None:
    require_real_file(REAL_QUOTATION_FILE)
    require_real_file(REAL_REQUEST_FILE)

    upload_token = upload_real_quotation_file(real_file_client, REAL_QUOTATION_FILE)
    payload = preview_payload(real_file_client, upload_token)
    assert len(payload["rows"]) >= 10
    first_row = next(row for row in payload["rows"] if row["values"]["gts_no"] == "GTSTEST001")
    assert first_row["values"]["item_per_package"] == 2
    assert first_row["values"]["packages"] == 10
    assert first_row["values"]["weight_per_package"] == 9
    assert first_row["values"]["gross_weight"] == 90

    resolve_all_unmatched_suppliers(real_file_client, upload_token)
    confirm_response = real_file_client.post(
        "/upload/confirm",
        data={"token": upload_token, "confirm_password": "55123511"},
    )
    assert confirm_response.status_code == 200

    with sqlite3.connect(real_file_client.database_path) as connection:
        connection.row_factory = sqlite3.Row
        item = connection.execute(
            """
            SELECT item_per_package, packages, weight_per_package, gross_weight
            FROM quotation_items
            WHERE gts_no_normalized = 'GTSTEST001'
            """
        ).fetchone()
    assert item["item_per_package"] == 2
    assert item["packages"] == 10
    assert item["weight_per_package"] == 9
    assert item["gross_weight"] == 90

    generate_response = real_file_client.post(
        "/generate/preview",
        data={"operator_name": "Nancy"},
        files={
            "request_file": (
                REAL_REQUEST_FILE.name,
                REAL_REQUEST_FILE.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert generate_response.status_code == 200
    assert "GTSTEST001" in generate_response.text
    assert "GTSTEST002" in generate_response.text

    generate_token = extract_token(generate_response.text)
    download_response = real_file_client.post(
        "/generate/download",
        data=download_form_for_all_preview_rows(real_file_client, generate_token),
    )
    assert download_response.status_code == 200
    workbook = load_workbook(BytesIO(download_response.content))
    worksheet = workbook.active
    assert worksheet["B3"].value == "GTSTEST001"
    assert worksheet["I3"].value == "pc"
    assert worksheet["J3"].value == 9
    assert worksheet["L3"].value == 2
    assert worksheet["M3"].value == 10
    assert worksheet["N3"].value == 9
    assert worksheet["O3"].value == 90


def require_real_file(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Optional real-file fixture is missing: {path}")


def upload_real_quotation_file(client: TestClient, path: Path) -> str:
    upload_response = client.post(
        "/upload/preview",
        data={"operator_name": "Nancy"},
        files={
            "excel_file": (
                path.name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_response.status_code == 200
    token = extract_token(upload_response.text)
    stream_response = client.get(f"/upload/preview/stream/{token}")
    assert stream_response.status_code == 200
    assert '"has_errors": false' in stream_response.text
    return token


def preview_payload(client: TestClient, token: str) -> dict:
    return json.loads((client.upload_path / f"preview_{token}.json").read_text())


def generate_preview_payload(client: TestClient, token: str) -> dict:
    return json.loads((client.upload_path / f"generate_preview_{token}.json").read_text())


def resolve_all_unmatched_suppliers(client: TestClient, token: str) -> None:
    payload = preview_payload(client, token)
    data = {"token": token, "operator_name": payload["operator_name"]}
    for match in payload.get("supplier_matches") or []:
        if match["status"] not in {"pending_unmatched", "blank_pending", "ambiguous_pending"}:
            continue
        factory = match.get("factory") or f"Blank Supplier {match['key']}"
        data[f"action__{match['key']}"] = "create"
        data[f"supplier_short_name__{match['key']}"] = factory
    if len(data) == 2:
        return
    response = client.post(
        "/upload/preview/supplier/batch",
        data=data,
        follow_redirects=False,
    )
    assert response.status_code == 303


def download_form_for_all_preview_rows(client: TestClient, token: str) -> dict:
    payload = generate_preview_payload(client, token)
    form_data = {"token": token}
    for row in payload["rows"]:
        row_number = row["row_number"]
        form_data[f"include__{row_number}"] = "1"
        if row["status"] == "missing_identifier":
            form_data[f"candidate__{row_number}"] = "-1"
        elif row.get("candidates"):
            form_data[f"candidate__{row_number}"] = str(row["candidates"][0]["id"])
    return form_data


def extract_token(html: str) -> str:
    match = re.search(r'name="token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)
