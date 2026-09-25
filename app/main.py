import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, get_settings
from app.controllers import auth_controller, chat_controller, health_controller, knowledge_controller, user_controller
from app.controllers.deps import LoginRequired, templates
from app.db import Base, make_engine
from app.services import auth_service, crawl_service

APP_DIR = Path(__file__).resolve().parent
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ERROR_PAGES = {
    403: ("Bạn không có quyền xem trang này", "Trang này chỉ dành cho quản trị viên. Hãy quay về trang chủ."),
    404: ("Không tìm thấy trang", "Đường dẫn không tồn tại hoặc đã bị đổi. Hãy quay về trang chủ."),
}


def wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine = make_engine(settings)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        with session_factory() as db:
            auth_service.seed_admin(db, settings)
            crawl_service.recover_interrupted(db)
        yield
        engine.dispose()

    app = FastAPI(title="llm-ctu", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.http_transport = None
    app.state.dialogue = None

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="llmctu_session",
        max_age=settings.session_max_age_minutes * 60,
        same_site="lax",
        https_only=settings.session_https_only,
    )

    @app.middleware("http")
    async def reject_cross_site_writes(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in SAFE_METHODS and origin and urlsplit(origin).netloc != request.headers.get("host"):
            return PlainTextResponse("Yêu cầu bị từ chối: gửi từ trang web khác.", status_code=403)
        return await call_next(request)

    @app.exception_handler(LoginRequired)
    async def login_required(request: Request, exc: LoginRequired):
        if wants_html(request):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "Bạn cần đăng nhập."}, status_code=401)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if wants_html(request) and exc.status_code in ERROR_PAGES:
            heading, detail = ERROR_PAGES[exc.status_code]
            context = {"status": exc.status_code, "heading": heading, "detail": detail, "flash": None}
            return templates.TemplateResponse(request, "error.html", context, status_code=exc.status_code)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    app.include_router(health_controller.router)
    app.include_router(auth_controller.router)
    app.include_router(user_controller.router)
    app.include_router(knowledge_controller.router)
    app.include_router(chat_controller.router)
    return app

