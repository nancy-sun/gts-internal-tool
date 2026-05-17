import sqlite3
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.services.import_persistence import import_preview_rows
from app.services.quotation_export import create_generated_workbook
from app.services.search import group_search_results, search_catalogue
from app.services.suppliers import (
    add_alias_text_alias,
    clean_aliases_text,
    create_supplier,
    create_supplier_from_candidate,
    get_supplier,
    link_supplier_candidate,
    match_supplier_by_name,
    normalize_supplier_name,
    parse_rating,
    split_supplier_aliases,
    supplier_form_values_from_db,
    sync_supplier_aliases,
    update_supplier,
    validate_supplier_short_name_unique,
    validate_supplier_values,
)


@pytest.fixture()
def supplier_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database_path = tmp_path / "suppliers.sqlite3"
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


def test_split_supplier_aliases_handles_chinese_and_english_commas():
    assert split_supplier_aliases("中际，宝威流体, 威佰昇") == [
        "中际",
        "宝威流体",
        "威佰昇",
    ]


def test_split_supplier_aliases_removes_duplicate_aliases():
    assert split_supplier_aliases("中际，中际,  中际 ") == ["中际"]


def test_clean_aliases_text_uses_chinese_comma_separator():
    assert clean_aliases_text("中际，宝威流体, 威佰昇") == "中际，宝威流体，威佰昇"


def test_supplier_save_creates_aliases_from_full_short_and_aliases_text(supplier_connection):
    supplier_id = create_supplier(
        supplier_connection,
        values={
            "supplier_full_name": "中际",
            "supplier_short_name": "中际短名",
            "aliases_text": "宝威流体, 威佰昇",
        },
        operator_name="Nancy",
    )

    aliases = fetch_aliases(supplier_connection, supplier_id)

    assert aliases["中际"]["source"] == "full_name"
    assert aliases["中际短名"]["source"] == "short_name"
    assert aliases["宝威流体"]["source"] == "aliases_text"
    assert aliases["威佰昇"]["source"] == "aliases_text"


def test_supplier_edit_removes_old_aliases_text_alias_but_keeps_full_and_short_aliases(
    supplier_connection,
):
    supplier_id = create_supplier(
        supplier_connection,
        values={
            "supplier_full_name": "中际",
            "supplier_short_name": "中际短名",
            "aliases_text": "宝威流体，威佰昇",
        },
        operator_name="Nancy",
    )

    update_supplier(
        supplier_connection,
        supplier_id=supplier_id,
        values={
            "supplier_full_name": "中际",
            "supplier_short_name": "中际短名",
            "aliases_text": "宝威流体",
        },
        operator_name="Nancy",
    )

    aliases = fetch_aliases(supplier_connection, supplier_id)
    assert "威佰昇" not in aliases
    assert aliases["中际"]["source"] == "full_name"
    assert aliases["中际短名"]["source"] == "short_name"
    assert aliases["宝威流体"]["source"] == "aliases_text"


def test_aliases_text_duplicate_does_not_replace_full_or_short_name_aliases(
    supplier_connection,
):
    supplier_id = create_supplier(
        supplier_connection,
        values={
            "supplier_full_name": "中际",
            "supplier_short_name": "中际短名",
            "aliases_text": "中际，中际短名",
        },
        operator_name="Nancy",
    )

    aliases = fetch_aliases(supplier_connection, supplier_id)

    assert aliases["中际"]["source"] == "full_name"
    assert aliases["中际短名"]["source"] == "short_name"


def test_supplier_form_values_prefills_aliases_text_from_alias_rows_when_column_is_empty(
    supplier_connection,
):
    supplier_id = create_supplier(
        supplier_connection,
        values={"supplier_full_name": "中际", "aliases_text": "宝威流体，威佰昇"},
        operator_name="Nancy",
    )
    supplier_connection.execute(
        "UPDATE suppliers SET aliases_text = '' WHERE id = ?",
        (supplier_id,),
    )
    supplier = get_supplier(supplier_connection, supplier_id)

    values = supplier_form_values_from_db(supplier_connection, supplier)

    assert values["aliases_text"] == "宝威流体，威佰昇"


def test_rating_fields_accept_null_and_1_to_5_only():
    assert parse_rating("") is None
    assert parse_rating(None) is None
    assert parse_rating("1") == 1
    assert parse_rating("5") == 5
    for value in ("0", "6", "bad"):
        with pytest.raises(ValueError):
            parse_rating(value)


def test_validate_supplier_values_rejects_invalid_rating():
    errors = validate_supplier_values(
        {"supplier_full_name": "中际", "quality_rating": "6"},
        "Nancy",
    )

    assert "质量评分必须为空或 1-5。" in errors


def test_supplier_short_name_must_be_unique(supplier_connection):
    create_supplier(
        supplier_connection,
        values={"supplier_full_name": "供应商A", "supplier_short_name": "共同简称"},
        operator_name="Nancy",
    )

    errors = validate_supplier_short_name_unique(supplier_connection, "共同简称")

    assert errors == ["供应商简称已存在，请使用唯一简称。"]


def test_import_matches_supplier_by_full_name_short_name_and_alias(supplier_connection):
    supplier_id = create_supplier(
        supplier_connection,
        values={
            "supplier_full_name": "中际",
            "supplier_short_name": "中际短名",
            "aliases_text": "宝威流体，威佰昇",
        },
        operator_name="Nancy",
    )

    imported_ids = [
        import_factory_row(supplier_connection, "中际", "GTS-FULL"),
        import_factory_row(supplier_connection, "中际短名", "GTS-SHORT"),
        import_factory_row(supplier_connection, "宝威流体", "GTS-ALIAS"),
        import_factory_row(supplier_connection, "威佰昇", "GTS-ALIAS2"),
    ]

    assert imported_ids == [supplier_id, supplier_id, supplier_id, supplier_id]


def test_linked_quotation_displays_updated_supplier_short_name_in_search_and_export(
    supplier_connection,
):
    supplier_id = create_supplier(
        supplier_connection,
        values={"supplier_full_name": "中际全称", "supplier_short_name": "旧简称"},
        operator_name="Nancy",
    )
    insert_unlinked_quotation(supplier_connection, "历史工厂名", "GTS-DISPLAY")
    supplier_connection.execute(
        "UPDATE quotation_items SET supplier_id = ? WHERE gts_no = 'GTS-DISPLAY'",
        (supplier_id,),
    )
    quotation_id = supplier_connection.execute(
        "SELECT id FROM quotation_items WHERE gts_no = 'GTS-DISPLAY'"
    ).fetchone()["id"]

    update_supplier(
        supplier_connection,
        supplier_id=supplier_id,
        values={"supplier_full_name": "中际全称", "supplier_short_name": "新简称"},
        operator_name="Nancy",
    )

    rows, _ = search_catalogue(supplier_connection, field="gts_no", query="GTS-DISPLAY")
    grouped = group_search_results(rows)
    stream, generated_count = create_generated_workbook(
        supplier_connection,
        preview_rows=[
            {
                "row_number": 4,
                "values": {"gts_no": "GTS-DISPLAY", "quantity": 1},
            }
        ],
        selected_candidate_ids={4: quotation_id},
        operator_name="Nancy",
        request_file_name="request.xlsx",
    )
    workbook = load_workbook(stream)

    assert grouped[0]["quotations"][0]["supplier_display_name"] == "新简称"
    assert generated_count == 1
    assert workbook.active["F3"].value == "新简称"


def test_ambiguous_alias_does_not_auto_link(supplier_connection):
    create_supplier(
        supplier_connection,
        values={"supplier_full_name": "供应商A", "aliases_text": "共同简称"},
        operator_name="Nancy",
    )
    create_supplier(
        supplier_connection,
        values={"supplier_full_name": "供应商B", "aliases_text": "共同简称"},
        operator_name="Nancy",
    )

    supplier_id = import_factory_row(supplier_connection, "共同简称", "GTS-AMB")
    match = match_supplier_by_name(supplier_connection, "共同简称")

    assert supplier_id is None
    assert match.status == "ambiguous"
    assert len(match.suppliers) == 2


def test_removed_alias_no_longer_matches_but_full_and_short_names_still_match(
    supplier_connection,
):
    supplier_id = create_supplier(
        supplier_connection,
        values={
            "supplier_full_name": "中际",
            "supplier_short_name": "中际短名",
            "aliases_text": "宝威流体",
        },
        operator_name="Nancy",
    )
    update_supplier(
        supplier_connection,
        supplier_id=supplier_id,
        values={
            "supplier_full_name": "中际",
            "supplier_short_name": "中际短名",
            "aliases_text": "",
        },
        operator_name="Nancy",
    )

    assert import_factory_row(supplier_connection, "宝威流体", "GTS-REMOVED") is None
    assert import_factory_row(supplier_connection, "中际", "GTS-FULL2") == supplier_id
    assert import_factory_row(supplier_connection, "中际短名", "GTS-SHORT2") == supplier_id


def test_supplier_candidate_link_and_create_preserve_factory_text(supplier_connection):
    supplier_id = create_supplier(
        supplier_connection,
        values={"supplier_full_name": "中际", "aliases_text": ""},
        operator_name="Nancy",
    )
    insert_unlinked_quotation(supplier_connection, "宝威流体", "GTS-CAND-1")

    linked_count = link_supplier_candidate(
        supplier_connection,
        factory_name="宝威流体",
        supplier_id=supplier_id,
        operator_name="Nancy",
        action_type="supplier_candidate_linked",
    )

    row = supplier_connection.execute(
        "SELECT supplier_id, factory FROM quotation_items WHERE gts_no = 'GTS-CAND-1'"
    ).fetchone()
    assert linked_count == 1
    assert row["supplier_id"] == supplier_id
    assert row["factory"] == "宝威流体"

    insert_unlinked_quotation(supplier_connection, "新供应商", "GTS-CAND-2")
    new_supplier_id = create_supplier_from_candidate(
        supplier_connection,
        factory_name="新供应商",
        operator_name="Nancy",
    )
    new_row = supplier_connection.execute(
        "SELECT supplier_id, factory FROM quotation_items WHERE gts_no = 'GTS-CAND-2'"
    ).fetchone()
    assert new_row["supplier_id"] == new_supplier_id
    assert new_row["factory"] == "新供应商"


def fetch_aliases(connection: sqlite3.Connection, supplier_id: int) -> dict[str, sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT alias_name, source
        FROM supplier_aliases
        WHERE supplier_id = ?
        """,
        (supplier_id,),
    ).fetchall()
    return {row["alias_name"]: row for row in rows}


def import_factory_row(connection: sqlite3.Connection, factory: str, gts_no: str):
    import_preview_rows(
        connection,
        preview_rows=[
            {
                "row_number": 4,
                "errors": [],
                "values": {
                    "gts_no": gts_no,
                    "gts_no_normalized": normalize_supplier_name(gts_no),
                    "oem": "",
                    "oem_normalized": "",
                    "factory": factory,
                    "unit": "pc",
                    "unit_price": 10,
                },
            }
        ],
        operator_name="Nancy",
        file_name="supplier-match.xlsx",
        selected_updates=set(),
    )
    row = connection.execute(
        "SELECT supplier_id FROM quotation_items WHERE gts_no = ?",
        (gts_no,),
    ).fetchone()
    return row["supplier_id"]


def insert_unlinked_quotation(connection: sqlite3.Connection, factory: str, gts_no: str) -> None:
    connection.execute(
        """
        INSERT INTO products (
            gts_no, gts_no_normalized, created_by, created_at, updated_by, updated_at
        )
        VALUES (?, ?, 'Nancy', '2026-05-16T00:00:00+00:00', 'Nancy', '2026-05-16T00:00:00+00:00')
        """,
        (gts_no, normalize_supplier_name(gts_no)),
    )
    product_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    connection.execute(
        """
        INSERT INTO quotation_items (
            product_id, gts_no, gts_no_normalized, factory, created_by, created_at, updated_by, updated_at
        )
        VALUES (?, ?, ?, ?, 'Nancy', '2026-05-16T00:00:00+00:00', 'Nancy', '2026-05-16T00:00:00+00:00')
        """,
        (product_id, gts_no, normalize_supplier_name(gts_no), factory),
    )
