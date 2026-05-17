from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import require_auth, set_session_operator_name


router = APIRouter()


@router.get("/operator")
def operator_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    return RedirectResponse(url="/", status_code=303)


@router.post("/operator")
def update_operator(request: Request, operator_name: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect

    cleaned_operator_name = operator_name.strip()
    if not cleaned_operator_name:
        return RedirectResponse(url="/", status_code=303)

    set_session_operator_name(request, cleaned_operator_name)
    return RedirectResponse(url="/", status_code=303)
