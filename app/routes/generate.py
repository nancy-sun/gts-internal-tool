import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse

from app.auth import get_session_operator_name, require_auth, set_session_operator_name
from app.config import BASE_DIR, get_settings
from app.database import get_connection
from app.navigation import GENERATE_CRUMB, breadcrumbs, child_breadcrumbs
from app.services.download_names import attachment_header, dated_download_name
from app.services.quotation_generation import (
    build_generation_preview,
    create_generated_workbook,
    request_rows_have_any_identifier,
)
from app.services.preview_tokens import preview_file_path, remove_preview_file
from app.services.request_parser import parse_request_workbook
from app.services.upload_validation import validate_upload_size, validate_xlsx_upload
from app.templating import templates


router = APIRouter()
UPLOAD_DIR = BASE_DIR / "uploads"


@router.get("/generate")
def generate_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "generate.html",
        {
            "request": request,
            "error": None,
            "operator_name": get_session_operator_name(request),
            "breadcrumbs": breadcrumbs(GENERATE_CRUMB),
        },
    )


@router.post("/generate/preview")
async def generate_preview(
    request: Request,
    operator_name: str = Form(...),
    request_file: UploadFile = File(...),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    error = validate_xlsx_upload(request_file, operator_name)
    if error:
        return templates.TemplateResponse(
            request,
            "generate.html",
            {
                "request": request,
                "error": error,
                "operator_name": operator_name,
                "breadcrumbs": breadcrumbs(GENERATE_CRUMB),
            },
            status_code=400,
        )

    contents = await request_file.read()
    settings = get_settings()
    size_error = validate_upload_size(
        contents,
        max_upload_size_bytes=settings.max_upload_size_bytes,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
    if size_error:
        return templates.TemplateResponse(
            request,
            "generate.html",
            {
                "request": request,
                "error": size_error,
                "operator_name": operator_name,
                "breadcrumbs": breadcrumbs(GENERATE_CRUMB),
            },
            status_code=400,
        )

    token = uuid4().hex
    safe_name = Path(request_file.filename or "request.xlsx").name
    workbook_path = UPLOAD_DIR / f"{token}_{safe_name}"
    workbook_path.write_bytes(contents)
    parsed_rows = parse_request_workbook(workbook_path)
    if not request_rows_have_any_identifier(parsed_rows):
        return templates.TemplateResponse(
            request,
            "generate.html",
            {
                "request": request,
                "error": "需求文件中没有可识别的 GTS 或 OEM，请修改后重新上传。",
                "operator_name": operator_name,
                "breadcrumbs": breadcrumbs(GENERATE_CRUMB),
            },
            status_code=400,
        )

    with get_connection() as connection:
        preview_rows = build_generation_preview(connection, parsed_rows)

    payload = {
        "operator_name": operator_name,
        "file_name": safe_name,
        "rows": preview_rows,
    }
    preview_path(token).write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return templates.TemplateResponse(
        request,
        "generate_preview.html",
        {
            "request": request,
            "token": token,
            "operator_name": operator_name,
            "file_name": safe_name,
            "rows": preview_rows,
            "return_url": "/generate",
            "breadcrumbs": child_breadcrumbs(GENERATE_CRUMB, "生成预览"),
        },
    )


@router.post("/generate/download")
async def generate_download(request: Request, token: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect

    path = preview_path(token)
    if not path.exists():
        return RedirectResponse(url="/generate", status_code=303)

    form = await request.form()
    selected_candidate_ids = parse_selected_candidates(form)
    payload = json.loads(path.read_text(encoding="utf-8"))
    with get_connection() as connection:
        stream, _ = create_generated_workbook(
            connection,
            preview_rows=payload["rows"],
            selected_candidate_ids=selected_candidate_ids,
            operator_name=payload["operator_name"],
            request_file_name=payload["file_name"],
        )
        connection.commit()
    remove_preview_file(path)

    download_name = dated_download_name(payload["operator_name"], "询价")
    headers = {"Content-Disposition": attachment_header(download_name)}
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


def preview_path(token: str) -> Path:
    return preview_file_path(UPLOAD_DIR, "generate_preview", token)


def parse_selected_candidates(form_items) -> dict[int, int]:
    selected = {}
    included_rows = {
        int(key.split("__", 1)[1])
        for key, value in form_items.multi_items()
        if key.startswith("include__") and value
    }
    for key, value in form_items.multi_items():
        if not key.startswith("candidate__") or not value:
            continue
        row_number = int(key.split("__", 1)[1])
        if row_number in included_rows:
            selected[row_number] = int(value)
    return selected
