from __future__ import annotations

from pathlib import Path

import pytest

from app.services.suppliers import create_supplier, get_supplier
from app.services.upload_preview_state import validate_all_suppliers_resolved
from app.services.upload_supplier_matching import build_supplier_matches
from app.services.upload_supplier_resolution import (
    apply_supplier_resolution_to_rows,
    create_preview_supplier,
    link_preview_supplier,
)


@pytest.fixture()
def upload_supplier_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database_path = tmp_path / "upload-suppliers.sqlite3"
    monkeypatch.setenv("SHARED_ACCESS_CODE", "test-access-code")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "55123511")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    from app.config import get_settings
    from app.database import get_connection, initialize_database

    get_settings.cache_clear()
    initialize_database()
    connection = get_connection()
    yield connection
    connection.close()
    get_settings.cache_clear()


def test_build_supplier_matches_groups_repeated_factory_once(upload_supplier_connection):
    rows = [
        preview_row(4, "Same Factory", "GTS-1"),
        preview_row(5, "Same Factory", "GTS-2"),
    ]

    matches = build_supplier_matches(upload_supplier_connection, rows)

    assert len(matches) == 1
    assert matches[0]["status"] == "pending_unmatched"
    assert matches[0]["occurrence_count"] == 2
    assert rows[0]["supplier_match_key"] == rows[1]["supplier_match_key"]


def test_build_supplier_matches_creates_blank_pending_group(upload_supplier_connection):
    rows = [preview_row(4, "", "GTS-BLANK")]

    matches = build_supplier_matches(upload_supplier_connection, rows)

    assert len(matches) == 1
    assert matches[0]["status"] == "blank_pending"
    assert matches[0]["display_factory"] == "空白供应商"


def test_build_supplier_matches_auto_matches_full_short_and_alias(upload_supplier_connection):
    supplier_id = create_supplier(
        upload_supplier_connection,
        values={
            "supplier_full_name": "Auto Full",
            "supplier_short_name": "Auto Short",
            "aliases_text": "Auto Alias",
        },
        operator_name="Nancy",
    )
    rows = [
        preview_row(4, "Auto Full", "GTS-FULL"),
        preview_row(5, "Auto Short", "GTS-SHORT"),
        preview_row(6, "Auto Alias", "GTS-ALIAS"),
    ]

    matches = build_supplier_matches(upload_supplier_connection, rows)

    assert [match["status"] for match in matches] == [
        "auto_matched",
        "auto_matched",
        "auto_matched",
    ]
    assert {match["supplier_id"] for match in matches} == {supplier_id}


def test_link_preview_supplier_updates_payload_rows_and_aliases(upload_supplier_connection):
    supplier_id = create_supplier(
        upload_supplier_connection,
        values={"supplier_full_name": "Known Full", "supplier_short_name": "Known Short"},
        operator_name="Nancy",
    )
    rows = [preview_row(4, "Factory Alias", "GTS-LINK")]
    matches = build_supplier_matches(upload_supplier_connection, rows)
    payload = {"rows": rows, "supplier_matches": matches}

    error = link_preview_supplier(
        upload_supplier_connection,
        payload,
        match_key=matches[0]["key"],
        supplier_id=supplier_id,
        operator_name="Nancy",
    )
    supplier = get_supplier(upload_supplier_connection, supplier_id)

    assert error is None
    assert payload["supplier_matches"][0]["status"] == "resolved_existing"
    assert payload["rows"][0]["supplier_id"] == supplier_id
    assert "Factory Alias" in supplier["aliases_text"]
    assert validate_all_suppliers_resolved(payload) == []


def test_create_preview_supplier_defaults_non_blank_factory_values(upload_supplier_connection):
    rows = [preview_row(4, "Factory New", "GTS-CREATE")]
    matches = build_supplier_matches(upload_supplier_connection, rows)
    payload = {"rows": rows, "supplier_matches": matches}

    supplier_id, error = create_preview_supplier(
        upload_supplier_connection,
        payload,
        match_key=matches[0]["key"],
        supplier_full_name="",
        supplier_short_name="Factory New",
        aliases_text="",
        operator_name="Nancy",
    )
    supplier = get_supplier(upload_supplier_connection, supplier_id)

    assert error is None
    assert supplier["supplier_full_name"] == "Factory New"
    assert supplier["supplier_short_name"] == "Factory New"
    assert supplier["aliases_text"] == "Factory New"
    assert payload["supplier_matches"][0]["factory_value_for_import"] == "Factory New"


def test_create_preview_supplier_requires_names_for_blank_factory(upload_supplier_connection):
    rows = [preview_row(4, "", "GTS-BLANK")]
    matches = build_supplier_matches(upload_supplier_connection, rows)
    payload = {"rows": rows, "supplier_matches": matches}

    supplier_id, error = create_preview_supplier(
        upload_supplier_connection,
        payload,
        match_key=matches[0]["key"],
        supplier_full_name="",
        supplier_short_name="",
        aliases_text="",
        operator_name="Nancy",
    )

    assert supplier_id is None
    assert error is not None
    assert "请填写供应商全称" in error
    assert "请填写供应商简称" in error


def test_blank_factory_resolution_fills_row_factory_from_supplier_short_name(
    upload_supplier_connection,
):
    supplier_id = create_supplier(
        upload_supplier_connection,
        values={"supplier_full_name": "Blank Full", "supplier_short_name": "Blank Short"},
        operator_name="Nancy",
    )
    rows = [preview_row(4, "", "GTS-BLANK")]
    matches = build_supplier_matches(upload_supplier_connection, rows)
    payload = {"rows": rows, "supplier_matches": matches}

    error = link_preview_supplier(
        upload_supplier_connection,
        payload,
        match_key=matches[0]["key"],
        supplier_id=supplier_id,
        operator_name="Nancy",
    )
    apply_supplier_resolution_to_rows(payload["rows"], payload["supplier_matches"])

    assert error is None
    assert payload["rows"][0]["supplier_id"] == supplier_id
    assert payload["rows"][0]["values"]["factory"] == "Blank Short"
    assert validate_all_suppliers_resolved(payload) == []


def preview_row(row_number: int, factory: str, gts_no: str) -> dict:
    return {
        "row_number": row_number,
        "errors": [],
        "values": {
            "gts_no": gts_no,
            "oem": "",
            "description": "",
            "chinese_description": "",
            "factory": factory,
            "unit": "pc",
            "unit_price": 10,
        },
    }
