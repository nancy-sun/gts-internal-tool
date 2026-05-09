import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app.config import BASE_DIR, get_settings
from app.database import get_connection
from app.services.quotation_generation import (
    build_generation_preview,
    create_generated_workbook,
)
from app.services.request_parser import parse_request_workbook


router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
UPLOAD_DIR = BASE_DIR / "uploads"


@router.get("/generate")
def generate_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        "generate.html",
        {"request": request, "error": None},
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

    error = validate_request_upload(request_file, operator_name)
    if error:
        return templates.TemplateResponse(
            "generate.html",
            {"request": request, "error": error},
            status_code=400,
        )

    contents = await request_file.read()
    settings = get_settings()
    if len(contents) > settings.max_upload_size_bytes:
        return templates.TemplateResponse(
            "generate.html",
            {
                "request": request,
                "error": f"Upload file is larger than {settings.max_upload_size_mb} MB.",
            },
            status_code=400,
        )

    token = uuid4().hex
    safe_name = Path(request_file.filename or "request.xlsx").name
    workbook_path = UPLOAD_DIR / f"{token}_{safe_name}"
    workbook_path.write_bytes(contents)
    parsed_rows = parse_request_workbook(workbook_path)

    with get_connection() as connection:
        preview_rows = build_generation_preview(connection, parsed_rows)

    payload = {
        "operator_name": operator_name.strip(),
        "file_name": safe_name,
        "rows": preview_rows,
    }
    preview_path(token).write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return templates.TemplateResponse(
        "generate_preview.html",
        {
            "request": request,
            "token": token,
            "operator_name": operator_name.strip(),
            "file_name": safe_name,
            "rows": preview_rows,
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
        stream, generated_count = create_generated_workbook(
            connection,
            preview_rows=payload["rows"],
            selected_candidate_ids=selected_candidate_ids,
            operator_name=payload["operator_name"],
            request_file_name=payload["file_name"],
        )
        connection.commit()

    download_name = "internal_quotation.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


def validate_request_upload(request_file: UploadFile, operator_name: str) -> str | None:
    if not operator_name.strip():
        return "Operator name is required."
    filename = request_file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        return "Only .xlsx files are allowed."
    return None


def preview_path(token: str) -> Path:
    return UPLOAD_DIR / f"generate_preview_{token}.json"


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
