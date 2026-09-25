import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.controllers.deps import current_user, get_db, get_dialogue, page_number, render
from app.models.knowledge_entry import INTENT_LABELS
from app.schemas.user import UserOut
from app.services import dialogue_service
from app.services.dialogue_service import DialogueService
from app.services.errors import BusinessError, NotFoundError

router = APIRouter(prefix="/chat")


def _page(request: Request, user: UserOut, db: Session, conversation_id: int | None = None):
    try:
        conversation = dialogue_service.get_conversation(db, conversation_id, user.id) if conversation_id else None
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    conversations = dialogue_service.list_conversations(
        db, user.id, page_number(request.query_params.get("page", "1")), request.app.state.settings.page_size,
    )
    return render(
        request, "chat.html", user=user, active="chat", conversation=conversation, conversations=conversations,
        intent_labels=INTENT_LABELS,
    )


@router.get("")
def chat_page(request: Request, user: UserOut = Depends(current_user), db: Session = Depends(get_db)):
    return _page(request, user, db)


@router.get("/{conversation_id}")
def conversation_page(conversation_id: int, request: Request, user: UserOut = Depends(current_user), db: Session = Depends(get_db)):
    return _page(request, user, db, conversation_id)


@router.post("/conversations", status_code=201)
def create_conversation(user: UserOut = Depends(current_user), db: Session = Depends(get_db)):
    conversation_id = dialogue_service.start_conversation(db, user.id)
    return {"id": conversation_id, "url": f"/chat/{conversation_id}"}


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: int,
    request: Request,
    text: str = Body("", embed=True),
    user: UserOut = Depends(current_user),
    db: Session = Depends(get_db),
    dialogue: DialogueService = Depends(get_dialogue),
):
    try:
        dialogue.check(db, conversation_id, user.id, text)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except BusinessError as error:
        return JSONResponse({"detail": str(error)}, status_code=400)
    events = dialogue.stream_events(request.app.state.session_factory, conversation_id, user.id, text)
    return StreamingResponse(
        (json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )
