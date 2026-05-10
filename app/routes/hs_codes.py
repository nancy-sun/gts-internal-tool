import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse

from app.auth import require_auth
from app.config import BASE_DIR, get_settings
from app.database import get_connection
from app.navigation import HS_CRUMB, breadcrumbs, child_breadcrumbs
from app.services.hs_codes import (
    build_hs_generate_preview,
    build_hs_upload_preview,
    create_hs_code_workbook,
    parse_hs_code_request_workbook,
    parse_hs_code_upload_workbook,
    save_hs_upload_preview,
)
from app.services.preview_tokens import preview_file_path
from app.services.upload_validation import validate_upload_size, validate_xlsx_upload
from app.templating import templates


router = APIRouter()
UPLOAD_DIR = BASE_DIR / "uploads"


@router.get("/hs-codes")
def hs_home(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "hs_codes.html",
        {
            "request": request,
            "breadcrumbs": breadcrumbs(HS_CRUMB),
        },
    )


@router.get("/hs-codes/upload")
def hs_upload_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "hs_upload.html",
        {
            "request": request,
            "error": None,
            "breadcrumbs": child_breadcrumbs(HS_CRUMB, "上传 HS Code"),
            "return_url": "/hs-codes",
        },
    )


@router.post("/hs-codes/upload/preview")
async def hs_upload_preview(
    request: Request,
    operator_name: str = Form(...),
    excel_file: UploadFile = File(...),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    error = validate_xlsx_upload(excel_file, operator_name)
    if error:
        return hs_upload_error_response(request, error)

    contents = await excel_file.read()
    settings = get_settings()
    size_error = validate_upload_size(
        contents,
        max_upload_size_bytes=settings.max_upload_size_bytes,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
    if size_error:
        return hs_upload_error_response(request, size_error)

    token = uuid4().hex
    safe_name = Path(excel_file.filename or "hs-codes.xlsx").name
    workbook_path = UPLOAD_DIR / f"{token}_{safe_name}"
    workbook_path.write_bytes(contents)
    parsed_rows = parse_hs_code_upload_workbook(workbook_path)
    with get_connection() as connection:
        preview_rows = build_hs_upload_preview(connection, parsed_rows)

    payload = {
        "operator_name": operator_name.strip(),
        "file_name": safe_name,
        "rows": preview_rows,
    }
    hs_upload_preview_path(token).write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return templates.TemplateResponse(
        request,
        "hs_upload_preview.html",
        {
            "request": request,
            "token": token,
            "operator_name": operator_name.strip(),
            "file_name": safe_name,
            "rows": preview_rows,
            "has_errors": preview_has_errors(preview_rows),
            "breadcrumbs": [
                HS_CRUMB,
                {"label": "上传 HS Code", "href": "/hs-codes/upload"},
                {"label": "上传预览", "href": ""},
            ],
            "return_url": "/hs-codes/upload",
        },
    )


@router.post("/hs-codes/upload/confirm")
async def hs_upload_confirm(request: Request, token: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect

    path = hs_upload_preview_path(token)
    if not path.exists():
        return RedirectResponse(url="/hs-codes/upload", status_code=303)

    payload = json.loads(path.read_text(encoding="utf-8"))
    with get_connection() as connection:
        result = save_hs_upload_preview(
            connection,
            preview_rows=payload["rows"],
            operator_name=payload["operator_name"],
            file_name=payload["file_name"],
        )
        connection.commit()

    return templates.TemplateResponse(
        request,
        "hs_upload_result.html",
        {
            "request": request,
            "file_name": payload["file_name"],
            "result": result,
            "breadcrumbs": [
                HS_CRUMB,
                {"label": "上传 HS Code", "href": "/hs-codes/upload"},
                {"label": "上传结果", "href": ""},
            ],
            "return_url": "/hs-codes/upload",
        },
    )


@router.get("/hs-codes/generate")
def hs_generate_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "hs_generate.html",
        {
            "request": request,
            "error": None,
            "breadcrumbs": child_breadcrumbs(HS_CRUMB, "生成 HS Code"),
            "return_url": "/hs-codes",
        },
    )


@router.post("/hs-codes/generate/preview")
async def hs_generate_preview(
    request: Request,
    operator_name: str = Form(...),
    excel_file: UploadFile = File(...),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    error = validate_xlsx_upload(excel_file, operator_name)
    if error:
        return hs_generate_error_response(request, error)

    contents = await excel_file.read()
    settings = get_settings()
    size_error = validate_upload_size(
        contents,
        max_upload_size_bytes=settings.max_upload_size_bytes,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
    if size_error:
        return hs_generate_error_response(request, size_error)

    token = uuid4().hex
    safe_name = Path(excel_file.filename or "hs-code-request.xlsx").name
    workbook_path = UPLOAD_DIR / f"{token}_{safe_name}"
    workbook_path.write_bytes(contents)
    parsed_rows = parse_hs_code_request_workbook(workbook_path)
    with get_connection() as connection:
        preview_rows = build_hs_generate_preview(connection, parsed_rows)

    payload = {
        "operator_name": operator_name.strip(),
        "file_name": safe_name,
        "rows": preview_rows,
    }
    hs_generate_preview_path(token).write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return templates.TemplateResponse(
        request,
        "hs_generate_preview.html",
        {
            "request": request,
            "token": token,
            "operator_name": operator_name.strip(),
            "file_name": safe_name,
            "rows": preview_rows,
            "breadcrumbs": [
                HS_CRUMB,
                {"label": "生成 HS Code", "href": "/hs-codes/generate"},
                {"label": "生成预览", "href": ""},
            ],
            "return_url": "/hs-codes/generate",
        },
    )


@router.post("/hs-codes/generate/download")
async def hs_generate_download(request: Request, token: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect

    path = hs_generate_preview_path(token)
    if not path.exists():
        return RedirectResponse(url="/hs-codes/generate", status_code=303)

    payload = json.loads(path.read_text(encoding="utf-8"))
    with get_connection() as connection:
        stream, _ = create_hs_code_workbook(
            connection,
            preview_rows=payload["rows"],
            operator_name=payload["operator_name"],
            file_name=payload["file_name"],
        )
        connection.commit()

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="hs_codes.xlsx"'},
    )


def hs_upload_error_response(request: Request, error: str):
    return templates.TemplateResponse(
        request,
        "hs_upload.html",
        {
            "request": request,
            "error": error,
            "breadcrumbs": child_breadcrumbs(HS_CRUMB, "上传 HS Code"),
            "return_url": "/hs-codes",
        },
        status_code=400,
    )


def hs_generate_error_response(request: Request, error: str):
    return templates.TemplateResponse(
        request,
        "hs_generate.html",
        {
            "request": request,
            "error": error,
            "breadcrumbs": child_breadcrumbs(HS_CRUMB, "生成 HS Code"),
            "return_url": "/hs-codes",
        },
        status_code=400,
    )


def hs_upload_preview_path(token: str) -> Path:
    return preview_file_path(UPLOAD_DIR, "hs_upload_preview", token)


def hs_generate_preview_path(token: str) -> Path:
    return preview_file_path(UPLOAD_DIR, "hs_generate_preview", token)


def preview_has_errors(rows: list[dict]) -> bool:
    return any(row.get("errors") for row in rows)
