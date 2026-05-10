from fastapi import APIRouter, Request

from app.auth import require_auth
from app.database import get_connection
from app.navigation import LOGS_CRUMB, breadcrumbs
from app.services.operation_logging import list_operation_logs
from app.templating import templates


router = APIRouter()


@router.get("/logs")
def logs_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        rows = list_operation_logs(connection)

    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "request": request,
            "rows": rows,
            "breadcrumbs": breadcrumbs(LOGS_CRUMB),
        },
    )
