from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    SESSION_LEGACY_KEY,
    SESSION_USER_ID_KEY,
    get_current_user,
    require_auth,
    set_login_session,
)
from app.config import get_settings
from app.database import get_connection
from app.services.users import (
    count_users,
    create_user,
    change_user_password,
    get_user_by_username,
    update_last_login,
    verify_user_password,
)
from app.templating import templates


router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    if request.session.get(SESSION_USER_ID_KEY):
        return RedirectResponse(url="/", status_code=303)
    with get_connection() as connection:
        if count_users(connection) == 0:
            return RedirectResponse(url="/setup-admin", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "error": None, "username": ""},
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    access_code: str = Form(""),
):
    settings = get_settings()
    with get_connection() as connection:
        if count_users(connection) == 0:
            return RedirectResponse(url="/setup-admin", status_code=303)

        user = get_user_by_username(connection, username)
        if user and user["is_active"] and verify_user_password(user, password):
            update_last_login(connection, int(user["id"]))
            connection.commit()
            set_login_session(request, user)
            return RedirectResponse(url="/", status_code=303)

    if settings.enable_legacy_access_code and access_code == settings.shared_access_code:
        request.session.clear()
        request.session["authenticated"] = True
        request.session["operator_name"] = "Legacy Access"
        request.session[SESSION_LEGACY_KEY] = True
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "error": "用户名或密码不正确，或账号已被禁用。",
            "username": username.strip(),
        },
        status_code=401,
    )


@router.get("/setup-admin")
def setup_admin_page(request: Request):
    with get_connection() as connection:
        if count_users(connection) > 0:
            return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "setup_admin.html",
        {"request": request, "error": None, "values": {}},
    )


@router.post("/setup-admin")
def setup_admin_submit(
    request: Request,
    username: str = Form(""),
    display_name: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
):
    values = {"username": username.strip(), "display_name": display_name.strip()}
    with get_connection() as connection:
        if count_users(connection) > 0:
            return RedirectResponse(url="/login", status_code=303)
        errors = []
        if password != confirm_password:
            errors.append("两次输入的密码不一致。")
        user_id = None
        if not errors:
            user_id, create_errors = create_user(
                connection,
                username=username,
                display_name=display_name,
                role="admin",
                password=password,
            )
            errors.extend(create_errors)
        if errors:
            return templates.TemplateResponse(
                request,
                "setup_admin.html",
                {"request": request, "error": "；".join(errors), "values": values},
                status_code=400,
            )
        user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        connection.commit()
    set_login_session(request, user)
    return RedirectResponse(url="/", status_code=303)


@router.get("/change-password")
def change_password_page(request: Request):
    redirect = require_auth(request)
    if redirect and redirect.headers.get("location") != "/change-password":
        return redirect
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "change_password.html",
        {"request": request, "error": None},
    )


@router.post("/change-password")
def change_password_submit(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
    confirm_new_password: str = Form(""),
):
    redirect = require_auth(request)
    if redirect and redirect.headers.get("location") != "/change-password":
        return redirect
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    errors = []
    if not verify_user_password(user, current_password):
        errors.append("当前密码不正确。")
    if not new_password:
        errors.append("请填写新密码。")
    confirmed_password = confirm_password or confirm_new_password
    if new_password != confirmed_password:
        errors.append("两次输入的新密码不一致。")
    if errors:
        return templates.TemplateResponse(
            request,
            "change_password.html",
            {"request": request, "error": "；".join(errors)},
            status_code=400,
        )
    with get_connection() as connection:
        errors = change_user_password(
            connection,
            user_id=int(user["id"]),
            new_password=new_password,
        )
        if errors:
            return templates.TemplateResponse(
                request,
                "change_password.html",
                {"request": request, "error": "；".join(errors)},
                status_code=400,
            )
        connection.commit()
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/logout")
def logout_get(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/forbidden")
def forbidden_page(request: Request):
    return templates.TemplateResponse(
        request,
        "forbidden.html",
        {"request": request},
        status_code=403,
    )
