import re

import pymysql
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings

DATABASE_NAME = re.compile(r"^\w+$")
DISPOSABLE_PREFIX = "llm_ctu"


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings) -> Engine:
    url = URL.create(
        "mysql+pymysql",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


def server_connection(settings: Settings) -> pymysql.Connection:
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        charset="utf8mb4",
        connect_timeout=5,
        autocommit=True,
    )


def _checked(name: str) -> str:
    if not DATABASE_NAME.match(name):
        raise ValueError(f"Tên CSDL không hợp lệ: {name}")
    return name


def ensure_database(settings: Settings, name: str) -> bool:
    name = _checked(name)
    with server_connection(settings) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (name,))
        if cursor.fetchone():
            return False
        cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        return True


def drop_database(settings: Settings, name: str) -> None:
    name = _checked(name)
    if not name.startswith(DISPOSABLE_PREFIX):
        raise ValueError(f"Chỉ được xoá CSDL của dự án ({DISPOSABLE_PREFIX}*), không xoá: {name}")
    with server_connection(settings) as conn, conn.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
