from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    get_current_user,
    require_admin,
    require_password_confirmation,
    session_display_name,
)
from app.database import get_connection
from app.navigation import ADMIN_USERS_CRUMB, breadcrumbs, child_breadcrumbs
from app.services.operation_logging import create_operation_log
from app.services.users import (
    VALID_ROLES,
    create_user,
    delete_user_if_safe,
    get_user,
    list_users,
    reset_user_password,
    set_user_active,
    update_user,
)
from app.templating import templates


router = APIRouter()


@router.get("/admin/users")
def admin_users_page(request: Request):
    redirect = require_admin(request)
    if redirect:
        return redirect
    with get_connection() as connection:
        users = list_users(connection)
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "request": request,
            "users": users,
            "breadcrumbs": breadcrumbs(ADMIN_USERS_CRUMB),
            "return_url": "/",
        },
    )


@router.get("/admin/users/new")
def admin_user_new_page(request: Request):
    redirect = require_admin(request)
    if redirect:
        return redirect
    return render_user_form(
        request,
        user=None,
        values={"role": "sales", "must_change_password": "1"},
        mode="new",
        errors=[],
    )


@router.post("/admin/users/new")
def admin_user_create(
    request: Request,
    username: str = Form(""),
    display_name: str = Form(""),
    role: str = Form("sales"),
    password: str = Form(""),
    confirm_password: str = Form(""),
    must_change_password: str = Form(""),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    values = user_form_values(locals())
    errors = []
    if password != confirm_password:
        errors.append("两次输入的密码不一致。")
    with get_connection() as connection:
        user_id = None
        if not errors:
            user_id, create_errors = create_user(
                connection,
                username=username,
                display_name=display_name,
                role=role,
                password=password,
                must_change_password=bool(must_change_password),
            )
            errors.extend(create_errors)
        if errors:
            return render_user_form(
                request,
                user=None,
                values=values,
                mode="new",
                errors=errors,
                status_code=400,
            )
        create_operation_log(
            connection,
            operator_name=session_display_name(request),
            action_type="user_created",
            note=username.strip(),
        )
        connection.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}/edit", status_code=303)


@router.get("/admin/users/{user_id}/edit")
def admin_user_edit_page(request: Request, user_id: int):
    redirect = require_admin(request)
    if redirect:
        return redirect
    with get_connection() as connection:
        user = get_user(connection, user_id)
    if not user:
        return RedirectResponse(url="/admin/users", status_code=303)
    return render_user_form(
        request,
        user=user,
        values=dict(user),
        mode="edit",
        errors=[],
    )


@router.post("/admin/users/{user_id}/edit")
def admin_user_edit(
    request: Request,
    user_id: int,
    username: str = Form(""),
    display_name: str = Form(""),
    role: str = Form("sales"),
    must_change_password: str = Form(""),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    values = user_form_values(locals())
    with get_connection() as connection:
        user = get_user(connection, user_id)
        if not user:
            return RedirectResponse(url="/admin/users", status_code=303)
        errors = update_user(
            connection,
            user_id=user_id,
            username=username,
            display_name=display_name,
            role=role,
            must_change_password=bool(must_change_password),
            operator_name=session_display_name(request),
        )
        if errors:
            return render_user_form(
                request,
                user=user,
                values=values,
                mode="edit",
                errors=errors,
                status_code=400,
            )
        create_operation_log(
            connection,
            operator_name=session_display_name(request),
            action_type="user_edited",
            note=username.strip(),
        )
        connection.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/reset-password")
def admin_user_reset_password(
    request: Request,
    user_id: int,
    password: str = Form(""),
    confirm_password: str = Form(""),
    must_change_password: str = Form(""),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    errors = []
    if password != confirm_password:
        errors.append("两次输入的密码不一致。")
    with get_connection() as connection:
        user = get_user(connection, user_id)
        if not user:
            return RedirectResponse(url="/admin/users", status_code=303)
        if not errors:
            errors = reset_user_password(
                connection,
                user_id=user_id,
                password=password,
                must_change_password=bool(must_change_password),
            )
        if errors:
            return render_user_form(
                request,
                user=user,
                values=dict(user),
                mode="edit",
                errors=errors,
                status_code=400,
            )
        create_operation_log(
            connection,
            operator_name=session_display_name(request),
            action_type="user_password_reset",
            note=user["username"],
        )
        connection.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/toggle-active")
def admin_user_toggle_active(request: Request, user_id: int):
    redirect = require_admin(request)
    if redirect:
        return redirect
    current_user = get_current_user(request)
    if current_user and int(current_user["id"]) == user_id:
        return RedirectResponse(url="/admin/users", status_code=303)
    with get_connection() as connection:
        user = get_user(connection, user_id)
        if not user:
            return RedirectResponse(url="/admin/users", status_code=303)
        errors = set_user_active(
            connection,
            user_id=user_id,
            is_active=not bool(user["is_active"]),
        )
        if not errors:
            create_operation_log(
                connection,
                operator_name=session_display_name(request),
                action_type="user_active_changed",
                note=user["username"],
            )
            connection.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/delete")
def admin_user_delete(
    request: Request,
    user_id: int,
    confirm_password: str = Form(""),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    current_user = get_current_user(request)
    if current_user and int(current_user["id"]) == user_id:
        return render_delete_error(request, "不能删除当前登录账号。")
    password_error = require_password_confirmation(request, confirm_password)
    if password_error:
        return render_delete_error(request, password_error)
    with get_connection() as connection:
        user = get_user(connection, user_id)
        errors = delete_user_if_safe(connection, user_id=user_id)
        if errors:
            return render_delete_error(request, "；".join(errors))
        if user:
            create_operation_log(
                connection,
                operator_name=session_display_name(request),
                action_type="user_deleted",
                note=user["username"],
            )
        connection.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


def render_delete_error(request: Request, error: str):
    with get_connection() as connection:
        users = list_users(connection)
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "request": request,
            "users": users,
            "error": error,
            "breadcrumbs": breadcrumbs(ADMIN_USERS_CRUMB),
            "return_url": "/",
        },
        status_code=400,
    )


def render_user_form(
    request: Request,
    *,
    user,
    values: dict,
    mode: str,
    errors: list[str],
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "admin_user_form.html",
        {
            "request": request,
            "user": user,
            "values": values,
            "mode": mode,
            "roles": VALID_ROLES,
            "errors": errors,
            "breadcrumbs": child_breadcrumbs(
                ADMIN_USERS_CRUMB,
                "新增用户" if mode == "new" else str(values.get("username") or "编辑用户"),
            ),
            "return_url": "/admin/users",
        },
        status_code=status_code,
    )


def user_form_values(values: dict) -> dict:
    return {
        "username": str(values.get("username") or "").strip(),
        "display_name": str(values.get("display_name") or "").strip(),
        "role": str(values.get("role") or "sales"),
        "must_change_password": "1" if values.get("must_change_password") else "",
    }
