import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app.config import BASE_DIR, get_settings
from app.database import get_connection
from app.services.excel_parser import parse_full_quotation_workbook
from app.services.import_full_quotation import build_import_preview, import_preview_rows


router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
UPLOAD_DIR = BASE_DIR / "uploads"


@router.get("/upload")
def upload_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, "error": None},
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

    error = validate_upload(excel_file, operator_name)
    if error:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": error},
            status_code=400,
        )

    contents = await excel_file.read()
    settings = get_settings()
    if len(contents) > settings.max_upload_size_bytes:
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "error": f"Upload file is larger than {settings.max_upload_size_mb} MB.",
            },
            status_code=400,
        )

    token = uuid4().hex
    safe_name = Path(excel_file.filename or "quotation.xlsx").name
    workbook_path = UPLOAD_DIR / f"{token}_{safe_name}"
    workbook_path.write_bytes(contents)

    parsed_rows = parse_full_quotation_workbook(workbook_path)
    with get_connection() as connection:
        preview_rows = build_import_preview(connection, parsed_rows)

    preview_payload = {
        "operator_name": operator_name.strip(),
        "file_name": safe_name,
        "workbook_path": str(workbook_path),
        "rows": preview_rows,
    }
    preview_path(token).write_text(
        json.dumps(preview_payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return templates.TemplateResponse(
        "upload_preview.html",
        {
            "request": request,
            "token": token,
            "operator_name": operator_name.strip(),
            "file_name": safe_name,
            "rows": preview_rows,
        },
    )


@router.post("/upload/confirm")
async def upload_confirm(request: Request, token: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect

    path = preview_path(token)
    if not path.exists():
        return RedirectResponse(url="/upload", status_code=303)

    payload = json.loads(path.read_text(encoding="utf-8"))
    form = await request.form()
    selected_updates = parse_selected_updates(form)

    with get_connection() as connection:
        result = import_preview_rows(
            connection,
            preview_rows=payload["rows"],
            operator_name=payload["operator_name"],
            file_name=payload["file_name"],
            selected_updates=selected_updates,
        )
        connection.commit()

    return templates.TemplateResponse(
        "upload_result.html",
        {
            "request": request,
            "file_name": payload["file_name"],
            "result": result,
        },
    )


def validate_upload(excel_file: UploadFile, operator_name: str) -> str | None:
    if not operator_name.strip():
        return "Operator name is required."
    filename = excel_file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        return "Only .xlsx files are allowed."
    return None


def preview_path(token: str) -> Path:
    return UPLOAD_DIR / f"preview_{token}.json"


def parse_selected_updates(form_items) -> set[tuple[int, str]]:
    selected = set()
    for key in form_items:
        if not key.startswith("update_product__"):
            continue
        _, row_number, field = key.split("__", 2)
        selected.add((int(row_number), field))
    return selected
