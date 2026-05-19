from sqlite3 import Row

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.database import get_connection
from app.services.operation_logging import set_current_log_user
from app.services.users import get_user, verify_user_password


SESSION_AUTH_KEY = "authenticated"
SESSION_OPERATOR_KEY = "operator_name"
SESSION_USER_ID_KEY = "user_id"
SESSION_DISPLAY_NAME_KEY = "display_name"
SESSION_ROLE_KEY = "role"
SESSION_LEGACY_KEY = "legacy_access"

PASSWORD_CHANGE_ALLOWED_PATHS = {
    "/change-password",
    "/logout",
    "/static",
    "/healthz",
    "/robots.txt",
}


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(SESSION_USER_ID_KEY) or request.session.get(SESSION_AUTH_KEY))


def require_auth(request: Request) -> RedirectResponse | None:
    if is_authenticated(request):
        set_current_log_user(session_user_id(request))
        if must_change_password(request) and not password_change_path_allowed(request):
            return RedirectResponse(url="/change-password", status_code=303)
        return None
    return RedirectResponse(url="/login", status_code=303)


def require_login(request: Request) -> RedirectResponse | None:
    return require_auth(request)


def require_admin(request: Request) -> RedirectResponse | None:
    redirect = require_login(request)
    if redirect:
        return redirect
    if is_legacy_session(request):
        return RedirectResponse(url="/forbidden", status_code=303)
    if request.session.get(SESSION_ROLE_KEY) == "admin":
        return None
    return RedirectResponse(url="/forbidden", status_code=303)


def require_role(request: Request, roles: set[str] | tuple[str, ...] | list[str]) -> RedirectResponse | None:
    redirect = require_login(request)
    if redirect:
        return redirect
    if request.session.get(SESSION_ROLE_KEY) in roles:
        return None
    return RedirectResponse(url="/forbidden", status_code=303)


def is_legacy_session(request: Request) -> bool:
    return bool(request.session.get(SESSION_LEGACY_KEY))


def must_change_password(request: Request) -> bool:
    if is_legacy_session(request):
        return False
    current_user = get_current_user(request)
    return bool(current_user and current_user["must_change_password"])


def password_change_path_allowed(request: Request) -> bool:
    path = request.url.path
    return any(path == allowed or path.startswith(f"{allowed}/") for allowed in PASSWORD_CHANGE_ALLOWED_PATHS)


def get_current_user(request: Request) -> Row | None:
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not user_id:
        return None
    with get_connection() as connection:
        return get_user(connection, int(user_id))


def set_login_session(request: Request, user: Row) -> None:
    request.session.clear()
    request.session[SESSION_USER_ID_KEY] = int(user["id"])
    request.session[SESSION_DISPLAY_NAME_KEY] = user["display_name"]
    request.session[SESSION_ROLE_KEY] = user["role"]
    request.session[SESSION_OPERATOR_KEY] = user["display_name"]
    request.session[SESSION_AUTH_KEY] = True


def session_user_id(request: Request) -> int | None:
    user_id = request.session.get(SESSION_USER_ID_KEY)
    return int(user_id) if user_id else None


def session_display_name(request: Request) -> str:
    return str(request.session.get(SESSION_DISPLAY_NAME_KEY) or "").strip()


def get_session_operator_name(request: Request) -> str:
    display_name = session_display_name(request)
    if display_name and not is_legacy_session(request):
        return display_name
    return (
        str(request.session.get(SESSION_OPERATOR_KEY) or "").strip()
        or display_name
    )


def set_session_operator_name(request: Request, operator_name: str) -> str:
    display_name = session_display_name(request)
    if display_name and not is_legacy_session(request):
        request.session[SESSION_OPERATOR_KEY] = display_name
        return display_name
    cleaned_operator_name = operator_name.strip() or session_display_name(request)
    if cleaned_operator_name:
        request.session[SESSION_OPERATOR_KEY] = cleaned_operator_name
    return cleaned_operator_name


def require_password_confirmation(
    request: Request,
    submitted_password: str,
) -> str | None:
    current_user = get_current_user(request)
    if not current_user:
        return "请先登录。"
    if not verify_user_password(current_user, submitted_password):
        return "密码确认失败，操作已取消。"
    return None
