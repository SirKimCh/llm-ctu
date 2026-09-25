from collections.abc import Callable
from math import ceil

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.schemas.page import Page


def paginate[T](db: Session, statement: Select, page: int, size: int, to_item: Callable[[object], T]) -> Page[T]:
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    pages = max(1, ceil(total / size))
    page = min(max(page, 1), pages)
    rows = db.scalars(statement.limit(size).offset((page - 1) * size))
    return Page(items=[to_item(row) for row in rows], page=page, pages=pages, total=total)
