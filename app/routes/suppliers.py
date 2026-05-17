from hmac import compare_digest

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import get_session_operator_name, require_auth, set_session_operator_name
from app.config import get_settings
from app.database import get_connection
from app.navigation import SUPPLIERS_CRUMB, breadcrumbs, child_breadcrumbs
from app.services.suppliers import (
    create_supplier,
    get_supplier,
    list_suppliers,
    supplier_form_values,
    supplier_form_values_from_db,
    supplier_display_name,
    update_supplier,
    validate_supplier_short_name_unique,
    validate_supplier_values,
)
from app.templating import templates


router = APIRouter()


@router.get("/suppliers")
def suppliers_page(request: Request, q: str = "", status: str = "all"):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        suppliers = list_suppliers(connection, query=q)
    supplier_rows = [
        {"supplier": supplier, "missing_tags": supplier_missing_tags(supplier)}
        for supplier in suppliers
    ]
    incomplete_count = sum(1 for row in supplier_rows if row["missing_tags"])
    if status == "incomplete":
        supplier_rows = [row for row in supplier_rows if row["missing_tags"]]
    return templates.TemplateResponse(
        request,
        "suppliers.html",
        {
            "request": request,
            "supplier_rows": supplier_rows,
            "query": q,
            "status": status,
            "incomplete_count": incomplete_count,
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
    quality_rating: str = Form(""),
    price_rating: str = Form(""),
    cooperation_rating: str = Form(""),
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


def supplier_missing_tags(supplier) -> list[dict[str, str]]:
    tags = []
    supplier_info_fields = (
        "supplier_full_name",
        "supplier_short_name",
        "aliases_text",
        "city",
        "product_scope",
    )
    if any(not (supplier[field] or "").strip() for field in supplier_info_fields):
        tags.append({"label": "缺供应商信息", "kind": "supplier-info"})
    contact_fields = ("contact_person", "phone", "wechat")
    if any(not (supplier[field] or "").strip() for field in contact_fields):
        tags.append({"label": "缺联系方式", "kind": "contact"})
    rating_fields = ("quality_rating", "price_rating", "cooperation_rating")
    if any(supplier[field] is None for field in rating_fields):
        tags.append({"label": "缺评分", "kind": "rating"})
    return tags


@router.get("/suppliers/{supplier_id}/edit")
def supplier_edit_page(request: Request, supplier_id: int, mode: str = "view"):
    redirect = require_auth(request)
    if redirect:
        return redirect

    with get_connection() as connection:
        supplier = get_supplier(connection, supplier_id)
        values = supplier_form_values_from_db(connection, supplier) if supplier else {}
    if not supplier:
        return RedirectResponse(url="/suppliers", status_code=303)
    if mode != "edit":
        return render_supplier_detail(
            request,
            supplier=supplier,
            values=values,
            operator_name=get_session_operator_name(request),
        )
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
    quality_rating: str = Form(""),
    price_rating: str = Form(""),
    cooperation_rating: str = Form(""),
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

    return RedirectResponse(url=f"/suppliers/{supplier_id}/edit", status_code=303)


def render_supplier_detail(
    request: Request,
    *,
    supplier,
    values: dict[str, str],
    operator_name: str,
    status_code: int = 200,
):
    display_name = supplier_display_name(supplier)
    return templates.TemplateResponse(
        request,
        "supplier_detail.html",
        {
            "request": request,
            "supplier": supplier,
            "values": values,
            "operator_name": operator_name,
            "missing_tags": supplier_missing_tags(supplier),
            "breadcrumbs": child_breadcrumbs(SUPPLIERS_CRUMB, display_name),
            "return_url": "/suppliers",
        },
        status_code=status_code,
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
    page_label = "新增供应商" if mode == "new" else supplier_display_name(supplier)
    return templates.TemplateResponse(
        request,
        "supplier_form.html",
        {
            "request": request,
            "supplier": supplier,
            "values": values,
            "mode": mode,
            "operator_name": operator_name,
            "errors": errors or [],
            "success": success,
            "breadcrumbs": child_breadcrumbs(SUPPLIERS_CRUMB, page_label),
            "return_url": "/suppliers",
        },
        status_code=status_code,
    )
