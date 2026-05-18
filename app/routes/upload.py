import json
import logging
from pathlib import Path
from uuid import uuid4

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
from app.services.preview_tokens import remove_preview_file
from app.services.suppliers import (
    list_suppliers,
)
from app.services.upload_preview_state import (
    find_supplier_match,
    load_preview_payload as load_preview_payload_from_state,
    preview_path as preview_path_from_state,
    save_preview_payload as save_preview_payload_to_state,
    validate_all_suppliers_resolved,
)
from app.services.upload_supplier_matching import (
    build_supplier_matches,
    supplier_display,
    supplier_matches_summary,
    unresolved_supplier_count,
)
from app.services.upload_supplier_resolution import (
    apply_supplier_resolution_to_rows,
    create_preview_supplier,
    link_preview_supplier,
    resolve_batch_preview_suppliers,
    resolve_preview_ambiguous_supplier,
    supplier_resolution_map,
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
    save_preview_payload(token, preview_payload)

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
        payload = load_preview_payload(token)
        if not payload:
            yield sse_event("preview_error", {"message": "找不到预览文件。"})
            return
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
            save_preview_payload(token, payload)
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
        error = link_preview_supplier(
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

    with get_connection() as connection:
        errors = resolve_batch_preview_suppliers(
            connection,
            payload,
            form,
            operator_name=operator_name,
        )
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

    with get_connection() as connection:
        _, error = create_preview_supplier(
            connection,
            payload,
            match_key=match_key,
            supplier_full_name=supplier_full_name,
            supplier_short_name=supplier_short_name,
            aliases_text=aliases_text,
            operator_name=operator_name,
        )
        if error:
            return render_upload_preview(
                request,
                token,
                payload,
                error=error,
                status_code=400,
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
        error = resolve_preview_ambiguous_supplier(
            connection,
            payload,
            match_key=match_key,
            supplier_id=supplier_id,
            operator_name=operator_name,
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

    payload = load_preview_payload(token)
    if not payload:
        return RedirectResponse(url="/upload", status_code=303)
    if preview_has_errors(payload["rows"]):
        return render_upload_preview(
            request,
            token,
            payload,
            error="预览有错误，请修改 Excel 后再导入。",
            status_code=400,
        )

    supplier_errors = validate_all_suppliers_resolved(payload)
    if supplier_errors:
        return render_upload_preview(
            request,
            token,
            payload,
            error="；".join(supplier_errors),
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
    return preview_path_from_state(token, UPLOAD_DIR)


def load_preview_payload(token: str) -> dict | None:
    return load_preview_payload_from_state(token, UPLOAD_DIR)


def save_preview_payload(token: str, payload: dict) -> None:
    save_preview_payload_to_state(token, payload, UPLOAD_DIR)


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
