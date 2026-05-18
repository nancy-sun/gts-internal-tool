from __future__ import annotations

from collections import Counter
from sqlite3 import Connection
from typing import Any

from app.services.operation_logging import create_operation_log
from app.services.suppliers import (
    add_alias_text_alias,
    create_supplier,
    get_supplier,
    normalize_supplier_name,
    sync_supplier_aliases,
    validate_supplier_short_name_unique,
)
from app.services.upload_preview_state import find_supplier_match
from app.services.upload_supplier_matching import (
    build_supplier_matches,
    supplier_display,
    supplier_factory_display_value,
    supplier_match_is_unresolved,
    supplier_match_key,
    supplier_matches_summary,
    supplier_status_label,
    unresolved_supplier_count,
)


def link_preview_supplier(
    connection: Connection,
    payload: dict[str, Any],
    *,
    match_key: str,
    supplier_id: int,
    operator_name: str,
    resolved_status: str = "resolved_existing",
    action_type: str = "supplier_preview_linked",
    add_factory_alias: bool = True,
    force_factory_value: bool = False,
) -> str | None:
    match = find_supplier_match(payload, match_key)
    if not match:
        return "找不到供应商匹配项。"
    supplier = get_supplier(connection, supplier_id)
    if not supplier:
        return "选择的供应商不存在。"
    factory = _text(match.get("factory"))
    if factory:
        if add_factory_alias:
            add_alias_text_alias(connection, supplier_id, factory)
            sync_supplier_aliases(connection, supplier_id, operator_name)
        factory_value_for_import = (
            supplier_factory_display_value(supplier) if force_factory_value else factory
        )
    else:
        factory_value_for_import = supplier_factory_display_value(supplier)
        if not factory_value_for_import:
            return "选择的供应商缺少名称，不能用于空白供应商。"
    update_resolved_supplier_match(
        payload,
        match,
        supplier=supplier,
        status=resolved_status,
        factory_value_for_import=factory_value_for_import,
        force_factory_value=force_factory_value,
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type=action_type,
        row_count=match.get("occurrence_count"),
        note=f"供应商ID={supplier_id}; 工厂={match.get('display_factory')}",
    )
    return None


def create_preview_supplier(
    connection: Connection,
    payload: dict[str, Any],
    *,
    match_key: str,
    supplier_full_name: str,
    supplier_short_name: str,
    aliases_text: str,
    operator_name: str,
    add_factory_alias: bool = True,
    force_factory_value: bool = False,
) -> tuple[int | None, str | None]:
    match = find_supplier_match(payload, match_key)
    if not match:
        return None, "找不到供应商匹配项。"
    values = prepare_preview_supplier_values(
        match,
        supplier_full_name=supplier_full_name,
        supplier_short_name=supplier_short_name,
        aliases_text=aliases_text,
        add_factory_alias=add_factory_alias,
    )
    errors = validate_preview_supplier_values(
        connection,
        values,
        operator_name=operator_name,
    )
    if errors:
        return None, "；".join(errors)
    supplier_id = create_supplier(
        connection,
        values=values,
        operator_name=operator_name,
    )
    supplier = get_supplier(connection, supplier_id)
    factory = _text(match.get("factory"))
    factory_value_for_import = (
        supplier_factory_display_value(supplier)
        if force_factory_value or not factory
        else factory
    )
    update_resolved_supplier_match(
        payload,
        match,
        supplier=supplier,
        status="resolved_new",
        factory_value_for_import=factory_value_for_import,
        force_factory_value=force_factory_value,
    )
    create_operation_log(
        connection,
        operator_name=operator_name,
        action_type="supplier_preview_created",
        row_count=match.get("occurrence_count"),
        note=f"供应商ID={supplier_id}; 工厂={match.get('display_factory')}",
    )
    return supplier_id, None


def resolve_preview_ambiguous_supplier(
    connection: Connection,
    payload: dict[str, Any],
    *,
    match_key: str,
    supplier_id: int,
    operator_name: str,
) -> str | None:
    return link_preview_supplier(
        connection,
        payload,
        match_key=match_key,
        supplier_id=supplier_id,
        operator_name=operator_name,
        resolved_status="ambiguous_resolved",
        action_type="supplier_preview_ambiguous_resolved",
    )


def resolve_batch_preview_suppliers(
    connection: Connection,
    payload: dict[str, Any],
    form,
    *,
    operator_name: str,
) -> list[str]:
    supplier_matches = payload.get("supplier_matches") or []
    pending_matches = [
        match for match in supplier_matches if supplier_match_is_unresolved(match)
    ]
    errors = validate_batch_supplier_form(form, pending_matches)
    if errors:
        return errors

    errors.extend(validate_batch_supplier_database(connection, form, pending_matches))
    if errors:
        return errors

    create_counts_by_short_name = Counter(
        normalize_supplier_name(str(form.get(f"supplier_short_name__{match['key']}") or ""))
        for match in pending_matches
        if str(form.get(f"action__{match['key']}") or "") == "create"
    )
    created_suppliers_by_name: dict[str, int] = {}
    for match in pending_matches:
        key = match["key"]
        action = str(form.get(f"action__{key}") or "")
        if action in {"existing", "ambiguous"}:
            supplier_id = int(str(form.get(f"supplier_id__{key}") or "0"))
            error = link_preview_supplier(
                connection,
                payload,
                match_key=key,
                supplier_id=supplier_id,
                operator_name=operator_name,
                resolved_status=(
                    "ambiguous_resolved"
                    if match.get("status") == "ambiguous_pending"
                    else "resolved_existing"
                ),
                action_type=(
                    "supplier_preview_ambiguous_resolved"
                    if match.get("status") == "ambiguous_pending"
                    else "supplier_preview_linked"
                ),
            )
            if error:
                errors.append(error)
        elif action == "create":
            normalized_short_name = normalize_supplier_name(
                str(form.get(f"supplier_short_name__{key}") or "")
            )
            is_same_batch_merge = create_counts_by_short_name[normalized_short_name] > 1
            existing_supplier_id = created_suppliers_by_name.get(normalized_short_name)
            if existing_supplier_id:
                error = link_preview_supplier(
                    connection,
                    payload,
                    match_key=key,
                    supplier_id=existing_supplier_id,
                    operator_name=operator_name,
                    resolved_status="resolved_new",
                    action_type="supplier_preview_created",
                    add_factory_alias=False,
                    force_factory_value=True,
                )
                if error:
                    errors.append(error)
                continue
            supplier_id, error = create_preview_supplier(
                connection,
                payload,
                match_key=key,
                supplier_full_name=str(form.get(f"supplier_short_name__{key}") or ""),
                supplier_short_name=str(form.get(f"supplier_short_name__{key}") or ""),
                aliases_text="",
                operator_name=operator_name,
                add_factory_alias=not is_same_batch_merge,
                force_factory_value=is_same_batch_merge,
            )
            if error:
                errors.append(error)
                continue
            created_suppliers_by_name[normalized_short_name] = int(supplier_id)
    return errors


def update_resolved_supplier_match(
    payload: dict[str, Any],
    match: dict[str, Any],
    *,
    supplier,
    status: str,
    factory_value_for_import: str,
    force_factory_value: bool = False,
) -> None:
    match["status"] = status
    match["status_label"] = supplier_status_label(status)
    match["supplier_id"] = supplier["id"]
    match["factory_value_for_import"] = factory_value_for_import
    match["force_factory_value_for_import"] = force_factory_value
    match["matched_supplier"] = supplier_display(supplier)
    apply_supplier_resolution_to_rows(payload.get("rows") or [], payload.get("supplier_matches") or [])


def prepare_preview_supplier_values(
    match: dict[str, Any],
    *,
    supplier_full_name: str,
    supplier_short_name: str,
    aliases_text: str,
    add_factory_alias: bool = True,
) -> dict[str, str]:
    factory = _text(match.get("factory"))
    short_name = supplier_short_name.strip()
    full_name = supplier_full_name.strip() or short_name
    default_alias = factory if factory and add_factory_alias else ""
    return {
        "supplier_full_name": full_name,
        "supplier_short_name": short_name,
        "aliases_text": aliases_text.strip() or default_alias,
    }


def validate_preview_supplier_values(
    connection: Connection,
    values: dict[str, str],
    *,
    operator_name: str,
) -> list[str]:
    errors = []
    if not operator_name:
        errors.append("请填写操作人。")
    if not values["supplier_full_name"]:
        errors.append("请填写供应商全称。")
    if not values["supplier_short_name"]:
        errors.append("请填写供应商简称。")
    errors.extend(
        validate_supplier_short_name_unique(
            connection,
            values["supplier_short_name"],
        )
    )
    return errors


def validate_batch_supplier_form(form, pending_matches: list[dict[str, Any]]) -> list[str]:
    errors = []
    for match in pending_matches:
        key = match["key"]
        label = match.get("display_factory") or key
        action = str(form.get(f"action__{key}") or "")
        if match.get("status") == "ambiguous_pending":
            if action != "ambiguous":
                errors.append(f"{label} 请选择一个供应商。")
                continue
            if not str(form.get(f"supplier_id__{key}") or "").strip():
                errors.append(f"{label} 请选择一个供应商。")
            continue
        if action not in {"existing", "create"}:
            errors.append(f"{label} 请选择处理方式。")
            continue
        if action == "existing" and not str(form.get(f"supplier_id__{key}") or "").strip():
            errors.append(f"{label} 请选择已有供应商。")
        if action == "create" and not str(form.get(f"supplier_short_name__{key}") or "").strip():
            errors.append(f"{label} 请填写供应商简称。")
    return errors


def validate_batch_supplier_database(
    connection: Connection,
    form,
    pending_matches: list[dict[str, Any]],
) -> list[str]:
    errors = []
    for match in pending_matches:
        key = match["key"]
        action = str(form.get(f"action__{key}") or "")
        if action in {"existing", "ambiguous"}:
            supplier_id = int(str(form.get(f"supplier_id__{key}") or "0"))
            if supplier_id and not get_supplier(connection, supplier_id):
                errors.append(f"{match.get('display_factory')} 选择的供应商不存在。")
        elif action == "create":
            short_name = str(form.get(f"supplier_short_name__{key}") or "").strip()
            duplicate_errors = validate_supplier_short_name_unique(connection, short_name)
            errors.extend(f"{short_name}：{message}" for message in duplicate_errors)
    return errors


def apply_supplier_resolution_to_rows(
    rows: list[dict[str, Any]],
    supplier_matches: list[dict[str, Any]],
) -> None:
    resolutions = {match["key"]: match for match in supplier_matches}
    for row in rows:
        key = row.get("supplier_match_key") or supplier_match_key(
            (row.get("values") or {}).get("factory")
        )
        row["supplier_match_key"] = key
        match = resolutions.get(key)
        if not match:
            continue
        row["supplier_id"] = match.get("supplier_id")
        should_overwrite_factory = bool(match.get("force_factory_value_for_import"))
        if should_overwrite_factory or not _text((row.get("values") or {}).get("factory")):
            row.setdefault("values", {})["factory"] = match.get("factory_value_for_import")


def supplier_resolution_map(
    supplier_matches: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        match["key"]: {
            "supplier_id": match.get("supplier_id"),
            "factory_value_for_import": match.get("factory_value_for_import"),
            "force_factory_value_for_import": bool(match.get("force_factory_value_for_import")),
        }
        for match in supplier_matches
    }


def resolve_import_supplier_for_row(
    row: dict[str, Any],
    supplier_matches: list[dict[str, Any]],
) -> dict[str, Any] | None:
    resolutions = supplier_resolution_map(supplier_matches)
    key = row.get("supplier_match_key") or supplier_match_key((row.get("values") or {}).get("factory"))
    return resolutions.get(key)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
