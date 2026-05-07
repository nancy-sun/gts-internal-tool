from fastapi import Request
from fastapi.responses import RedirectResponse


SESSION_AUTH_KEY = "authenticated"


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(SESSION_AUTH_KEY))


def require_auth(request: Request) -> RedirectResponse | None:
    if is_authenticated(request):
        return None
    return RedirectResponse(url="/login", status_code=303)
