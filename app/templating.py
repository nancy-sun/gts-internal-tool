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


def format_compact_number(value) -> str:
    if value in ("", None):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


templates.env.filters["quantity"] = format_quantity
templates.env.filters["number_compact"] = format_compact_number
