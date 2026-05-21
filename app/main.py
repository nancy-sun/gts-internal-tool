from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.auth import is_authenticated
from app.config import BASE_DIR, ensure_local_directories, get_settings
from app.database import initialize_database
from app.routes import (
    admin_users,
    auth,
    customs,
    data_quality,
    generate,
    home,
    hs_codes,
    logs,
    operator,
    products,
    search,
    suppliers,
    system,
    upload,
)
from app.services.operation_logging import reset_current_log_user, set_current_log_user
from app.services.temp_cleanup import cleanup_stale_preview_files
from app.templating import templates


def create_app() -> FastAPI:
    settings = get_settings()
    ensure_local_directories()
    initialize_database()
    cleanup_stale_preview_files()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        same_site="lax",
        https_only=settings.secure_cookies,
        max_age=None,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            if not is_authenticated(request):
                return RedirectResponse(url="/login", status_code=303)
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {"request": request, "missing_path": request.url.path},
                status_code=404,
            )
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.middleware("http")
    async def security_and_log_user_context(request, call_next):
        if settings.force_https and request.url.scheme != "https":
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            if forwarded_proto != "https":
                return RedirectResponse(str(request.url.replace(scheme="https")))
        user_id = request.session.get("user_id") if "session" in request.scope else None
        token = set_current_log_user(int(user_id) if user_id else None)
        try:
            response = await call_next(request)
        finally:
            reset_current_log_user(token)
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response

    app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
    app.include_router(auth.router)
    app.include_router(admin_users.router)
    app.include_router(customs.router)
    app.include_router(upload.router)
    app.include_router(generate.router)
    app.include_router(hs_codes.router)
    app.include_router(operator.router)
    app.include_router(products.router)
    app.include_router(suppliers.router)
    app.include_router(search.router)
    app.include_router(data_quality.router)
    app.include_router(logs.router)
    app.include_router(system.router)
    app.include_router(home.router)
    return app


app = create_app()
