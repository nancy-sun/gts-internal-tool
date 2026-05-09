import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app.config import BASE_DIR, get_settings
from app.database import get_connection
from app.services.excel_parser import iter_full_quotation_workbook_rows
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

    preview_payload = {
        "operator_name": operator_name.strip(),
        "file_name": safe_name,
        "workbook_path": str(workbook_path),
        "rows": [],
    }
    preview_path(token).write_text(
        json.dumps(preview_payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return templates.TemplateResponse(
        "upload_preview_loading.html",
        {
            "request": request,
            "token": token,
            "operator_name": operator_name.strip(),
            "file_name": safe_name,
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
        preview_rows = []
        workbook_path = Path(payload["workbook_path"])
        try:
            with get_connection() as connection:
                for parsed_row in iter_full_quotation_workbook_rows(workbook_path):
                    yield sse_event("loading", {"row_number": parsed_row.row_number})
                    preview_row = build_import_preview(connection, [parsed_row])[0]
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
        except Exception as exc:
            yield sse_event("preview_error", {"message": str(exc)})

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
            },
            status_code=400,
        )

    form = await request.form()
    selected_updates = parse_selected_updates(form)
    selected_quotation_changes = parse_selected_quotation_changes(form)

    with get_connection() as connection:
        result = import_preview_rows(
            connection,
            preview_rows=payload["rows"],
            operator_name=payload["operator_name"],
            file_name=payload["file_name"],
            selected_updates=selected_updates,
            selected_quotation_changes=selected_quotation_changes,
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


def parse_selected_quotation_changes(form_items) -> set[int]:
    selected = set()
    for key in form_items:
        if not key.startswith("apply_quotation_change__"):
            continue
        _, row_number = key.split("__", 1)
        selected.add(int(row_number))
    return selected


def preview_has_warnings(rows: list[dict]) -> bool:
    return any(
        row.get("errors")
        or row.get("warnings")
        or row.get("quotation_warnings")
        or row.get("product_changes")
        for row in rows
    )


def preview_has_errors(rows: list[dict]) -> bool:
    return any(row.get("errors") for row in rows)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
