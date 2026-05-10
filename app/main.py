from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, ensure_local_directories, get_settings
from app.database import initialize_database
from app.routes import auth, generate, home, hs_codes, logs, products, search, upload


def create_app() -> FastAPI:
    settings = get_settings()
    ensure_local_directories()
    initialize_database()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        same_site="lax",
        https_only=False,
        max_age=None,
    )
    app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
    app.include_router(auth.router)
    app.include_router(upload.router)
    app.include_router(generate.router)
    app.include_router(hs_codes.router)
    app.include_router(products.router)
    app.include_router(search.router)
    app.include_router(logs.router)
    app.include_router(home.router)
    return app


app = create_app()
