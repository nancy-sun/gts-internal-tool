from hmac import compare_digest

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import get_session_operator_name, require_auth, set_session_operator_name
from app.config import get_settings
from app.database import get_connection
from app.navigation import SEARCH_CRUMB
from app.services.product_edit import get_product, update_product, validate_product_edit
from app.templating import templates


router = APIRouter()


@router.get("/products/{product_id}/edit")
def product_edit_page(request: Request, product_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        product = get_product(connection, product_id)
    if not product:
        return RedirectResponse(url="/search", status_code=303)

    return render_product_edit(
        request,
        product=product,
        values=dict(product),
        errors=[],
        warnings=[],
    )


@router.post("/products/{product_id}/edit")
async def product_edit_submit(
    request: Request,
    product_id: int,
    operator_name: str = Form(...),
    gts_no: str = Form(""),
    oem: str = Form(""),
    description: str = Form(""),
    chinese_description: str = Form(""),
    hs_code: str = Form(""),
    edit_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    values = {
        "gts_no": gts_no,
        "oem": oem,
        "description": description,
        "chinese_description": chinese_description,
        "hs_code": hs_code,
    }
    errors = []
    if not operator_name.strip():
        errors.append("请填写操作人。")
    if not compare_digest(edit_password, get_settings().product_edit_password):
        errors.append("确认密码不正确。")

    with get_connection() as connection:
        validation = validate_product_edit(
            connection,
            product_id=product_id,
            values=values,
        )
        product = validation.product
        errors.extend(validation.errors)
        if errors or not product:
            return render_product_edit(
                request,
                product=product,
                values=values,
                errors=errors,
                warnings=validation.warnings,
                operator_name=operator_name,
                status_code=400,
            )

        result = update_product(
            connection,
            product_id=product_id,
            values=values,
            operator_name=operator_name,
        )
        connection.commit()

    return render_product_edit(
        request,
        product=result.product,
        values=dict(result.product) if result.product else values,
        errors=[],
        warnings=result.warnings,
        success="产品资料已更新。",
    )


def render_product_edit(
    request: Request,
    *,
    product,
    values: dict,
    errors: list[str],
    warnings: list[str],
    operator_name: str | None = None,
    success: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "product_edit.html",
        {
            "request": request,
            "product": product,
            "values": values,
            "operator_name": (
                get_session_operator_name(request)
                if operator_name is None
                else operator_name
            ),
            "errors": errors,
            "warnings": warnings,
            "success": success,
            "breadcrumbs": [
                SEARCH_CRUMB,
                {"label": "编辑产品", "href": ""},
            ],
            "return_url": "/search",
        },
        status_code=status_code,
    )
