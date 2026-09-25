import logging
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Role, User
from app.schemas.page import Page
from app.schemas.user import UserOut
from app.services.auth_service import BCRYPT_MAX_BYTES, hash_password, normalize_username
from app.services.errors import BusinessError
from app.services.pagination import paginate
from app.services.text_service import normalize_text

logger = logging.getLogger(__name__)

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,50}$")
PASSWORD_MIN_LENGTH = 6
FULL_NAME_MAX_LENGTH = 100
MYSQL_DUPLICATE_KEY = 1062
DUPLICATE_USERNAME = "Tên đăng nhập đã tồn tại. Hãy chọn tên khác."
FORM_INVALID = "Chưa tạo được tài khoản. Hãy sửa các ô được đánh dấu bên dưới."


def list_users(db: Session, page: int, size: int) -> Page[UserOut]:
    statement = select(User).order_by(User.created_at.desc(), User.id.desc())
    return paginate(db, statement, page, size, UserOut.model_validate)


def _validate(username: str, password: str, full_name: str, role: str) -> dict[str, str]:
    errors = {}
    if not USERNAME_PATTERN.match(username):
        errors["username"] = "Tên đăng nhập chỉ gồm chữ thường không dấu, số và . _ -; hãy bỏ dấu, khoảng trắng và giữ độ dài 3–50 ký tự."
    if len(password) < PASSWORD_MIN_LENGTH or len(password.encode()) > BCRYPT_MAX_BYTES:
        errors["password"] = f"Mật khẩu cần từ {PASSWORD_MIN_LENGTH} đến {BCRYPT_MAX_BYTES} ký tự."
    if not full_name or len(full_name) > FULL_NAME_MAX_LENGTH:
        errors["full_name"] = f"Nhập họ tên, tối đa {FULL_NAME_MAX_LENGTH} ký tự."
    if role not in set(Role):
        errors["role"] = "Vai trò không hợp lệ. Chọn Người dùng hoặc Quản trị viên."
    return errors


def create_user(db: Session, username: str, password: str, full_name: str, role: str) -> UserOut:
    username = normalize_username(username)
    full_name = normalize_text(full_name)
    errors = _validate(username, password, full_name, role)
    if errors:
        raise BusinessError(FORM_INVALID, errors)
    user = User(username=username, password_hash=hash_password(password), full_name=full_name, role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if error.orig.args and error.orig.args[0] == MYSQL_DUPLICATE_KEY:
            raise BusinessError(FORM_INVALID, {"username": DUPLICATE_USERNAME}) from error
        raise
    logger.info("Đã tạo tài khoản %s (vai trò %s)", username, role)
    return UserOut.model_validate(user)
