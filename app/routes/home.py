from fastapi import APIRouter, Request

from app.auth import require_auth
from app.templating import templates


router = APIRouter()


@router.get("/")
def home(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("home.html", {"request": request})
