from fastapi import APIRouter, Form, Request

from app.auth import get_session_operator_name, require_auth, set_session_operator_name
from app.navigation import OPERATOR_CRUMB, breadcrumbs
from app.templating import templates


router = APIRouter()


@router.get("/operator")
def operator_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    return render_operator_page(request)


@router.post("/operator")
def update_operator(request: Request, operator_name: str = Form(...)):
    redirect = require_auth(request)
    if redirect:
        return redirect

    cleaned_operator_name = operator_name.strip()
    if not cleaned_operator_name:
        return render_operator_page(
            request,
            operator_name="",
            error="请填写操作人。",
            status_code=400,
        )

    set_session_operator_name(request, cleaned_operator_name)
    return render_operator_page(
        request,
        operator_name=cleaned_operator_name,
        success="操作人已保存。",
    )


def render_operator_page(
    request: Request,
    *,
    operator_name: str | None = None,
    error: str | None = None,
    success: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "operator.html",
        {
            "request": request,
            "operator_name": (
                get_session_operator_name(request)
                if operator_name is None
                else operator_name
            ),
            "error": error,
            "success": success,
            "breadcrumbs": breadcrumbs(OPERATOR_CRUMB),
            "return_url": "/",
        },
        status_code=status_code,
    )
