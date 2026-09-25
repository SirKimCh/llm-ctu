from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.controllers.deps import current_user, get_db, optional_user, render
from app.schemas.user import UserOut
from app.services import auth_service

router = APIRouter()

WRONG_CREDENTIALS = "Tên đăng nhập hoặc mật khẩu không đúng."


@router.get("/login")
def login_page(request: Request, user: UserOut | None = Depends(optional_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html")


@router.post("/login")
def login(
    request: Request,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    user = auth_service.authenticate(db, username, password)
    if user is None:
        return render(request, "login.html", status_code=400, error=WRONG_CREDENTIALS, username=username)
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/")
def home(user: UserOut = Depends(current_user)):
    return RedirectResponse("/chat", status_code=303)
