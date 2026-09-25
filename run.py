import sys

from app.services.preflight_service import run_checks


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", line_buffering=True)
    print("Kiểm tra môi trường trước khi chạy…")
    results = run_checks(".env")
    for result in results:
        print(" ", result.line())
    failed = next((result for result in results if not result.ok), None)
    if failed:
        print(f"\nDừng lại: sửa mục [LỖI] ở trên rồi chạy lại `uv run run.py` (mã thoát {failed.exit_code}).")
        return failed.exit_code

    import uvicorn

    from app.config import get_settings

    settings = get_settings()
    print(f"\nMở trình duyệt: http://{settings.app_host}:{settings.app_port}   (đăng nhập bằng tài khoản quản trị trong .env)")
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
