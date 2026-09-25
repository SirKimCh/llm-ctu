import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models.crawl_job import ACTIVE_STATUSES, CrawlJob, CrawlStatus
from app.models.knowledge_entry import KNOWLEDGE_INTENTS, KnowledgeEntry, SourceType
from app.models.user import utc_now
from app.services.errors import BusinessError
from app.services.html_page import html_to_markdown
from app.services.text_service import URL_PATTERN

logger = logging.getLogger(__name__)

NOT_CONFIGURED = "Chưa cấu hình Brightdata: điền BRIGHTDATA_API_TOKEN và BRIGHTDATA_ZONE trong .env rồi khởi động lại ứng dụng."
WAIT_FOR_JOB = "Chờ tiến trình đó xong rồi tạo tiến trình mới."
INTERRUPTED = "Ứng dụng khởi động lại khi đang cào. Hãy tạo lại tiến trình cho các trang chưa xong."
HEADING = "# "
NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*\.?\s")
TABLE_SEPARATOR = re.compile(r"^\|[\s:|\-]+\|$")
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
STATUS_LABELS = {
    CrawlStatus.PENDING: "Đang chờ",
    CrawlStatus.RUNNING: "Đang cào",
    CrawlStatus.DONE: "Hoàn tất",
    CrawlStatus.FAILED: "Thất bại",
}
MIN_BLOCK_CHARS = 40
TITLE_MAX_LENGTH = 230


class CrawlError(Exception):
    pass


@dataclass(frozen=True)
class Chunk:
    title: str
    content: str


@dataclass
class _Block:
    section: str | None
    text: str
    is_table: bool


def _blocks(markdown: str) -> tuple[str | None, list[_Block]]:
    page_title, section, blocks = None, None, []
    for text in markdown.split("\n\n"):
        if text.startswith(HEADING):
            section = text.removeprefix(HEADING)
            page_title = page_title or section
            continue
        page_title = page_title or text
        blocks.append(_Block(section, text, text.startswith("|")))
    return page_title, blocks


def _kept(blocks: list[_Block]) -> list[_Block]:
    kept, prefix = [], ""
    for block in blocks:
        if block.is_table or len(block.text) >= MIN_BLOCK_CHARS:
            text = f"{prefix}\n{block.text}" if prefix and not block.is_table else block.text
            kept.append(_Block(block.section, text, block.is_table))
            prefix = ""
        elif NUMBERED_HEADING.match(block.text):
            prefix = block.text
    return kept


def _pack(parts: list[str], separator: str, limit: int) -> list[str]:
    parts = [part[i:i + limit] for part in parts for i in range(0, len(part), limit)]
    pieces, current = [], ""
    for part in parts:
        candidate = f"{current}{separator}{part}" if current else part
        if len(candidate) > limit:
            pieces.append(current)
            candidate = part
        current = candidate
    return [*pieces, current] if current else pieces


def _pieces(block: _Block, max_chars: int) -> list[str]:
    if len(block.text) <= max_chars:
        return [block.text]
    if not block.is_table:
        return _pack(SENTENCE_END.split(block.text), " ", max_chars)
    lines = block.text.split("\n")
    header_size = 2 if len(lines) > 1 and TABLE_SEPARATOR.match(lines[1]) else 1
    header = "\n".join(lines[:header_size])
    if len(header) * 2 > max_chars:
        return _pack(lines, "\n", max_chars)
    return [f"{header}\n{piece}" for piece in _pack(lines[header_size:], "\n", max_chars - len(header) - 1)]


def split_page(html: str, max_chars: int) -> list[Chunk]:
    page_title, blocks = _blocks(html_to_markdown(html))
    grouped: list[tuple[str | None, str]] = []
    for block in _kept(blocks):
        for piece in _pieces(block, max_chars):
            if grouped and grouped[-1][0] == block.section and len(grouped[-1][1]) + 2 + len(piece) <= max_chars:
                grouped[-1] = (block.section, f"{grouped[-1][1]}\n\n{piece}")
            else:
                grouped.append((block.section, piece))
    total = len(grouped)
    chunks = []
    for index, (section, content) in enumerate(grouped, start=1):
        base = (section or page_title or "Trang web")[:TITLE_MAX_LENGTH]
        chunks.append(Chunk(f"{base} ({index}/{total})" if total > 1 else base, content))
    return chunks


def parse_urls(text: str, max_urls: int) -> list[str]:
    urls: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        url = line.strip()
        if not url:
            continue
        if not URL_PATTERN.match(url):
            raise BusinessError(f"Dòng {number}: “{url}” không phải đường dẫn http:// hoặc https:// hợp lệ.")
        if url not in urls:
            urls.append(url)
    if not urls:
        raise BusinessError("Nhập ít nhất một đường dẫn, mỗi dòng một đường dẫn.")
    if len(urls) > max_urls:
        raise BusinessError(f"Mỗi lần cào tối đa {max_urls} đường dẫn; bạn đang nhập {len(urls)}.")
    return urls


def launch(target: Callable, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True, name="crawl-job").start()


def start_job(
    db: Session, settings: Settings, urls_text: str, intent: str, user_id: int,
    session_factory: sessionmaker, transport: httpx.BaseTransport | None = None,
) -> int:
    if not (settings.brightdata_api_token and settings.brightdata_zone):
        raise BusinessError(NOT_CONFIGURED)
    urls = parse_urls(urls_text, settings.crawl_max_urls)
    running = db.scalar(select(CrawlJob.id).where(CrawlJob.status.in_(ACTIVE_STATUSES)))
    if running:
        raise BusinessError(f"Đang có tiến trình cào chạy (#{running}). {WAIT_FOR_JOB}")
    job = CrawlJob(urls=urls, intent=intent if intent in KNOWLEDGE_INTENTS else None, total=len(urls), created_by=user_id)
    db.add(job)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise BusinessError(f"Đang có tiến trình cào chạy. {WAIT_FOR_JOB}") from error
    logger.info("Tạo tiến trình cào #%s: %s đường dẫn bởi user %s", job.id, len(urls), user_id)
    launch(run_job, session_factory, settings, job.id, transport)
    return job.id


def _fetch_page(client: httpx.Client, settings: Settings, url: str) -> str:
    response = client.post(
        settings.brightdata_api_url,
        headers={"Authorization": f"Bearer {settings.brightdata_api_token}"},
        json={"zone": settings.brightdata_zone, "url": url, "format": "raw"},
    )
    response.raise_for_status()
    target_status = response.headers.get("x-brd-status-code")
    if target_status and target_status != "200":
        raise CrawlError(f"Trang nguồn trả mã HTTP {target_status}")
    return response.text


def _reason(error: Exception, settings: Settings) -> str:
    if isinstance(error, CrawlError):
        return str(error)
    if isinstance(error, httpx.TimeoutException):
        return f"Hết thời gian chờ Brightdata (quá {settings.crawl_timeout_seconds} giây)."
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403):
        return (f"Brightdata từ chối truy cập (HTTP {error.response.status_code}). "
                "Kiểm tra BRIGHTDATA_API_TOKEN và BRIGHTDATA_ZONE trong .env.")
    if isinstance(error, httpx.HTTPStatusError):
        return f"Brightdata trả mã lỗi HTTP {error.response.status_code}"
    if isinstance(error, httpx.HTTPError):
        return "Không kết nối được Brightdata."
    logger.exception("Lỗi không xác định khi cào trang")
    return "Lỗi không xác định khi lưu trang (xem log máy chủ)."


def _crawl_url(db: Session, client: httpx.Client, settings: Settings, job: CrawlJob, url: str) -> None:
    chunks = split_page(_fetch_page(client, settings, url), settings.chunk_max_chars)
    if not chunks:
        raise CrawlError("Trang không có nội dung văn bản dùng được.")
    db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.source_type == SourceType.CRAWL, KnowledgeEntry.source_url == url))
    db.add_all(
        KnowledgeEntry(
            intent=job.intent, title=chunk.title, content=chunk.content, source_type=SourceType.CRAWL,
            source_url=url, crawl_job_id=job.id, created_by=job.created_by,
        )
        for chunk in chunks
    )


def run_job(session_factory: sessionmaker, settings: Settings, job_id: int, transport: httpx.BaseTransport | None = None) -> None:
    with session_factory() as db:
        try:
            job = db.get(CrawlJob, job_id)
            job.status = CrawlStatus.RUNNING
            db.commit()
            with httpx.Client(timeout=settings.crawl_timeout_seconds, transport=transport) as client:
                for url in list(job.urls):
                    try:
                        _crawl_url(db, client, settings, job, url)
                        job.done += 1
                    except Exception as error:
                        db.rollback()
                        job = db.get(CrawlJob, job_id)
                        job.failed += 1
                        job.errors = [*job.errors, {"url": url, "message": _reason(error, settings)}]
                    db.commit()
            job.status = CrawlStatus.DONE if job.done else CrawlStatus.FAILED
        except Exception:
            logger.exception("Tiến trình cào #%s dừng bất thường", job_id)
            db.rollback()
            job = db.get(CrawlJob, job_id)
            job.status = CrawlStatus.FAILED
        job.finished_at = utc_now()
        job.active_slot = None
        db.commit()
        logger.info("Tiến trình cào #%s kết thúc: %s (xong %s, lỗi %s)", job_id, job.status, job.done, job.failed)


def _summary(job: CrawlJob) -> str:
    return f"{STATUS_LABELS[job.status]}: đã xử lý {job.done + job.failed}/{job.total} trang, {job.failed} lỗi."


def _to_json(job: CrawlJob) -> dict:
    return {
        "id": job.id, "status": job.status, "total": job.total, "done": job.done, "failed": job.failed,
        "errors": job.errors, "active": job.status in ACTIVE_STATUSES, "summary": _summary(job),
    }


def get_job(db: Session, job_id: int) -> dict | None:
    job = db.get(CrawlJob, job_id)
    return _to_json(job) if job else None


def latest_job(db: Session) -> dict | None:
    job = db.scalar(select(CrawlJob).order_by(CrawlJob.id.desc()).limit(1))
    return _to_json(job) if job else None


def recover_interrupted(db: Session) -> int:
    result = db.execute(
        update(CrawlJob)
        .where(CrawlJob.status.in_(ACTIVE_STATUSES))
        .values(status=CrawlStatus.FAILED, finished_at=utc_now(), active_slot=None, errors=[{"url": "", "message": INTERRUPTED}])
    )
    db.commit()
    return result.rowcount
