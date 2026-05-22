from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    get_current_user,
    require_auth,
    require_password_confirmation,
    session_display_name,
    session_user_id,
)
from app.database import get_connection
from app.navigation import (
    CUSTOMS_ITEMS_CRUMB,
    CUSTOMS_MAPPINGS_CRUMB,
    CUSTOMS_MISSING_CRUMB,
    breadcrumbs,
    child_breadcrumbs,
)
from app.services.customs_items import (
    DECIMAL_PLACE_OPTIONS,
    UNIT_SOURCE_LABELS,
    UNIT_SOURCES,
    can_manage_customs_master_data,
    create_customs_item,
    customs_item_form_values,
    customs_item_values_from_db,
    get_customs_item,
    list_customs_items,
    set_customs_item_active,
    unit_source_label,
    update_customs_item,
    validate_customs_item_values,
)
from app.services.product_customs import (
    build_missing_customs_report,
    can_manage_customs_mapping,
    get_product_customs_mapping,
    list_mapping_options,
    list_product_customs_mappings,
    mapping_form_values,
    mapping_values_from_db,
    upsert_product_customs_mapping,
    validate_mapping_values,
)
from app.templating import templates


router = APIRouter()


@router.get("/customs/items")
def customs_items_page(request: Request, q: str = "", status: str = "active"):
    redirect = require_auth(request)
    if redirect:
        return redirect
    with get_connection() as connection:
        items = list_customs_items(connection, query=q, status=status)
    return templates.TemplateResponse(
        request,
        "customs_items.html",
        {
            "request": request,
            "items": items,
            "query": q,
            "status": status,
            "can_manage": can_manage_customs_master_data(get_current_user(request)),
            "unit_source_labels": UNIT_SOURCE_LABELS,
            "breadcrumbs": breadcrumbs(CUSTOMS_ITEMS_CRUMB),
            "return_url": "/",
        },
    )


@router.get("/customs/items/new")
def customs_item_new_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_customs_master_data(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    return render_customs_item_form(
        request,
        item=None,
        values=customs_item_form_values(),
        mode="new",
    )


@router.post("/customs/items/new")
def customs_item_create_submit(
    request: Request,
    customs_name_cn: str = Form(""),
    customs_name_en: str = Form(""),
    hs_code: str = Form(""),
    unit_1: str = Form(""),
    unit_1_source: str = Form(""),
    unit_1_decimal_places: str = Form("0"),
    unit_2: str = Form(""),
    unit_2_source: str = Form(""),
    unit_2_decimal_places: str = Form(""),
    declaration_element_template: str = Form(""),
    notes: str = Form(""),
    confirm_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    current_user = get_current_user(request)
    if not can_manage_customs_master_data(current_user):
        return RedirectResponse(url="/forbidden", status_code=303)
    values = customs_item_form_values(locals())
    password_error = require_password_confirmation(request, confirm_password)
    with get_connection() as connection:
        errors = validate_customs_item_values(connection, values)
        if password_error:
            errors.append(password_error)
        if errors:
            return render_customs_item_form(
                request,
                item=None,
                values=values,
                mode="new",
                errors=errors,
                status_code=400,
            )
        item_id = create_customs_item(
            connection,
            values=values,
            user_id=session_user_id(request),
            operator_name=session_display_name(request),
        )
        connection.commit()
    return RedirectResponse(url=f"/customs/items/{item_id}", status_code=303)


@router.get("/customs/items/{item_id}")
def customs_item_detail_page(request: Request, item_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect
    with get_connection() as connection:
        item = get_customs_item(connection, item_id)
    if not item:
        return RedirectResponse(url="/customs/items", status_code=303)
    return render_customs_item_detail(request, item=item)


@router.get("/customs/items/{item_id}/edit")
def customs_item_edit_page(request: Request, item_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_customs_master_data(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    with get_connection() as connection:
        item = get_customs_item(connection, item_id)
    if not item:
        return RedirectResponse(url="/customs/items", status_code=303)
    return render_customs_item_form(
        request,
        item=item,
        values=customs_item_values_from_db(item),
        mode="edit",
    )


@router.post("/customs/items/{item_id}/edit")
def customs_item_edit_submit(
    request: Request,
    item_id: int,
    customs_name_cn: str = Form(""),
    customs_name_en: str = Form(""),
    hs_code: str = Form(""),
    unit_1: str = Form(""),
    unit_1_source: str = Form(""),
    unit_1_decimal_places: str = Form("0"),
    unit_2: str = Form(""),
    unit_2_source: str = Form(""),
    unit_2_decimal_places: str = Form(""),
    declaration_element_template: str = Form(""),
    notes: str = Form(""),
    confirm_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_customs_master_data(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    values = customs_item_form_values(locals())
    password_error = require_password_confirmation(request, confirm_password)
    with get_connection() as connection:
        item = get_customs_item(connection, item_id)
        if not item:
            return RedirectResponse(url="/customs/items", status_code=303)
        errors = validate_customs_item_values(connection, values, item_id=item_id)
        if password_error:
            errors.append(password_error)
        if errors:
            return render_customs_item_form(
                request,
                item=item,
                values=values,
                mode="edit",
                errors=errors,
                status_code=400,
            )
        update_customs_item(
            connection,
            item_id=item_id,
            values=values,
            user_id=session_user_id(request),
            operator_name=session_display_name(request),
        )
        connection.commit()
    return RedirectResponse(url=f"/customs/items/{item_id}", status_code=303)


@router.post("/customs/items/{item_id}/toggle-active")
def customs_item_toggle_active(
    request: Request,
    item_id: int,
    confirm_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_customs_master_data(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    password_error = require_password_confirmation(request, confirm_password)
    with get_connection() as connection:
        item = get_customs_item(connection, item_id)
        if not item:
            return RedirectResponse(url="/customs/items", status_code=303)
        if password_error:
            return render_customs_item_detail(
                request,
                item=item,
                errors=[password_error],
                status_code=400,
            )
        set_customs_item_active(
            connection,
            item_id=item_id,
            is_active=not bool(item["is_active"]),
            user_id=session_user_id(request),
            operator_name=session_display_name(request),
        )
        connection.commit()
    return RedirectResponse(url=f"/customs/items/{item_id}", status_code=303)


@router.get("/customs/mappings")
def customs_mappings_page(request: Request, q: str = ""):
    redirect = require_auth(request)
    if redirect:
        return redirect
    with get_connection() as connection:
        mappings = list_product_customs_mappings(connection, query=q)
    return templates.TemplateResponse(
        request,
        "customs_mappings.html",
        {
            "request": request,
            "mappings": mappings,
            "query": q,
            "can_manage": can_manage_customs_mapping(get_current_user(request)),
            "unit_source_labels": UNIT_SOURCE_LABELS,
            "breadcrumbs": breadcrumbs(CUSTOMS_MAPPINGS_CRUMB),
            "return_url": "/customs",
        },
    )


@router.get("/customs/mappings/new")
def customs_mapping_new_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_customs_mapping(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    with get_connection() as connection:
        products, customs_items = list_mapping_options(connection)
    return render_customs_mapping_form(
        request,
        mapping=None,
        values=mapping_form_values(),
        products=products,
        customs_items=customs_items,
        mode="new",
    )


@router.post("/customs/mappings/new")
def customs_mapping_create_submit(
    request: Request,
    product_id: str = Form(""),
    customs_item_id: str = Form(""),
    part_no_for_declaration: str = Form(""),
    model_for_declaration: str = Form(""),
    material: str = Form(""),
    brand: str = Form(""),
    declaration_notes: str = Form(""),
    confirm_password: str = Form(""),
):
    return handle_customs_mapping_submit(
        request,
        mapping_id=None,
        values=mapping_form_values(locals()),
        confirm_password=confirm_password,
    )


@router.get("/customs/mappings/{mapping_id}/edit")
def customs_mapping_edit_page(request: Request, mapping_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_customs_mapping(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    with get_connection() as connection:
        mapping = get_product_customs_mapping(connection, mapping_id)
        products, customs_items = list_mapping_options(connection)
    if not mapping:
        return RedirectResponse(url="/customs/mappings", status_code=303)
    return render_customs_mapping_form(
        request,
        mapping=mapping,
        values=mapping_values_from_db(mapping),
        products=products,
        customs_items=customs_items,
        mode="edit",
    )


@router.post("/customs/mappings/{mapping_id}/edit")
def customs_mapping_edit_submit(
    request: Request,
    mapping_id: int,
    product_id: str = Form(""),
    customs_item_id: str = Form(""),
    part_no_for_declaration: str = Form(""),
    model_for_declaration: str = Form(""),
    material: str = Form(""),
    brand: str = Form(""),
    declaration_notes: str = Form(""),
    confirm_password: str = Form(""),
):
    return handle_customs_mapping_submit(
        request,
        mapping_id=mapping_id,
        values=mapping_form_values(locals()),
        confirm_password=confirm_password,
    )


@router.get("/customs/missing")
def customs_missing_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    with get_connection() as connection:
        report = build_missing_customs_report(connection)
    return templates.TemplateResponse(
        request,
        "customs_missing.html",
        {
            "request": request,
            "report": report,
            "unit_source_labels": UNIT_SOURCE_LABELS,
            "breadcrumbs": breadcrumbs(CUSTOMS_MISSING_CRUMB),
            "return_url": "/customs",
        },
    )


def handle_customs_mapping_submit(
    request: Request,
    *,
    mapping_id: int | None,
    values: dict[str, str],
    confirm_password: str,
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_customs_mapping(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    password_error = require_password_confirmation(request, confirm_password)
    with get_connection() as connection:
        mapping = get_product_customs_mapping(connection, mapping_id) if mapping_id else None
        products, customs_items = list_mapping_options(connection)
        errors = validate_mapping_values(connection, values)
        if password_error:
            errors.append(password_error)
        if errors:
            return render_customs_mapping_form(
                request,
                mapping=mapping,
                values=values,
                products=products,
                customs_items=customs_items,
                mode="edit" if mapping_id else "new",
                errors=errors,
                status_code=400,
            )
        saved_mapping_id, _ = upsert_product_customs_mapping(
            connection,
            values=values,
            user_id=session_user_id(request),
            operator_name=session_display_name(request),
        )
        connection.commit()
    return RedirectResponse(url=f"/customs/mappings?mapped={saved_mapping_id}", status_code=303)


def render_customs_item_detail(
    request: Request,
    *,
    item,
    errors: list[str] | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "customs_item_detail.html",
        {
            "request": request,
            "item": item,
            "can_manage": can_manage_customs_master_data(get_current_user(request)),
            "unit_source_labels": UNIT_SOURCE_LABELS,
            "errors": errors or [],
            "breadcrumbs": child_breadcrumbs(
                CUSTOMS_ITEMS_CRUMB,
                item["customs_name_cn"],
            ),
            "return_url": "/customs/items",
        },
        status_code=status_code,
    )


def render_customs_mapping_form(
    request: Request,
    *,
    mapping,
    values: dict,
    products,
    customs_items,
    mode: str,
    errors: list[str] | None = None,
    status_code: int = 200,
):
    page_label = "新增产品报关映射" if mode == "new" else "编辑产品报关映射"
    return templates.TemplateResponse(
        request,
        "customs_mapping_form.html",
        {
            "request": request,
            "mapping": mapping,
            "values": values,
            "products": products,
            "customs_items": customs_items,
            "mode": mode,
            "errors": errors or [],
            "breadcrumbs": child_breadcrumbs(CUSTOMS_MAPPINGS_CRUMB, page_label),
            "return_url": "/customs/mappings",
        },
        status_code=status_code,
    )


def render_customs_item_form(
    request: Request,
    *,
    item,
    values: dict,
    mode: str,
    errors: list[str] | None = None,
    status_code: int = 200,
):
    page_label = "新增报关资料" if mode == "new" else str(values.get("customs_name_cn") or "编辑报关资料")
    return templates.TemplateResponse(
        request,
        "customs_item_form.html",
        {
            "request": request,
            "item": item,
            "values": values,
            "mode": mode,
            "errors": errors or [],
            "unit_sources": UNIT_SOURCES,
            "unit_source_labels": UNIT_SOURCE_LABELS,
            "unit_source_label": unit_source_label,
            "decimal_places": DECIMAL_PLACE_OPTIONS,
            "breadcrumbs": child_breadcrumbs(CUSTOMS_ITEMS_CRUMB, page_label),
            "return_url": "/customs/items",
        },
        status_code=status_code,
    )
