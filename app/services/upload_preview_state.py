from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import BASE_DIR
from app.services.preview_tokens import preview_file_path
from app.services.upload_supplier_matching import supplier_match_is_unresolved


DEFAULT_UPLOAD_DIR = BASE_DIR / "uploads"


def preview_path(token: str, upload_dir: Path = DEFAULT_UPLOAD_DIR) -> Path:
    return preview_file_path(upload_dir, "preview", token)


def load_preview_payload(token: str, upload_dir: Path = DEFAULT_UPLOAD_DIR) -> dict[str, Any] | None:
    path = preview_path(token, upload_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_preview_payload(
    token: str,
    payload: dict[str, Any],
    upload_dir: Path = DEFAULT_UPLOAD_DIR,
) -> None:
    preview_path(token, upload_dir).write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def get_supplier_matches(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("supplier_matches") or []


def find_supplier_match(payload: dict[str, Any], match_key: str) -> dict[str, Any] | None:
    for match in get_supplier_matches(payload):
        if match.get("key") == match_key:
            return match
    return None


def update_supplier_match(
    payload: dict[str, Any],
    match_key: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    match = find_supplier_match(payload, match_key)
    if match is None:
        return None
    match.update(updates)
    return match


def count_unresolved_supplier_matches(payload: dict[str, Any]) -> int:
    return sum(
        1 for match in get_supplier_matches(payload) if supplier_match_is_unresolved(match)
    )


def validate_all_suppliers_resolved(payload: dict[str, Any]) -> list[str]:
    supplier_matches = payload.get("supplier_matches")
    if supplier_matches is None:
        return ["请先完成供应商匹配。"]
    if count_unresolved_supplier_matches(payload):
        return ["还有未处理的供应商，请先完成供应商匹配。"]
    for row in payload.get("rows") or []:
        if row.get("errors"):
            continue
        values = row.get("values") or {}
        if not row.get("supplier_id"):
            return ["还有未处理的供应商，请先完成供应商匹配。"]
        if not str(values.get("factory") or "").strip():
            return ["还有空白供应商，请先完成供应商匹配。"]
    return []
