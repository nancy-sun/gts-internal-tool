from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app.config import BASE_DIR


router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@router.get("/")
def home(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("home.html", {"request": request})


@router.get("/upload")
def upload_placeholder(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        "placeholder.html",
        {
            "request": request,
            "title": "Upload Full Quotation List",
            "message": "This page will be implemented in Phase 3.",
        },
    )


@router.get("/generate")
def generate_placeholder(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        "placeholder.html",
        {
            "request": request,
            "title": "Generate Quotation",
            "message": "This page will be implemented in Phase 4.",
        },
    )


@router.get("/search")
def search_placeholder(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        "placeholder.html",
        {
            "request": request,
            "title": "Search Database",
            "message": "This page will be implemented in Phase 2.",
        },
    )


@router.get("/logs")
def logs_placeholder(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        "placeholder.html",
        {
            "request": request,
            "title": "Operation Logs",
            "message": "This page will be implemented in Phase 5.",
        },
    )
