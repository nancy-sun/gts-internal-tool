from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, ensure_local_directories, get_settings
from app.database import initialize_database
from app.routes import (
    admin_users,
    auth,
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
        https_only=False,
        max_age=None,
    )

    @app.middleware("http")
    async def security_and_log_user_context(request, call_next):
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
