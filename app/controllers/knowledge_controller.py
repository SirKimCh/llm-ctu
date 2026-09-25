from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.controllers.deps import attachment, flash, get_db, page_number, render, require_admin
from app.models.knowledge_entry import INTENT_LABELS
from app.schemas.user import UserOut
from app.services import crawl_service, knowledge_import_service, knowledge_service
from app.services.errors import BusinessError

router = APIRouter(prefix="/admin/knowledge")

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _page(request: Request, admin: UserOut, db: Session, status_code: int = 200, **context):
    settings = request.app.state.settings
    params = request.query_params
    filters = {"intent": params.get("intent", ""), "q": params.get("q", "")}
    entries = knowledge_service.list_entries(
        db, page_number(params.get("page", "1")), settings.page_size, filters["intent"] or None, filters["q"] or None,
    )
    context.setdefault("crawl_form", {"urls": "", "intent": ""})
    return render(
        request, "admin/knowledge.html", status_code=status_code, user=admin, active="knowledge",
        entries=entries, filters=filters, intents=INTENT_LABELS, upload_max_mb=settings.upload_max_mb,
        crawl_enabled=bool(settings.brightdata_api_token and settings.brightdata_zone),
        crawl_max_urls=settings.crawl_max_urls, job=crawl_service.latest_job(db), **context,
    )


@router.get("")
def knowledge_page(request: Request, admin: UserOut = Depends(require_admin), db: Session = Depends(get_db)):
    return _page(request, admin, db)


@router.get("/template")
def download_template(admin: UserOut = Depends(require_admin)):
    return Response(
        knowledge_import_service.build_template(),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": attachment(knowledge_import_service.TEMPLATE_FILENAME)},
    )


@router.post("/import")
def import_knowledge(
    request: Request,
    file: UploadFile | None = File(None),
    admin: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    max_mb = request.app.state.settings.upload_max_mb
    if file is None or not file.filename:
        return _page(request, admin, db, status_code=400, import_error="Chọn tệp Excel .xlsx để nhập.")
    data = file.file.read(max_mb * knowledge_import_service.MEGABYTE + 1)
    try:
        result = knowledge_import_service.import_file(db, data, admin.id, max_mb)
    except BusinessError as error:
        return _page(request, admin, db, status_code=400, import_error=str(error))
    if result.errors:
        return _page(request, admin, db, status_code=400, import_result=result)
    flash(request, "success", result.message)
    return RedirectResponse("/admin/knowledge", status_code=303)


@router.post("/crawl-jobs")
def create_crawl_job(
    request: Request,
    urls: Annotated[str, Form()] = "",
    intent: Annotated[str, Form()] = "",
    admin: UserOut = Depends(require_admin),
    db: Session = Depends(get_db),
):
    state = request.app.state
    try:
        job_id = crawl_service.start_job(db, state.settings, urls, intent, admin.id, state.session_factory, state.http_transport)
    except BusinessError as error:
        return _page(request, admin, db, status_code=400, crawl_error=str(error), crawl_form={"urls": urls, "intent": intent})
    return RedirectResponse(f"/admin/knowledge?job={job_id}", status_code=303)


@router.get("/crawl-jobs/{job_id}")
def crawl_job_status(job_id: int, admin: UserOut = Depends(require_admin), db: Session = Depends(get_db)):
    job = crawl_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình cào.")
    return job
