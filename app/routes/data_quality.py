from fastapi import APIRouter, Request

from app.auth import require_auth
from app.database import get_connection
from app.navigation import DATA_QUALITY_CRUMB, breadcrumbs
from app.services.data_quality import build_data_quality_report
from app.templating import templates


router = APIRouter()


@router.get("/data-quality")
def data_quality_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        report = build_data_quality_report(connection)

    return templates.TemplateResponse(
        request,
        "data_quality.html",
        {
            "request": request,
            "report": report,
            "breadcrumbs": breadcrumbs(DATA_QUALITY_CRUMB),
        },
    )
