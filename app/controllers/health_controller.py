from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services import preflight_service

router = APIRouter()

REPORTED = {"MySQL": "db", "Ollama": "ollama", "Model": "model", "NLU": "nlu"}


@router.get("/health")
def health(request: Request):
    results = preflight_service.service_checks(request.app.state.settings)
    passed = {REPORTED[result.name] for result in results if result.ok}
    body = {key: "ok" if key in passed else "error" for key in REPORTED.values()}
    return JSONResponse(body, status_code=200 if len(passed) == len(REPORTED) else 503)
