from hmac import compare_digest

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import get_session_operator_name, require_auth, set_session_operator_name
from app.config import get_settings
from app.database import get_connection
from app.navigation import SUPPLIERS_CRUMB, breadcrumbs
from app.services.suppliers import (
    SUPPLIER_FIELDS,
    create_supplier_from_candidate,
    create_supplier,
    get_supplier,
    link_supplier_candidate,
    list_suppliers,
    list_supplier_candidates,
    supplier_form_values,
    supplier_form_values_from_db,
    update_supplier,
    validate_supplier_short_name_unique,
    validate_supplier_values,
)
from app.templating import templates


router = APIRouter()


@router.get("/suppliers")
def suppliers_page(request: Request, q: str = ""):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        suppliers = list_suppliers(connection, query=q)
    return templates.TemplateResponse(
        request,
        "suppliers.html",
        {
            "request": request,
            "suppliers": suppliers,
            "query": q,
            "breadcrumbs": breadcrumbs(SUPPLIERS_CRUMB),
            "return_url": "/",
        },
    )


@router.get("/suppliers/new")
def supplier_new_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    return render_supplier_form(
        request,
        supplier=None,
        values=supplier_form_values(),
        mode="new",
        operator_name=get_session_operator_name(request),
    )


@router.post("/suppliers/new")
def supplier_create_submit(
    request: Request,
    operator_name: str = Form(...),
    edit_password: str = Form(""),
    supplier_full_name: str = Form(""),
    supplier_short_name: str = Form(""),
    aliases_text: str = Form(""),
    contact_person: str = Form(""),
    phone: str = Form(""),
    wechat: str = Form(""),
    city: str = Form(""),
    province: str = Form(""),
    product_scope: str = Form(""),
    factory_or_trader: str = Form(""),
    quality_level: str = Form(""),
    price_level: str = Form(""),
    quality_rating: str = Form(""),
    price_rating: str = Form(""),
    cooperation_rating: str = Form(""),
    cooperation_notes: str = Form(""),
    notes: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    values = supplier_form_values(locals())
    errors = validate_supplier_values(values, operator_name)
    if not compare_digest(edit_password, get_settings().supplier_edit_password):
        errors.append("密码不正确。")
    with get_connection() as connection:
        errors.extend(
            validate_supplier_short_name_unique(
                connection,
                values.get("supplier_short_name", ""),
            )
        )
        if errors:
            return render_supplier_form(
                request,
                supplier=None,
                values=values,
                mode="new",
                errors=errors,
                operator_name=operator_name,
                status_code=400,
            )
        supplier_id = create_supplier(
            connection,
            values=values,
            operator_name=operator_name,
        )
        connection.commit()
    return RedirectResponse(url=f"/suppliers/{supplier_id}/edit", status_code=303)


@router.get("/suppliers/candidates")
def supplier_candidates_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        candidates = list_supplier_candidates(connection)
        suppliers = list_suppliers(connection, limit=1000)
    return templates.TemplateResponse(
        request,
        "supplier_candidates.html",
        {
            "request": request,
            "candidates": candidates,
            "suppliers": suppliers,
            "operator_name": get_session_operator_name(request),
            "breadcrumbs": [SUPPLIERS_CRUMB, {"label": "供应商候选", "href": ""}],
            "return_url": "/suppliers",
        },
    )


@router.post("/suppliers/candidates")
def supplier_candidate_submit(
    request: Request,
    operator_name: str = Form(...),
    factory_name: str = Form(...),
    action: str = Form(...),
    supplier_id: int = Form(0),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    if action == "create":
        with get_connection() as connection:
            create_supplier_from_candidate(
                connection,
                factory_name=factory_name,
                operator_name=operator_name,
            )
            connection.commit()
    elif action in {"link", "resolve"} and supplier_id:
        with get_connection() as connection:
            link_supplier_candidate(
                connection,
                factory_name=factory_name,
                supplier_id=supplier_id,
                operator_name=operator_name,
                action_type=(
                    "supplier_ambiguous_match_resolved"
                    if action == "resolve"
                    else "supplier_candidate_linked"
                ),
            )
            connection.commit()
    return RedirectResponse(url="/suppliers/candidates", status_code=303)


@router.get("/suppliers/{supplier_id}/edit")
def supplier_edit_page(request: Request, supplier_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        supplier = get_supplier(connection, supplier_id)
        values = supplier_form_values_from_db(connection, supplier) if supplier else {}
    if not supplier:
        return RedirectResponse(url="/suppliers", status_code=303)
    return render_supplier_form(
        request,
        supplier=supplier,
        values=values,
        mode="edit",
        operator_name=get_session_operator_name(request),
    )


@router.post("/suppliers/{supplier_id}/edit")
def supplier_edit_submit(
    request: Request,
    supplier_id: int,
    operator_name: str = Form(...),
    edit_password: str = Form(""),
    supplier_full_name: str = Form(""),
    supplier_short_name: str = Form(""),
    aliases_text: str = Form(""),
    contact_person: str = Form(""),
    phone: str = Form(""),
    wechat: str = Form(""),
    city: str = Form(""),
    province: str = Form(""),
    product_scope: str = Form(""),
    factory_or_trader: str = Form(""),
    quality_level: str = Form(""),
    price_level: str = Form(""),
    quality_rating: str = Form(""),
    price_rating: str = Form(""),
    cooperation_rating: str = Form(""),
    cooperation_notes: str = Form(""),
    notes: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect

    operator_name = set_session_operator_name(request, operator_name)
    values = supplier_form_values(locals())
    errors = validate_supplier_values(values, operator_name)
    if not compare_digest(edit_password, get_settings().supplier_edit_password):
        errors.append("密码不正确。")

    with get_connection() as connection:
        supplier = get_supplier(connection, supplier_id)
        if not supplier:
            return RedirectResponse(url="/suppliers", status_code=303)
        errors.extend(
            validate_supplier_short_name_unique(
                connection,
                values.get("supplier_short_name", ""),
                supplier_id=supplier_id,
            )
        )
        if errors:
            return render_supplier_form(
                request,
                supplier=supplier,
                values=values,
                mode="edit",
                errors=errors,
                operator_name=operator_name,
                status_code=400,
            )
        update_supplier(
            connection,
            supplier_id=supplier_id,
            values=values,
            operator_name=operator_name,
        )
        connection.commit()
        supplier = get_supplier(connection, supplier_id)
        values = supplier_form_values_from_db(connection, supplier)

    return render_supplier_form(
        request,
        supplier=supplier,
        values=values,
        mode="edit",
        success="供应商资料已保存。",
        operator_name=operator_name,
    )


def render_supplier_form(
    request: Request,
    *,
    supplier,
    values: dict[str, str],
    mode: str,
    operator_name: str,
    errors: list[str] | None = None,
    success: str | None = None,
    status_code: int = 200,
):
    page_label = "新增供应商" if mode == "new" else "编辑供应商"
    return templates.TemplateResponse(
        request,
        "supplier_form.html",
        {
            "request": request,
            "supplier": supplier,
            "values": values,
            "fields": SUPPLIER_FIELDS,
            "mode": mode,
            "operator_name": operator_name,
            "errors": errors or [],
            "success": success,
            "breadcrumbs": [SUPPLIERS_CRUMB, {"label": page_label, "href": ""}],
            "return_url": "/suppliers",
        },
        status_code=status_code,
    )
