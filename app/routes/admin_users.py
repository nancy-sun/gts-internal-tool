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
    delete_user_and_detach_logs,
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
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    admin_confirm_password: str = Form(""),
    must_change_password: str = Form(""),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    values = user_form_values(locals())
    errors = []
    password_error = require_password_confirmation(request, admin_confirm_password)
    if password_error:
        errors.append(password_error)
    if new_password != new_password_confirm:
        errors.append("两次输入的密码不一致。")
    with get_connection() as connection:
        user_id = None
        if not errors:
            user_id, create_errors = create_user(
                connection,
                username=username,
                display_name=display_name,
                role=role,
                password=new_password,
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
    admin_confirm_password: str = Form(""),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    values = user_form_values(locals())
    with get_connection() as connection:
        user = get_user(connection, user_id)
        if not user:
            return RedirectResponse(url="/admin/users", status_code=303)
        errors = []
        password_error = require_password_confirmation(request, admin_confirm_password)
        if password_error:
            errors.append(password_error)
        if not errors:
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
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    admin_confirm_password: str = Form(""),
    must_change_password: str = Form(""),
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    errors = []
    password_error = require_password_confirmation(request, admin_confirm_password)
    if password_error:
        errors.append(password_error)
    if new_password != new_password_confirm:
        errors.append("两次输入的密码不一致。")
    with get_connection() as connection:
        user = get_user(connection, user_id)
        if not user:
            return RedirectResponse(url="/admin/users", status_code=303)
        if not errors:
            errors = reset_user_password(
                connection,
                user_id=user_id,
                password=new_password,
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


@router.post("/admin/users/{user_id}/status")
def admin_user_status(
    request: Request,
    user_id: int,
    status_action: str = Form(""),
    admin_confirm_password: str = Form(""),
    confirm_delete: str = Form(""),
):
    return handle_user_status_action(
        request,
        user_id=user_id,
        status_action=status_action,
        admin_confirm_password=admin_confirm_password,
        confirm_delete=confirm_delete,
    )


@router.post("/admin/users/{user_id}/toggle-active")
def admin_user_toggle_active(
    request: Request,
    user_id: int,
    admin_confirm_password: str = Form(""),
):
    return handle_user_status_action(
        request,
        user_id=user_id,
        status_action="toggle_active",
        admin_confirm_password=admin_confirm_password,
        confirm_delete="",
    )


@router.post("/admin/users/{user_id}/delete")
def admin_user_delete(
    request: Request,
    user_id: int,
    confirm_password: str = Form(""),
):
    return handle_user_status_action(
        request,
        user_id=user_id,
        status_action="delete",
        admin_confirm_password=confirm_password,
        confirm_delete="1",
    )


def handle_user_status_action(
    request: Request,
    *,
    user_id: int,
    status_action: str,
    admin_confirm_password: str,
    confirm_delete: str,
):
    redirect = require_admin(request)
    if redirect:
        return redirect
    if status_action not in {"toggle_active", "delete"}:
        return render_user_action_error(request, user_id, "请选择有效账号操作。")
    current_user = get_current_user(request)
    if current_user and int(current_user["id"]) == user_id:
        message = "不能删除当前登录账号。" if status_action == "delete" else "不能禁用当前登录账号。"
        return render_user_action_error(request, user_id, message)
    if status_action == "delete" and not confirm_delete:
        return render_user_action_error(
            request,
            user_id,
            "请先确认：删除账号不会删除历史操作记录，历史记录将保留操作人姓名但不再关联账号。",
        )
    password_error = require_password_confirmation(request, admin_confirm_password)
    if password_error:
        return render_user_action_error(request, user_id, password_error)
    with get_connection() as connection:
        user = get_user(connection, user_id)
        if not user:
            return RedirectResponse(url="/admin/users", status_code=303)
        if status_action == "toggle_active":
            errors = set_user_active(
                connection,
                user_id=user_id,
                is_active=not bool(user["is_active"]),
            )
            action_type = "user_active_changed"
        else:
            errors = delete_user_and_detach_logs(connection, user_id=user_id)
            action_type = "user_deleted"
        if errors:
            return render_user_action_error(request, user_id, "；".join(errors))
        create_operation_log(
            connection,
            operator_name=session_display_name(request),
            action_type=action_type,
            note=format_user_action_note(user),
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


def format_user_action_note(user) -> str:
    return f"{user['username']} / {user['display_name']}"


def render_user_action_error(request: Request, user_id: int, error: str):
    with get_connection() as connection:
        user = get_user(connection, user_id)
    if not user:
        return render_delete_error(request, error)
    return render_user_form(
        request,
        user=user,
        values=dict(user),
        mode="edit",
        errors=[error],
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
