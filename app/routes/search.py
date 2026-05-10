from fastapi import APIRouter, Request

from app.auth import require_auth
from app.database import get_connection
from app.navigation import SEARCH_CRUMB, breadcrumbs
from app.services.search import SEARCH_FIELDS, search_catalogue
from app.templating import templates


router = APIRouter()


@router.get("/search")
def search_page(request: Request, field: str = "gts_no", q: str = ""):
    redirect = require_auth(request)
    if redirect:
        return redirect

    selected_field = field if field in SEARCH_FIELDS else "gts_no"
    rows = []
    warnings = []
    if q.strip():
        with get_connection() as connection:
            rows, warnings = search_catalogue(
                connection,
                field=selected_field,
                query=q,
            )

    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "request": request,
            "field": selected_field,
            "query": q,
            "rows": rows,
            "warnings": warnings,
            "breadcrumbs": breadcrumbs(SEARCH_CRUMB),
        },
    )
