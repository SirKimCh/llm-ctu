import logging

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Role, User
from app.schemas.user import UserOut

logger = logging.getLogger(__name__)

ADMIN_FULL_NAME = "Quản trị hệ thống"
BCRYPT_MAX_BYTES = 72
TIMING_DECOY_HASH = bcrypt.hashpw(b"timing-decoy", bcrypt.gensalt()).decode()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode()
    if len(raw) > BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(raw, password_hash.encode())


def authenticate(db: Session, username: str, password: str) -> UserOut | None:
    name = normalize_username(username)
    user = db.scalar(select(User).where(User.username == name))
    if user is None:
        verify_password(password, TIMING_DECOY_HASH)
        logger.info("Đăng nhập thất bại: tên đăng nhập không tồn tại %r", name)
        return None
    if not verify_password(password, user.password_hash):
        logger.info("Đăng nhập thất bại: sai mật khẩu %r", name)
        return None
    logger.info("Đăng nhập thành công: %s", name)
    return UserOut.model_validate(user)


def get_user(db: Session, user_id: int) -> UserOut | None:
    user = db.get(User, user_id)
    return UserOut.model_validate(user) if user else None


def seed_admin(db: Session, settings: Settings) -> bool:
    name = normalize_username(settings.admin_username)
    if db.scalar(select(User.id).where(User.username == name)) is not None:
        return False
    db.add(User(username=name, password_hash=hash_password(settings.admin_password), full_name=ADMIN_FULL_NAME, role=Role.ADMIN))
    db.commit()
    logger.info("Đã tạo tài khoản quản trị đầu tiên: %s", name)
    return True
