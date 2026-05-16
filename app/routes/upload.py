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
from app.services.preview_tokens import preview_file_path, remove_preview_file
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
            for parsed_row in parsed_rows:
                yield sse_event("loading", {"row_number": parsed_row.row_number})
                preview_row = build_import_preview_row(lookup_context, parsed_row)
                preview_rows.append(preview_row)
                yield sse_event("row", preview_row)

            payload["rows"] = preview_rows
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
                },
            )
        except Exception:
            logger.exception("Upload preview failed for token %s", token)
            yield sse_event("preview_error", {"message": UPLOAD_PREVIEW_ERROR})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
        return templates.TemplateResponse(
            request,
            "upload_preview.html",
            {
                "request": request,
                "token": token,
                "operator_name": payload["operator_name"],
                "file_name": payload["file_name"],
                "rows": payload["rows"],
                "has_warnings": preview_has_warnings(payload["rows"]),
                "has_errors": True,
                "error": "预览有错误，请修改 Excel 后再导入。",
                "return_url": "/upload",
                "breadcrumbs": child_breadcrumbs(UPLOAD_CRUMB, "导入预览"),
            },
            status_code=400,
        )

    form = await request.form()
    selected_updates = parse_selected_updates(form)
    required_choices = parse_required_choices(form)
    if missing_required_choices(payload["rows"], required_choices):
        return templates.TemplateResponse(
            request,
            "upload_preview.html",
            {
                "request": request,
                "token": token,
                "operator_name": payload["operator_name"],
                "file_name": payload["file_name"],
                "rows": payload["rows"],
                "has_warnings": preview_has_warnings(payload["rows"]),
                "has_errors": False,
                "error": "请先为 GTS、OEM、工厂、价格的差异选择保留旧值或使用新值。",
                "return_url": "/upload",
                "breadcrumbs": child_breadcrumbs(UPLOAD_CRUMB, "导入预览"),
            },
            status_code=400,
        )

    try:
        auto_backup_path = create_auto_backup("full_quotation_import")
    except BackupError as exc:
        return templates.TemplateResponse(
            request,
            "upload_preview.html",
            {
                "request": request,
                "token": token,
                "operator_name": payload["operator_name"],
                "file_name": payload["file_name"],
                "rows": payload["rows"],
                "has_warnings": preview_has_warnings(payload["rows"]),
                "has_errors": False,
                "error": str(exc),
                "return_url": "/upload",
                "breadcrumbs": child_breadcrumbs(UPLOAD_CRUMB, "导入预览"),
            },
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
