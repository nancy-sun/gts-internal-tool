from dataclasses import dataclass
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse

from app.auth import (
    get_session_operator_name,
    require_auth,
    require_password_confirmation,
    set_session_operator_name,
)
from app.config import get_settings
from app.database import get_connection
from app.navigation import CUSTOMS_CRUMB, breadcrumbs
from app.services.backup import BackupError, create_auto_backup
from app.services.download_names import attachment_header, dated_download_name
from app.services.hs_codes import (
    build_hs_generate_preview,
    build_hs_upload_preview,
    create_hs_code_workbook,
    parse_hs_code_request_workbook,
    parse_hs_code_upload_workbook,
    save_hs_upload_preview,
)
from app.services.preview_tokens import preview_file_path, remove_preview_file
from app.services.upload_validation import (
    sanitize_upload_filename,
    validate_upload_size,
    validate_workbook_contents,
    validate_xlsx_upload,
)
from app.templating import templates


router = APIRouter()
UPLOAD_DIR = get_settings().upload_dir
EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class HsWorkflow:
    label: str
    href: str
    form_template: str
    preview_template: str
    fallback_file_name: str
    preview_action: str
    finish_action: str


@dataclass(frozen=True)
class SavedWorkbook:
    error: str | None
    file_name: str
    path: Path | None


CUSTOMS_UPLOAD_WORKFLOW = HsWorkflow(
    label="批量上传",
    href="/customs/upload",
    form_template="hs_upload.html",
    preview_template="hs_upload_preview.html",
    fallback_file_name="hs-codes.xlsx",
    preview_action="/customs/upload/preview",
    finish_action="/customs/upload/confirm",
)
CUSTOMS_EXPORT_WORKFLOW = HsWorkflow(
    label="导出报告",
    href="/customs/export",
    form_template="hs_generate.html",
    preview_template="hs_generate_preview.html",
    fallback_file_name="hs-code-request.xlsx",
    preview_action="/customs/export/preview",
    finish_action="/customs/export/download",
)


@router.get("/hs-codes")
def hs_home(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return RedirectResponse(url="/customs", status_code=303)


@router.get("/customs")
def customs_home(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "customs.html",
        {
            "request": request,
            "breadcrumbs": breadcrumbs(CUSTOMS_CRUMB),
            "return_url": "/",
        },
    )


@router.get("/hs-codes/upload")
def hs_upload_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return RedirectResponse(url="/customs/upload", status_code=303)


@router.get("/customs/upload")
def customs_upload_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return hs_form_response(request, CUSTOMS_UPLOAD_WORKFLOW)


@router.post("/hs-codes/upload/preview")
@router.post("/customs/upload/preview")
async def hs_upload_preview(
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
        return hs_form_response(
            request,
            CUSTOMS_UPLOAD_WORKFLOW,
            error=error,
            operator_name=operator_name,
            status_code=400,
        )

    workbook_result = await save_uploaded_workbook(excel_file, CUSTOMS_UPLOAD_WORKFLOW)
    if workbook_result.error or workbook_result.path is None:
        return hs_form_response(
            request,
            CUSTOMS_UPLOAD_WORKFLOW,
            error=workbook_result.error or "Excel 上传失败。",
            operator_name=operator_name,
            status_code=400,
        )

    parsed_rows = parse_hs_code_upload_workbook(workbook_result.path)
    with get_connection() as connection:
        preview_rows = build_hs_upload_preview(connection, parsed_rows)
    add_customs_master_data_warnings(preview_rows)

    token = uuid4().hex
    payload = build_preview_payload(
        operator_name=operator_name,
        file_name=workbook_result.file_name,
        rows=preview_rows,
    )
    hs_upload_preview_path(token).write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return render_hs_preview(
        request,
        token,
        payload,
        workflow=CUSTOMS_UPLOAD_WORKFLOW,
        current_label="上传预览",
        include_error_flag=True,
    )


@router.post("/hs-codes/upload/confirm")
@router.post("/customs/upload/confirm")
async def hs_upload_confirm(
    request: Request,
    token: str = Form(...),
    confirm_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    path = hs_upload_preview_path(token)
    if not path.exists():
        return RedirectResponse(url=CUSTOMS_UPLOAD_WORKFLOW.href, status_code=303)

    payload = read_preview_payload(path)
    password_error = require_password_confirmation(request, confirm_password)
    if password_error:
        return render_hs_preview(
            request,
            token,
            payload,
            workflow=CUSTOMS_UPLOAD_WORKFLOW,
            current_label="上传预览",
            include_error_flag=True,
            error=password_error,
            status_code=400,
        )
    try:
        auto_backup_path = create_auto_backup("hs_code_update")
    except BackupError as exc:
        context = {
            "request": request,
            "token": token,
            "operator_name": payload["operator_name"],
            "file_name": payload["file_name"],
            "rows": payload["rows"],
            "has_errors": preview_has_errors(payload["rows"]),
            "error": str(exc),
            "breadcrumbs": hs_child_page_breadcrumbs(
                CUSTOMS_UPLOAD_WORKFLOW,
                "上传预览",
            ),
            "return_url": CUSTOMS_UPLOAD_WORKFLOW.href,
        }
        return templates.TemplateResponse(
            request,
            CUSTOMS_UPLOAD_WORKFLOW.preview_template,
            context,
            status_code=500,
        )

    with get_connection() as connection:
        result = save_hs_upload_preview(
            connection,
            preview_rows=payload["rows"],
            operator_name=payload["operator_name"],
            file_name=payload["file_name"],
            auto_backup_path=str(auto_backup_path),
        )
        connection.commit()
    remove_preview_file(path)

    return templates.TemplateResponse(
        request,
        "hs_upload_result.html",
        {
            "request": request,
            "file_name": payload["file_name"],
            "result": result,
            "breadcrumbs": hs_child_page_breadcrumbs(
                CUSTOMS_UPLOAD_WORKFLOW,
                "上传结果",
            ),
            "return_url": CUSTOMS_UPLOAD_WORKFLOW.href,
        },
    )


@router.get("/hs-codes/generate")
def hs_generate_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return RedirectResponse(url="/customs/export", status_code=303)


@router.get("/hs-codes/report")
def hs_report_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return RedirectResponse(url="/customs/export", status_code=303)


@router.get("/customs/export")
def customs_export_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return hs_form_response(request, CUSTOMS_EXPORT_WORKFLOW)


@router.post("/hs-codes/generate/preview")
@router.post("/customs/export/preview")
async def hs_generate_preview(
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
        return hs_form_response(
            request,
            CUSTOMS_EXPORT_WORKFLOW,
            error=error,
            operator_name=operator_name,
            status_code=400,
        )

    workbook_result = await save_uploaded_workbook(excel_file, CUSTOMS_EXPORT_WORKFLOW)
    if workbook_result.error or workbook_result.path is None:
        return hs_form_response(
            request,
            CUSTOMS_EXPORT_WORKFLOW,
            error=workbook_result.error or "Excel 上传失败。",
            operator_name=operator_name,
            status_code=400,
        )

    parsed_rows = parse_hs_code_request_workbook(workbook_result.path)
    with get_connection() as connection:
        preview_rows = build_hs_generate_preview(connection, parsed_rows)

    token = uuid4().hex
    payload = build_preview_payload(
        operator_name=operator_name,
        file_name=workbook_result.file_name,
        rows=preview_rows,
    )
    hs_generate_preview_path(token).write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return render_hs_preview(
        request,
        token,
        payload,
        workflow=CUSTOMS_EXPORT_WORKFLOW,
        current_label="生成预览",
    )


@router.post("/hs-codes/generate/download")
@router.post("/customs/export/download")
async def hs_generate_download(request: Request, token: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect

    path = hs_generate_preview_path(token)
    if not path.exists():
        return RedirectResponse(url=CUSTOMS_EXPORT_WORKFLOW.href, status_code=303)

    payload = read_preview_payload(path)
    with get_connection() as connection:
        stream, _ = create_hs_code_workbook(
            connection,
            preview_rows=payload["rows"],
            operator_name=payload["operator_name"],
            file_name=payload["file_name"],
        )
        connection.commit()
    remove_preview_file(path)

    return StreamingResponse(
        stream,
        media_type=EXCEL_MEDIA_TYPE,
        headers={
            "Content-Disposition": attachment_header(
                dated_download_name(payload["operator_name"], "hs")
            )
        },
    )


def hs_form_response(
    request: Request,
    workflow: HsWorkflow,
    *,
    error: str | None = None,
    operator_name: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        workflow.form_template,
        {
            "request": request,
            "error": error,
            "operator_name": (
                get_session_operator_name(request)
                if operator_name is None
                else operator_name
            ),
            "workflow": workflow,
            "breadcrumbs": hs_child_page_breadcrumbs(workflow, ""),
            "return_url": "/customs",
        },
        status_code=status_code,
    )


def render_hs_preview(
    request: Request,
    token: str,
    payload: dict,
    *,
    workflow: HsWorkflow,
    current_label: str,
    include_error_flag: bool = False,
    error: str | None = None,
    status_code: int = 200,
):
    context = {
        "request": request,
        "token": token,
        "operator_name": payload["operator_name"],
        "file_name": payload["file_name"],
        "rows": payload["rows"],
        "workflow": workflow,
        "breadcrumbs": hs_child_page_breadcrumbs(workflow, current_label),
        "return_url": workflow.href,
    }
    if include_error_flag:
        context["has_errors"] = preview_has_errors(payload["rows"])
    if error:
        context["error"] = error
    return templates.TemplateResponse(
        request,
        workflow.preview_template,
        context,
        status_code=status_code,
    )


async def save_uploaded_workbook(
    excel_file: UploadFile,
    workflow: HsWorkflow,
) -> SavedWorkbook:
    contents = await excel_file.read()
    settings = get_settings()
    size_error = validate_upload_size(
        contents,
        max_upload_size_bytes=settings.max_upload_size_bytes,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
    if size_error:
        return SavedWorkbook(error=size_error, file_name="", path=None)
    workbook_error = validate_workbook_contents(contents)
    if workbook_error:
        return SavedWorkbook(error=workbook_error, file_name="", path=None)

    token = uuid4().hex
    safe_name = sanitize_upload_filename(
        excel_file.filename,
        default=workflow.fallback_file_name,
    )
    workbook_path = UPLOAD_DIR / f"{token}_{safe_name}"
    workbook_path.write_bytes(contents)
    return SavedWorkbook(error=None, file_name=safe_name, path=workbook_path)


def build_preview_payload(
    *,
    operator_name: str,
    file_name: str,
    rows: list[dict],
) -> dict:
    return {
        "operator_name": operator_name.strip(),
        "file_name": file_name,
        "rows": rows,
    }


def read_preview_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def hs_child_page_breadcrumbs(
    workflow: HsWorkflow,
    current_label: str,
) -> list[dict]:
    return [
        CUSTOMS_CRUMB,
        {"label": workflow.label, "href": workflow.href},
        *([{"label": current_label, "href": ""}] if current_label else []),
    ]


def hs_upload_preview_path(token: str) -> Path:
    return preview_file_path(UPLOAD_DIR, "hs_upload_preview", token)


def hs_generate_preview_path(token: str) -> Path:
    return preview_file_path(UPLOAD_DIR, "hs_generate_preview", token)


def preview_has_errors(rows: list[dict]) -> bool:
    return any(row.get("errors") for row in rows)


def add_customs_master_data_warnings(rows: list[dict]) -> None:
    warning = "仅更新产品旧 HS Code；缺少报关品名、第一单位、第一单位来源时不会创建报关资料库记录。"
    for row in rows:
        warnings = row.setdefault("warnings", [])
        if warning not in warnings:
            warnings.append(warning)
