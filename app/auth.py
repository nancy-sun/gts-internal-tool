from fastapi import Request
from fastapi.responses import RedirectResponse


SESSION_AUTH_KEY = "authenticated"
SESSION_OPERATOR_KEY = "operator_name"


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(SESSION_AUTH_KEY))


def require_auth(request: Request) -> RedirectResponse | None:
    if is_authenticated(request):
        return None
    return RedirectResponse(url="/login", status_code=303)


def get_session_operator_name(request: Request) -> str:
    return str(request.session.get(SESSION_OPERATOR_KEY) or "").strip()


def set_session_operator_name(request: Request, operator_name: str) -> str:
    cleaned_operator_name = operator_name.strip()
    if cleaned_operator_name:
        request.session[SESSION_OPERATOR_KEY] = cleaned_operator_name
    return cleaned_operator_name
