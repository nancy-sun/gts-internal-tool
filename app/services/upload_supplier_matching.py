from __future__ import annotations

from collections import OrderedDict
from hashlib import sha1
from sqlite3 import Connection, Row
from typing import Any

from app.services.suppliers import match_supplier_by_name, supplier_display_name


BLANK_FACTORY_KEY = "__BLANK_FACTORY__"
PENDING_STATUSES = {"pending_unmatched", "blank_pending", "ambiguous_pending"}
RESOLVED_STATUSES = {
    "auto_matched",
    "resolved_existing",
    "resolved_new",
    "ambiguous_resolved",
}


def build_supplier_matches(
    connection: Connection,
    preview_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in preview_rows:
        if row.get("errors"):
            continue
        values = row.get("values") or {}
        factory = _text(values.get("factory"))
        key = supplier_match_key(factory)
        group = groups.get(key)
        if group is None:
            group = new_supplier_match_group(connection, key, factory)
            groups[key] = group
        group["occurrence_count"] += 1
        if len(group["sample_rows"]) < 3:
            group["sample_rows"].append(sample_row(row))
        row["supplier_match_key"] = key
    return sorted(groups.values(), key=supplier_match_sort_key)


def new_supplier_match_group(connection: Connection, key: str, factory: str) -> dict[str, Any]:
    if not factory:
        return {
            "key": key,
            "factory": "",
            "display_factory": "空白供应商",
            "is_blank_factory": True,
            "status": "blank_pending",
            "status_label": supplier_status_label("blank_pending"),
            "occurrence_count": 0,
            "supplier_id": None,
            "factory_value_for_import": None,
            "matched_supplier": None,
            "candidate_suppliers": [],
            "sample_rows": [],
        }

    match = match_supplier_by_name(connection, factory)
    candidate_suppliers = [supplier_display(supplier) for supplier in match.suppliers]
    supplier = match.supplier
    status = {
        "matched": "auto_matched",
        "ambiguous": "ambiguous_pending",
    }.get(match.status, "pending_unmatched")
    return {
        "key": key,
        "factory": factory,
        "display_factory": factory,
        "is_blank_factory": False,
        "status": status,
        "status_label": supplier_status_label(status),
        "occurrence_count": 0,
        "supplier_id": supplier["id"] if supplier else None,
        "factory_value_for_import": factory if supplier else None,
        "matched_supplier": supplier_display(supplier) if supplier else None,
        "candidate_suppliers": candidate_suppliers,
        "sample_rows": [],
    }


def supplier_match_key(factory: str | None) -> str:
    clean_factory = _text(factory)
    if not clean_factory:
        return BLANK_FACTORY_KEY
    digest = sha1(clean_factory.encode("utf-8")).hexdigest()[:16]
    return f"factory_{digest}"


def supplier_matches_summary(
    supplier_matches: list[dict[str, Any]],
    total_rows: int,
) -> dict[str, int]:
    return {
        "total_rows": total_rows,
        "total_matches": len(supplier_matches),
        "matched": sum(
            1 for match in supplier_matches if match.get("status") in RESOLVED_STATUSES
        ),
        "pending": sum(
            1 for match in supplier_matches if match.get("status") == "pending_unmatched"
        ),
        "blank": sum(1 for match in supplier_matches if match.get("status") == "blank_pending"),
        "ambiguous": sum(
            1 for match in supplier_matches if match.get("status") == "ambiguous_pending"
        ),
        "unresolved": unresolved_supplier_count(supplier_matches),
    }


def unresolved_supplier_count(supplier_matches: list[dict[str, Any]]) -> int:
    return sum(1 for match in supplier_matches if supplier_match_is_unresolved(match))


def supplier_match_is_unresolved(match: dict[str, Any]) -> bool:
    return (
        match.get("status") in PENDING_STATUSES
        or not match.get("supplier_id")
        or not _text(match.get("factory_value_for_import"))
    )


def supplier_status_label(status: str) -> str:
    return {
        "auto_matched": "已匹配",
        "pending_unmatched": "待处理",
        "blank_pending": "空白供应商，待处理",
        "ambiguous_pending": "多重匹配，待选择",
        "resolved_existing": "已关联已有供应商",
        "resolved_new": "已创建新供应商",
        "ambiguous_resolved": "多重匹配已处理",
    }.get(status, status)


def supplier_display(supplier: Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if not supplier:
        return None
    return {
        "id": supplier["id"],
        "supplier_full_name": _row_value(supplier, "supplier_full_name"),
        "supplier_short_name": _row_value(supplier, "supplier_short_name"),
        "aliases_text": _row_value(supplier, "aliases_text"),
        "display_name": supplier_display_name(supplier),
    }


def supplier_factory_display_value(supplier: Row | dict[str, Any]) -> str:
    return (
        _text(_row_value(supplier, "supplier_short_name"))
        or _text(_row_value(supplier, "supplier_full_name"))
        or _text(_row_value(supplier, "supplier_name"))
    )


def sample_row(row: dict[str, Any]) -> dict[str, Any]:
    values = row.get("values") or {}
    return {
        "row_number": row.get("row_number"),
        "gts_no": _text(values.get("gts_no")),
        "oem": _text(values.get("oem")),
        "description": _text(values.get("description"))
        or _text(values.get("chinese_description")),
        "unit_price": values.get("unit_price"),
    }


def supplier_match_sort_key(match: dict[str, Any]) -> tuple[int, str]:
    status_order = {
        "blank_pending": 0,
        "pending_unmatched": 1,
        "ambiguous_pending": 2,
        "resolved_existing": 3,
        "resolved_new": 3,
        "ambiguous_resolved": 3,
        "auto_matched": 4,
    }
    return (status_order.get(match.get("status"), 9), _text(match.get("display_factory")))


def _row_value(row: Row | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key] if key in row.keys() else None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
