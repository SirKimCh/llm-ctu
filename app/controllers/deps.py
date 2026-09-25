import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.schemas.user import UserOut
from app.services import auth_service, dialogue_service
from app.services.dialogue_service import DialogueService

VIETNAM_UTC_OFFSET = timedelta(hours=7)
DIALOGUE_LOCK = threading.Lock()
ROLE_LABELS = {"ADMIN": "Quản trị viên", "USER": "Người dùng"}


def vietnam_datetime(value: datetime) -> str:
    return (value + VIETNAM_UTC_OFFSET).strftime("%d/%m/%Y %H:%M")


APP_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=APP_DIR / "views")


def asset(path: str) -> str:
    return f"/static/{path}?v={int((APP_DIR / 'static' / path).stat().st_mtime)}"


templates.env.globals["asset"] = asset
templates.env.filters["vn_datetime"] = vietnam_datetime
templates.env.globals["ROLE_LABELS"] = ROLE_LABELS


class LoginRequired(Exception):
    pass


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


def optional_user(request: Request, db: Session = Depends(get_db)) -> UserOut | None:
    user_id = request.session.get("user_id")
    return auth_service.get_user(db, user_id) if user_id else None


def current_user(user: UserOut | None = Depends(optional_user)) -> UserOut:
    if user is None:
        raise LoginRequired()
    return user


def require_admin(user: UserOut = Depends(current_user)) -> UserOut:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Chỉ quản trị viên được dùng chức năng này.")
    return user


def get_dialogue(request: Request) -> DialogueService:
    state = request.app.state
    with DIALOGUE_LOCK:
        if state.dialogue is None:
            state.dialogue = dialogue_service.create(state.settings)
    return state.dialogue


def page_number(value: str) -> int:
    return int(value) if value.isdigit() and int(value) > 0 else 1


def attachment(filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode() or "tep"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def flash(request: Request, kind: str, text: str) -> None:
    request.session["flash"] = {"kind": kind, "text": text}


def render(request: Request, template: str, status_code: int = 200, **context):
    context["flash"] = request.session.pop("flash", None)
    return templates.TemplateResponse(request, template, context, status_code=status_code)
