import socket
from dataclasses import dataclass
from pathlib import Path

import httpx
import pymysql
from pydantic import ValidationError

from app.config import SECRET_KEY_PLACEHOLDER, Settings
from app.db import ensure_database, server_connection
from app.services.nlu_model import missing_artifacts

MYSQL_ACCESS_DENIED = 1045


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str
    exit_code: int = 0
    warning: bool = False

    def line(self) -> str:
        tag = "[LỖI]" if not self.ok else "[CẢNH BÁO]" if self.warning else "[OK]"
        return f"{tag} {self.name}: {self.message}"


def load_settings(env_path: str) -> tuple[Settings | None, CheckResult]:
    if not Path(env_path).exists():
        return None, CheckResult(
            ".env", False,
            "Chưa có file .env. Chạy: Copy-Item .env.example .env rồi kiểm tra lại các giá trị (docs/ENVIRONMENT.md §3).", 2,
        )
    try:
        settings = Settings(_env_file=env_path)
    except ValidationError as error:
        names = sorted({str(item["loc"][0]).upper() for item in error.errors()})
        return None, CheckResult(
            ".env", False, f"Thiếu hoặc sai biến trong .env: {', '.join(names)} (xem docs/ENVIRONMENT.md §3).", 2,
        )
    return settings, CheckResult(".env", True, "đọc đủ biến cấu hình")


def check_secret(settings: Settings) -> CheckResult:
    weak = settings.secret_key == SECRET_KEY_PLACEHOLDER or len(settings.secret_key) < 32
    if not weak:
        return CheckResult("SECRET_KEY", True, "đã đặt")
    if settings.is_production:
        return CheckResult(
            "SECRET_KEY", False,
            "SECRET_KEY còn giá trị mẫu hoặc ngắn hơn 32 ký tự — APP_ENV=production không cho phép. Sinh khoá mới: openssl rand -base64 48", 2,
        )
    return CheckResult("SECRET_KEY", True, "đang dùng giá trị mẫu — chỉ chấp nhận trên máy dev", warning=True)


def check_mysql(settings: Settings) -> CheckResult:
    address = f"{settings.db_host}:{settings.db_port}"
    try:
        with server_connection(settings) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
    except pymysql.err.OperationalError as error:
        if error.args and error.args[0] == MYSQL_ACCESS_DENIED:
            return CheckResult(
                "MySQL", False,
                f"MySQL từ chối đăng nhập tài khoản '{settings.db_user}'. Kiểm tra DB_USER/DB_PASSWORD trong .env.", 3,
            )
        return CheckResult(
            "MySQL", False,
            f"Không kết nối được MySQL tại {address}. Bật dịch vụ: Start-Service MySQL80 (PowerShell quyền Admin) "
            "hoặc services.msc → MySQL80 → Start.", 3,
        )
    return CheckResult("MySQL", True, f"MySQL {version} tại {address}")


def check_database(settings: Settings, name: str) -> CheckResult:
    try:
        created = ensure_database(settings, name)
    except (pymysql.err.MySQLError, ValueError) as error:
        return CheckResult("CSDL", False, f"Không tạo được CSDL {name}: {error}", 3)
    return CheckResult("CSDL", True, f"{name} {'đã tạo mới (utf8mb4_unicode_ci)' if created else 'đã có'}")


def check_ollama(settings: Settings, transport: httpx.BaseTransport | None = None) -> tuple[list[str], CheckResult]:
    try:
        with httpx.Client(base_url=settings.ollama_base_url, timeout=5, transport=transport) as client:
            response = client.get("/api/tags")
            response.raise_for_status()
            models = [model["name"] for model in response.json().get("models", [])]
    except (httpx.HTTPError, ValueError):
        return [], CheckResult(
            "Ollama", False,
            f"Ollama chưa chạy tại {settings.ollama_base_url}. Mở ứng dụng Ollama từ Start menu, "
            "hoặc chạy `ollama serve` ở một cửa sổ khác.", 4,
        )
    return models, CheckResult("Ollama", True, f"đang chạy tại {settings.ollama_base_url}")


def check_model(model: str, available: list[str]) -> CheckResult:
    if model in available:
        return CheckResult("Model", True, model)
    listed = ", ".join(available) or "(chưa có model nào)"
    return CheckResult(
        "Model", False,
        f"Không thấy model '{model}' trong Ollama. Model đang có: {listed}. "
        "Sửa OLLAMA_MODEL trong .env thành một model ở trên. Hệ thống không tự tải model.", 5,
    )


def check_nlu(settings: Settings) -> CheckResult:
    missing = missing_artifacts(Path(settings.nlu_model_dir))
    if missing:
        return CheckResult(
            "NLU", False,
            f"Chưa có model NLU tại {settings.nlu_model_dir} (thiếu: {', '.join(missing)}). "
            "Huấn luyện bằng notebooks/train_nlu.ipynb (docs/RUN_LOCAL.md §4) rồi chạy lại.", 6,
        )
    return CheckResult("NLU", True, f"model tại {settings.nlu_model_dir}")


def check_brightdata(settings: Settings) -> CheckResult:
    if settings.brightdata_api_token and settings.brightdata_zone:
        return CheckResult("Brightdata", True, f"đã cấu hình (zone {settings.brightdata_zone})")
    return CheckResult(
        "Brightdata", True,
        "chưa cấu hình BRIGHTDATA_API_TOKEN/BRIGHTDATA_ZONE — chức năng cào tạm tắt, import Excel vẫn dùng được.",
        warning=True,
    )


def check_port(settings: Settings) -> CheckResult:
    with socket.socket() as sock:
        try:
            sock.bind((settings.app_host, settings.app_port))
        except OSError:
            return CheckResult(
                "Cổng", False,
                f"Cổng {settings.app_port} đang bị chiếm. Đổi APP_PORT trong .env hoặc tắt tiến trình đang dùng cổng.", 7,
            )
    return CheckResult("Cổng", True, f"{settings.app_port} còn trống")


def service_checks(settings: Settings, transport: httpx.BaseTransport | None = None) -> list[CheckResult]:
    results = [check_mysql(settings)]
    if not results[-1].ok:
        return results
    models, ollama = check_ollama(settings, transport)
    results.append(ollama)
    if ollama.ok:
        results.append(check_model(settings.ollama_model, models))
    results.append(check_nlu(settings))
    return results


def run_checks(env_path: str = ".env", include_port: bool = True) -> list[CheckResult]:
    settings, loaded = load_settings(env_path)
    results = [loaded]
    if settings is None:
        return results
    steps = [
        lambda: [check_secret(settings)],
        lambda: service_checks(settings),
        lambda: [check_database(settings, settings.db_name)],
        lambda: [check_brightdata(settings)],
        lambda: [check_port(settings)] if include_port else [],
    ]
    for step in steps:
        batch = step()
        results.extend(batch)
        if not all(result.ok for result in batch):
            break
    return results
