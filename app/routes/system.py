from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.auth import require_auth
from app.navigation import MAINTENANCE_CRUMB, breadcrumbs
from app.services.system_status import build_system_status
from app.templating import templates


router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/robots.txt")
def robots_txt():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@router.get("/maintenance")
def maintenance_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    return templates.TemplateResponse(
        request,
        "maintenance.html",
        {
            "request": request,
            "status": build_system_status(),
            "breadcrumbs": breadcrumbs(MAINTENANCE_CRUMB),
        },
    )
