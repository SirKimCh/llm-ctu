from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.controllers.deps import flash, get_db, page_number, render, require_admin
from app.models import Role
from app.schemas.user import UserOut
from app.services import user_service
from app.services.errors import BusinessError

router = APIRouter(prefix="/admin/users")


def _page(request: Request, admin: UserOut, db: Session, page: int = 1, status_code: int = 200, **context):
    context.setdefault("form", {"role": Role.USER})
    context.setdefault("errors", {})
    users = user_service.list_users(db, page, request.app.state.settings.page_size)
    return render(request, "admin/users.html", status_code=status_code, user=admin, active="users", users=users, **context)


@router.get("")
def list_users(request: Request, page: str = "1", admin: UserOut = Depends(require_admin), db: Session = Depends(get_db)):
    return _page(request, admin, db, page_number(page))


@router.post("")
def create_user(
    request: Request,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    full_name: Annotated[str, Form()] = "",
    role: Annotated[str, Form()] = Role.USER,
    admin: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        created = user_service.create_user(db, username, password, full_name, role)
    except BusinessError as error:
        form = {"username": username, "full_name": full_name, "role": role}
        return _page(request, admin, db, status_code=400, form=form, errors=error.errors, error=str(error))
    flash(request, "success", f"Đã tạo tài khoản {created.username} cho {created.full_name}.")
    return RedirectResponse("/admin/users", status_code=303)
