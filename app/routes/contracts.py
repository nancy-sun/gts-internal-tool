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
from app.navigation import CONTRACTS_CRUMB, breadcrumbs, child_breadcrumbs
from app.services.purchase_contracts import (
    CONTRACT_STATUS_LABELS,
    CONTRACT_STATUSES,
    add_purchase_contract_item,
    can_manage_purchase_contracts,
    cancel_purchase_contract,
    contract_form_values,
    contract_values_from_db,
    create_purchase_contract,
    delete_purchase_contract_item,
    get_purchase_contract,
    get_purchase_contract_item,
    item_form_values,
    list_contract_options,
    list_purchase_contract_items,
    list_purchase_contracts,
    update_purchase_contract,
    update_purchase_contract_item,
    validate_contract_values,
    validate_item_values,
)
from app.templating import templates


router = APIRouter()


@router.get("/contracts")
def contracts_page(request: Request, q: str = "", status: str = "all"):
    redirect = require_auth(request)
    if redirect:
        return redirect
    with get_connection() as connection:
        contracts = list_purchase_contracts(connection, query=q, status=status)
    return templates.TemplateResponse(
        request,
        "contracts.html",
        {
            "request": request,
            "contracts": contracts,
            "query": q,
            "status": status,
            "statuses": CONTRACT_STATUSES,
            "status_labels": CONTRACT_STATUS_LABELS,
            "can_manage": can_manage_purchase_contracts(get_current_user(request)),
            "breadcrumbs": breadcrumbs(CONTRACTS_CRUMB),
            "return_url": "/",
        },
    )


@router.get("/contracts/new")
def contract_new_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_purchase_contracts(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    with get_connection() as connection:
        suppliers, _ = list_contract_options(connection)
    return render_contract_form(
        request,
        contract=None,
        values=contract_form_values(),
        suppliers=suppliers,
        mode="new",
    )


@router.post("/contracts/new")
def contract_create_submit(
    request: Request,
    contract_no: str = Form(""),
    supplier_id: str = Form(""),
    status: str = Form("draft"),
    notes: str = Form(""),
    confirm_password: str = Form(""),
):
    return handle_contract_submit(
        request,
        contract_id=None,
        values=contract_form_values(locals()),
        confirm_password=confirm_password,
    )


@router.get("/contracts/{contract_id}")
def contract_detail_page(request: Request, contract_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect
    with get_connection() as connection:
        contract = get_purchase_contract(connection, contract_id)
        items = list_purchase_contract_items(connection, contract_id) if contract else []
        _, products = list_contract_options(connection)
    if not contract:
        return RedirectResponse(url="/contracts", status_code=303)
    return render_contract_detail(
        request,
        contract=contract,
        items=items,
        products=products,
    )


@router.get("/contracts/{contract_id}/edit")
def contract_edit_page(request: Request, contract_id: int):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_purchase_contracts(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    with get_connection() as connection:
        contract = get_purchase_contract(connection, contract_id)
        suppliers, _ = list_contract_options(connection)
    if not contract:
        return RedirectResponse(url="/contracts", status_code=303)
    return render_contract_form(
        request,
        contract=contract,
        values=contract_values_from_db(contract),
        suppliers=suppliers,
        mode="edit",
    )


@router.post("/contracts/{contract_id}/edit")
def contract_edit_submit(
    request: Request,
    contract_id: int,
    contract_no: str = Form(""),
    supplier_id: str = Form(""),
    status: str = Form("draft"),
    notes: str = Form(""),
    confirm_password: str = Form(""),
):
    return handle_contract_submit(
        request,
        contract_id=contract_id,
        values=contract_form_values(locals()),
        confirm_password=confirm_password,
    )


@router.post("/contracts/{contract_id}/cancel")
def contract_cancel_submit(
    request: Request,
    contract_id: int,
    confirm_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_purchase_contracts(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    password_error = require_password_confirmation(request, confirm_password)
    with get_connection() as connection:
        contract = get_purchase_contract(connection, contract_id)
        if not contract:
            return RedirectResponse(url="/contracts", status_code=303)
        if password_error:
            items = list_purchase_contract_items(connection, contract_id)
            _, products = list_contract_options(connection)
            return render_contract_detail(
                request,
                contract=contract,
                items=items,
                products=products,
                errors=[password_error],
                status_code=400,
            )
        cancel_purchase_contract(
            connection,
            contract_id=contract_id,
            user_id=session_user_id(request),
            operator_name=session_display_name(request),
        )
        connection.commit()
    return RedirectResponse(url=f"/contracts/{contract_id}", status_code=303)


@router.post("/contracts/{contract_id}/items/add")
def contract_item_add_submit(
    request: Request,
    contract_id: int,
    product_id: str = Form(""),
    quotation_item_id: str = Form(""),
    gts_no: str = Form(""),
    oem: str = Form(""),
    description_cn: str = Form(""),
    description_en: str = Form(""),
    quantity: str = Form(""),
    unit: str = Form(""),
    unit_price_rmb: str = Form(""),
    gross_weight: str = Form(""),
    packages: str = Form(""),
    volume: str = Form(""),
    notes: str = Form(""),
    confirm_password: str = Form(""),
):
    return handle_contract_item_submit(
        request,
        contract_id=contract_id,
        item_id=None,
        values=item_form_values(locals()),
        confirm_password=confirm_password,
    )


@router.post("/contracts/{contract_id}/items/{item_id}/edit")
def contract_item_edit_submit(
    request: Request,
    contract_id: int,
    item_id: int,
    product_id: str = Form(""),
    quotation_item_id: str = Form(""),
    gts_no: str = Form(""),
    oem: str = Form(""),
    description_cn: str = Form(""),
    description_en: str = Form(""),
    quantity: str = Form(""),
    unit: str = Form(""),
    unit_price_rmb: str = Form(""),
    gross_weight: str = Form(""),
    packages: str = Form(""),
    volume: str = Form(""),
    notes: str = Form(""),
    confirm_password: str = Form(""),
):
    return handle_contract_item_submit(
        request,
        contract_id=contract_id,
        item_id=item_id,
        values=item_form_values(locals()),
        confirm_password=confirm_password,
    )


@router.post("/contracts/{contract_id}/items/{item_id}/delete")
def contract_item_delete_submit(
    request: Request,
    contract_id: int,
    item_id: int,
    confirm_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_purchase_contracts(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    password_error = require_password_confirmation(request, confirm_password)
    if password_error:
        return render_contract_detail_by_id(
            request,
            contract_id,
            errors=[password_error],
            status_code=400,
        )
    with get_connection() as connection:
        delete_purchase_contract_item(
            connection,
            contract_id=contract_id,
            item_id=item_id,
            operator_name=session_display_name(request),
        )
        connection.commit()
    return RedirectResponse(url=f"/contracts/{contract_id}", status_code=303)


def handle_contract_submit(
    request: Request,
    *,
    contract_id: int | None,
    values: dict[str, str],
    confirm_password: str,
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_purchase_contracts(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    password_error = require_password_confirmation(request, confirm_password)
    with get_connection() as connection:
        contract = get_purchase_contract(connection, contract_id) if contract_id else None
        suppliers, _ = list_contract_options(connection)
        errors = validate_contract_values(connection, values, contract_id=contract_id)
        if password_error:
            errors.append(password_error)
        if errors:
            return render_contract_form(
                request,
                contract=contract,
                values=values,
                suppliers=suppliers,
                mode="edit" if contract_id else "new",
                errors=errors,
                status_code=400,
            )
        if contract_id:
            update_purchase_contract(
                connection,
                contract_id=contract_id,
                values=values,
                user_id=session_user_id(request),
                operator_name=session_display_name(request),
            )
            saved_id = contract_id
        else:
            saved_id = create_purchase_contract(
                connection,
                values=values,
                user_id=session_user_id(request),
                operator_name=session_display_name(request),
            )
        connection.commit()
    return RedirectResponse(url=f"/contracts/{saved_id}", status_code=303)


def handle_contract_item_submit(
    request: Request,
    *,
    contract_id: int,
    item_id: int | None,
    values: dict[str, str],
    confirm_password: str,
):
    redirect = require_auth(request)
    if redirect:
        return redirect
    if not can_manage_purchase_contracts(get_current_user(request)):
        return RedirectResponse(url="/forbidden", status_code=303)
    password_error = require_password_confirmation(request, confirm_password)
    with get_connection() as connection:
        contract = get_purchase_contract(connection, contract_id)
        if not contract:
            return RedirectResponse(url="/contracts", status_code=303)
        if item_id and not get_purchase_contract_item(connection, item_id):
            return RedirectResponse(url=f"/contracts/{contract_id}", status_code=303)
        errors = validate_item_values(values)
        if password_error:
            errors.append(password_error)
        if errors:
            items = list_purchase_contract_items(connection, contract_id)
            _, products = list_contract_options(connection)
            return render_contract_detail(
                request,
                contract=contract,
                items=items,
                products=products,
                errors=errors,
                item_values=values,
                status_code=400,
            )
        if item_id:
            update_purchase_contract_item(
                connection,
                contract_id=contract_id,
                item_id=item_id,
                values=values,
                operator_name=session_display_name(request),
            )
        else:
            add_purchase_contract_item(
                connection,
                contract_id=contract_id,
                values=values,
                operator_name=session_display_name(request),
            )
        connection.commit()
    return RedirectResponse(url=f"/contracts/{contract_id}", status_code=303)


def render_contract_detail_by_id(
    request: Request,
    contract_id: int,
    *,
    errors: list[str],
    status_code: int,
):
    with get_connection() as connection:
        contract = get_purchase_contract(connection, contract_id)
        items = list_purchase_contract_items(connection, contract_id) if contract else []
        _, products = list_contract_options(connection)
    if not contract:
        return RedirectResponse(url="/contracts", status_code=303)
    return render_contract_detail(
        request,
        contract=contract,
        items=items,
        products=products,
        errors=errors,
        status_code=status_code,
    )


def render_contract_detail(
    request: Request,
    *,
    contract,
    items,
    products,
    errors: list[str] | None = None,
    item_values: dict[str, str] | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "contract_detail.html",
        {
            "request": request,
            "contract": contract,
            "items": items,
            "products": products,
            "item_values": item_values or item_form_values(),
            "errors": errors or [],
            "can_manage": can_manage_purchase_contracts(get_current_user(request)),
            "breadcrumbs": child_breadcrumbs(CONTRACTS_CRUMB, contract["contract_no"]),
            "return_url": "/contracts",
        },
        status_code=status_code,
    )


def render_contract_form(
    request: Request,
    *,
    contract,
    values: dict[str, str],
    suppliers,
    mode: str,
    errors: list[str] | None = None,
    status_code: int = 200,
):
    page_label = "新增采购合同" if mode == "new" else str(values.get("contract_no") or "编辑采购合同")
    return templates.TemplateResponse(
        request,
        "contract_form.html",
        {
            "request": request,
            "contract": contract,
            "values": values,
            "suppliers": suppliers,
            "mode": mode,
            "errors": errors or [],
            "statuses": CONTRACT_STATUSES,
            "status_labels": CONTRACT_STATUS_LABELS,
            "breadcrumbs": child_breadcrumbs(CONTRACTS_CRUMB, page_label),
            "return_url": "/contracts",
        },
        status_code=status_code,
    )
