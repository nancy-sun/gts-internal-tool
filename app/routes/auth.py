from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import SESSION_AUTH_KEY, set_session_operator_name
from app.config import get_settings
from app.templating import templates


router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    if request.session.get(SESSION_AUTH_KEY):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "error": None, "operator_name": ""},
    )


@router.post("/login")
def login(
    request: Request,
    access_code: str = Form(...),
    operator_name: str = Form(""),
):
    settings = get_settings()
    if access_code == settings.shared_access_code:
        request.session[SESSION_AUTH_KEY] = True
        set_session_operator_name(request, operator_name)
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "error": "访问码不正确。",
            "operator_name": operator_name.strip(),
        },
        status_code=401,
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
