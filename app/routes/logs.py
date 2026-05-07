from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app.config import BASE_DIR
from app.database import get_connection
from app.services.operation_logging import list_operation_logs


router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@router.get("/logs")
def logs_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        rows = list_operation_logs(connection)

    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "rows": rows,
        },
    )
