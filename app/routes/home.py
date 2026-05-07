from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app.config import BASE_DIR


router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@router.get("/")
def home(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("home.html", {"request": request})
