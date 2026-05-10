from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR


templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


def format_quantity(value) -> str:
    if value in ("", None):
        return ""
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return str(value)


templates.env.filters["quantity"] = format_quantity
