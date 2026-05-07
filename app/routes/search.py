from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app.config import BASE_DIR
from app.database import get_connection
from app.services.search import SEARCH_FIELDS, search_catalogue


router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


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
        "search.html",
        {
            "request": request,
            "field": selected_field,
            "query": q,
            "rows": rows,
            "warnings": warnings,
        },
    )
