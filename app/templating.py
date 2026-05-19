from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR


templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


ROLE_LABELS = {
    "admin": "管理员",
    "sales": "业务员",
    "merchandiser": "跟单",
}


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


def role_label(value) -> str:
    return ROLE_LABELS.get(str(value or ""), str(value or ""))


templates.env.filters["quantity"] = format_quantity
templates.env.filters["number_compact"] = format_compact_number
templates.env.filters["role_label"] = role_label
