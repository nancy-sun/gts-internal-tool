import json
import logging
from pathlib import Path
from uuid import uuid4
from collections import Counter

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse

from app.auth import get_session_operator_name, require_auth, set_session_operator_name
from app.config import BASE_DIR, get_settings
from app.database import get_connection
from app.navigation import UPLOAD_CRUMB, breadcrumbs, child_breadcrumbs
from app.services.backup import BackupError, create_auto_backup
from app.services.excel_parser import iter_full_quotation_workbook_rows
from app.services.import_full_quotation import (
    build_import_lookup_context,
    build_import_preview_row,
    import_preview_rows,
)
from app.services.operation_logging import create_operation_log
from app.services.preview_tokens import preview_file_path, remove_preview_file
from app.services.suppliers import (
    add_alias_text_alias,
    create_supplier,
    get_supplier,
    list_suppliers,
    normalize_supplier_name,
    sync_supplier_aliases,
    validate_supplier_short_name_unique,
)
from app.services.upload_supplier_resolution import (
    apply_supplier_resolution_to_rows,
    build_supplier_matches,
    supplier_display,
    supplier_factory_display_value,
    supplier_match_is_unresolved,
    supplier_matches_summary,
    supplier_resolution_map,
    supplier_status_label,
    unresolved_supplier_count,
)
from app.services.upload_validation import (
    sanitize_upload_filename,
    validate_full_quotation_workbook,
    validate_upload_size,
    validate_xlsx_upload,
)
from app.templating import templates


router = APIRouter()
UPLOAD_DIR = BASE_DIR / "uploads"
logger = logging.getLogger(__name__)
UPLOAD_PREVIEW_ERROR = "预览加载失败，请检查 Excel 文件格式后重新上传。"


@router.get("/upload")
def upload_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "request": request,
            "error": None,
            "operator_name": get_session_operator_name(request),
            "breadcrumbs": breadcrumbs(UPLOAD_CRUMB),
        },
    )


@router.post("/upload/preview")
async def upload_preview(
    request: Request,
    operator_name: str = Form(...),
    excel_file: UploadFile = File(...),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    error = validate_xlsx_upload(excel_file, operator_name)
    if error:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "request": request,
                "error": error,
                "operator_name": operator_name,
                "breadcrumbs": breadcrumbs(UPLOAD_CRUMB),
            },
            status_code=400,
        )

    contents = await excel_file.read()
    settings = get_settings()
    size_error = validate_upload_size(
        contents,
        max_upload_size_bytes=settings.max_upload_size_bytes,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
    if size_error:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "request": request,
                "error": size_error,
                "operator_name": operator_name,
                "breadcrumbs": breadcrumbs(UPLOAD_CRUMB),
            },
            status_code=400,
        )
    workbook_error = validate_full_quotation_workbook(contents)
    if workbook_error:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "request": request,
                "error": workbook_error,
                "operator_name": operator_name,
                "breadcrumbs": breadcrumbs(UPLOAD_CRUMB),
            },
            status_code=400,
        )

    token = uuid4().hex
    safe_name = sanitize_upload_filename(excel_file.filename, default="quotation.xlsx")
    workbook_path = UPLOAD_DIR / f"{token}_{safe_name}"
    workbook_path.write_bytes(contents)

    preview_payload = {
        "operator_name": operator_name,
        "file_name": safe_name,
        "workbook_path": str(workbook_path),
        "rows": [],
    }
    preview_path(token).write_text(
        json.dumps(preview_payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return templates.TemplateResponse(
        request,
        "upload_preview_loading.html",
        {
            "request": request,
            "token": token,
            "operator_name": operator_name,
            "file_name": safe_name,
            "return_url": "/upload",
            "breadcrumbs": child_breadcrumbs(UPLOAD_CRUMB, "导入预览"),
        },
    )


@router.get("/upload/preview/stream/{token}")
def upload_preview_stream(request: Request, token: str):
    redirect = require_auth(request)
    if redirect:
        return redirect

    path = preview_path(token)
    if not path.exists():
        return StreamingResponse(
            iter([sse_event("preview_error", {"message": "找不到预览文件。"})]),
            media_type="text/event-stream",
        )

    def event_stream():
        payload = json.loads(path.read_text(encoding="utf-8"))
        parsed_rows = []
        workbook_path = Path(payload["workbook_path"])
        try:
            for parsed_row in iter_full_quotation_workbook_rows(workbook_path):
                parsed_rows.append(parsed_row)

            preview_rows = []
            with get_connection() as connection:
                lookup_context = build_import_lookup_context(connection, parsed_rows)
                suppliers = [supplier_display(supplier) for supplier in list_suppliers(connection, limit=1000)]
            for parsed_row in parsed_rows:
                yield sse_event("loading", {"row_number": parsed_row.row_number})
                preview_row = build_import_preview_row(lookup_context, parsed_row)
                preview_rows.append(preview_row)
                yield sse_event("row", preview_row)

            with get_connection() as connection:
                supplier_matches = build_supplier_matches(connection, preview_rows)
            apply_supplier_resolution_to_rows(preview_rows, supplier_matches)
            supplier_summary = supplier_matches_summary(supplier_matches, len(preview_rows))
            payload["rows"] = preview_rows
            payload["supplier_matches"] = supplier_matches
            path.write_text(
                json.dumps(payload, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            yield sse_event(
                "complete",
                {
                    "row_count": len(preview_rows),
                    "has_warnings": preview_has_warnings(preview_rows),
                    "has_errors": preview_has_errors(preview_rows),
                    "has_supplier_pending": bool(supplier_summary["unresolved"]),
                    "supplier_matches": supplier_matches,
                    "supplier_summary": supplier_summary,
                    "suppliers": suppliers,
                },
            )
        except Exception:
            logger.exception("Upload preview failed for token %s", token)
            yield sse_event("preview_error", {"message": UPLOAD_PREVIEW_ERROR})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/upload/preview/{token}")
def upload_preview_display(request: Request, token: str):
    redirect = require_auth(request)
    if redirect:
        return redirect

    payload = load_preview_payload(token)
    if not payload:
        return RedirectResponse(url="/upload", status_code=303)
    return render_upload_preview(request, token, payload)


@router.post("/upload/preview/supplier/link")
def upload_preview_supplier_link(
    request: Request,
    token: str = Form(...),
    match_key: str = Form(...),
    supplier_id: int = Form(...),
    operator_name: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    payload = load_preview_payload(token)
    if not payload:
        return RedirectResponse(url="/upload", status_code=303)

    with get_connection() as connection:
        error = resolve_supplier_match_with_existing(
            connection,
            payload,
            match_key=match_key,
            supplier_id=supplier_id,
            operator_name=operator_name,
            resolved_status="resolved_existing",
            action_type="supplier_preview_linked",
        )
        if error:
            return render_upload_preview(request, token, payload, error=error, status_code=400)
        connection.commit()
    save_preview_payload(token, payload)
    return RedirectResponse(url=f"/upload/preview/{token}", status_code=303)


@router.post("/upload/preview/supplier/batch")
async def upload_preview_supplier_batch(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    token = str(form.get("token") or "")
    operator_name = set_session_operator_name(request, str(form.get("operator_name") or ""))
    payload = load_preview_payload(token)
    if not payload:
        return RedirectResponse(url="/upload", status_code=303)

    supplier_matches = payload.get("supplier_matches") or []
    pending_matches = [
        match for match in supplier_matches if supplier_match_is_unresolved(match)
    ]
    errors = validate_batch_supplier_form(form, pending_matches)
    if errors:
        return render_upload_preview(
            request,
            token,
            payload,
            error="；".join(errors),
            status_code=400,
        )

    with get_connection() as connection:
        errors.extend(validate_batch_supplier_database(connection, form, pending_matches))
        if errors:
            return render_upload_preview(
                request,
                token,
                payload,
                error="；".join(errors),
                status_code=400,
            )

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
                error = resolve_supplier_match_with_existing(
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
                    error = resolve_supplier_match_with_existing(
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
                supplier_id = create_supplier_for_preview_match(
                    connection,
                    payload,
                    match,
                    supplier_short_name=str(form.get(f"supplier_short_name__{key}") or ""),
                    operator_name=operator_name,
                    add_factory_alias=not is_same_batch_merge,
                    force_factory_value=is_same_batch_merge,
                )
                created_suppliers_by_name[normalized_short_name] = supplier_id

        if errors:
            return render_upload_preview(
                request,
                token,
                payload,
                error="；".join(errors),
                status_code=400,
            )
        connection.commit()

    save_preview_payload(token, payload)
    return RedirectResponse(url=f"/upload/preview/{token}", status_code=303)


@router.post("/upload/preview/supplier/create")
def upload_preview_supplier_create(
    request: Request,
    token: str = Form(...),
    match_key: str = Form(...),
    operator_name: str = Form(""),
    supplier_full_name: str = Form(""),
    supplier_short_name: str = Form(""),
    aliases_text: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    payload = load_preview_payload(token)
    if not payload:
        return RedirectResponse(url="/upload", status_code=303)
    match = find_supplier_match(payload, match_key)
    if not match:
        return render_upload_preview(request, token, payload, error="找不到供应商匹配项。", status_code=400)

    factory = (match.get("factory") or "").strip()
    short_name = supplier_short_name.strip()
    values = {
        "supplier_full_name": supplier_full_name.strip() or short_name,
        "supplier_short_name": short_name,
        "aliases_text": aliases_text.strip() or (factory if not match.get("is_blank_factory") else ""),
    }
    errors = []
    if not operator_name:
        errors.append("请填写操作人。")
    if not values["supplier_full_name"]:
        errors.append("请填写供应商全称。")
    if not values["supplier_short_name"]:
        errors.append("请填写供应商简称。")

    with get_connection() as connection:
        errors.extend(
            validate_supplier_short_name_unique(
                connection,
                values["supplier_short_name"],
            )
        )
        if errors:
            return render_upload_preview(
                request,
                token,
                payload,
                error="；".join(errors),
                status_code=400,
            )
        create_supplier_for_preview_match(
            connection,
            payload,
            match,
            supplier_short_name=values["supplier_short_name"],
            operator_name=operator_name,
        )
        connection.commit()
    save_preview_payload(token, payload)
    return RedirectResponse(url=f"/upload/preview/{token}", status_code=303)


@router.post("/upload/preview/supplier/resolve-ambiguous")
def upload_preview_supplier_resolve_ambiguous(
    request: Request,
    token: str = Form(...),
    match_key: str = Form(...),
    supplier_id: int = Form(...),
    operator_name: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    payload = load_preview_payload(token)
    if not payload:
        return RedirectResponse(url="/upload", status_code=303)

    with get_connection() as connection:
        error = resolve_supplier_match_with_existing(
            connection,
            payload,
            match_key=match_key,
            supplier_id=supplier_id,
            operator_name=operator_name,
            resolved_status="ambiguous_resolved",
            action_type="supplier_preview_ambiguous_resolved",
        )
        if error:
            return render_upload_preview(request, token, payload, error=error, status_code=400)
        connection.commit()
    save_preview_payload(token, payload)
    return RedirectResponse(url=f"/upload/preview/{token}", status_code=303)


@router.post("/upload/confirm")
async def upload_confirm(request: Request, token: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect

    path = preview_path(token)
    if not path.exists():
        return RedirectResponse(url="/upload", status_code=303)

    payload = json.loads(path.read_text(encoding="utf-8"))
    if preview_has_errors(payload["rows"]):
        return render_upload_preview(
            request,
            token,
            payload,
            error="预览有错误，请修改 Excel 后再导入。",
            status_code=400,
        )

    if supplier_resolution_blocked(payload):
        return render_upload_preview(
            request,
            token,
            payload,
            error="还有未处理的供应商，请先完成供应商匹配。",
            status_code=400,
        )

    form = await request.form()
    selected_updates = parse_selected_updates(form)
    required_choices = parse_required_choices(form)
    if missing_required_choices(payload["rows"], required_choices):
        return render_upload_preview(
            request,
            token,
            payload,
            error="请先为 GTS、OEM、工厂、价格的差异选择保留旧值或使用新值。",
            status_code=400,
        )

    try:
        auto_backup_path = create_auto_backup("full_quotation_import")
    except BackupError as exc:
        return render_upload_preview(
            request,
            token,
            payload,
            error=str(exc),
            status_code=500,
        )

    with get_connection() as connection:
        result = import_preview_rows(
            connection,
            preview_rows=payload["rows"],
            operator_name=payload["operator_name"],
            file_name=payload["file_name"],
            selected_updates=selected_updates,
            required_choices=required_choices,
            auto_backup_path=str(auto_backup_path),
            supplier_resolutions=supplier_resolution_map(payload.get("supplier_matches") or []),
        )
        connection.commit()
    remove_preview_file(path)

    return templates.TemplateResponse(
        request,
        "upload_result.html",
        {
            "request": request,
            "file_name": payload["file_name"],
            "result": result,
            "return_url": "/upload",
            "breadcrumbs": child_breadcrumbs(UPLOAD_CRUMB, "导入结果"),
        },
    )


def preview_path(token: str) -> Path:
    return preview_file_path(UPLOAD_DIR, "preview", token)


def load_preview_payload(token: str) -> dict | None:
    path = preview_path(token)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_preview_payload(token: str, payload: dict) -> None:
    preview_path(token).write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def render_upload_preview(
    request: Request,
    token: str,
    payload: dict,
    *,
    error: str | None = None,
    status_code: int = 200,
):
    supplier_matches = payload.get("supplier_matches") or []
    rows = payload.get("rows") or []
    apply_supplier_resolution_to_rows(rows, supplier_matches)
    with get_connection() as connection:
        suppliers = [supplier_display(supplier) for supplier in list_suppliers(connection, limit=1000)]
    return templates.TemplateResponse(
        request,
        "upload_preview.html",
        {
            "request": request,
            "token": token,
            "operator_name": payload["operator_name"],
            "file_name": payload["file_name"],
            "rows": rows,
            "supplier_matches": supplier_matches,
            "supplier_summary": supplier_matches_summary(supplier_matches, len(rows)),
            "suppliers": suppliers,
            "unresolved_supplier_count": unresolved_supplier_count(supplier_matches),
            "has_warnings": preview_has_warnings(rows),
            "has_errors": preview_has_errors(rows),
            "error": error,
            "return_url": "/upload",
            "breadcrumbs": child_breadcrumbs(UPLOAD_CRUMB, "导入预览"),
        },
        status_code=status_code,
    )


def find_supplier_match(payload: dict, match_key: str) -> dict | None:
    for match in payload.get("supplier_matches") or []:
        if match.get("key") == match_key:
            return match
    return None


def resolve_supplier_match_with_existing(
    connection,
    payload: dict,
    *,
    match_key: str,
    supplier_id: int,
    operator_name: str,
    resolved_status: str,
    action_type: str,
    add_factory_alias: bool = True,
    force_factory_value: bool = False,
) -> str | None:
    match = find_supplier_match(payload, match_key)
    if not match:
        return "找不到供应商匹配项。"
    supplier = get_supplier(connection, supplier_id)
    if not supplier:
        return "选择的供应商不存在。"
    factory = (match.get("factory") or "").strip()
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
    update_supplier_match(
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


def update_supplier_match(
    payload: dict,
    match: dict,
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


def create_supplier_for_preview_match(
    connection,
    payload: dict,
    match: dict,
    *,
    supplier_short_name: str,
    operator_name: str,
    add_factory_alias: bool = True,
    force_factory_value: bool = False,
) -> int:
    factory = (match.get("factory") or "").strip()
    short_name = supplier_short_name.strip()
    supplier_id = create_supplier(
        connection,
        values={
            "supplier_full_name": short_name,
            "supplier_short_name": short_name,
            "aliases_text": factory if factory and add_factory_alias else "",
        },
        operator_name=operator_name,
    )
    supplier = get_supplier(connection, supplier_id)
    factory_value_for_import = (
        supplier_factory_display_value(supplier)
        if force_factory_value or not factory
        else factory
    )
    update_supplier_match(
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
    return supplier_id


def validate_batch_supplier_form(form, pending_matches: list[dict]) -> list[str]:
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


def validate_batch_supplier_database(connection, form, pending_matches: list[dict]) -> list[str]:
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


def supplier_resolution_blocked(payload: dict) -> bool:
    supplier_matches = payload.get("supplier_matches")
    if supplier_matches is None:
        return True
    return any(supplier_match_is_unresolved(match) for match in supplier_matches)


def parse_selected_updates(form_items) -> set[tuple[int, str]]:
    selected = set()
    for key in form_items:
        if not key.startswith("update_product__"):
            continue
        _, row_number, field = key.split("__", 2)
        selected.add((int(row_number), field))
    return selected


def parse_required_choices(form_items) -> dict[tuple[int, str], str]:
    selected = {}
    for key, value in form_items.multi_items():
        if not key.startswith("required_choice__") or not value:
            continue
        _, row_number, field = key.split("__", 2)
        selected[(int(row_number), field)] = str(value)
    return selected


def missing_required_choices(rows: list[dict], choices: dict[tuple[int, str], str]) -> bool:
    for row in rows:
        if row.get("errors"):
            continue
        for choice in row.get("required_choices") or []:
            if choices.get((row["row_number"], choice["field"])) not in {"old", "new"}:
                return True
    return False


def preview_has_warnings(rows: list[dict]) -> bool:
    return any(
        row.get("errors")
        or row.get("warnings")
        or row.get("quotation_warnings")
        or row.get("required_choices")
        or row.get("product_changes")
        for row in rows
    )


def preview_has_errors(rows: list[dict]) -> bool:
    return any(row.get("errors") for row in rows)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
