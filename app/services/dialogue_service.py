from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Conversation, Intent, Message
from app.models.knowledge_entry import INTENT_LABELS
from app.models.user import utc_now
from app.schemas.chat import ConversationDetail, ConversationOut, Turn
from app.schemas.page import Page
from app.services import search_service
from app.services.errors import BusinessError, NotFoundError
from app.services.llm_service import LlmService
from app.services.nlu_service import SLOTLESS_INTENTS, NluService
from app.services.pagination import paginate
from app.services.slot_service import MAJOR_CATALOG, extract_slots, follow_up_slots
from app.services.text_service import normalize_text, strip_accents

REQUIRED_SLOTS = {Intent.HOI_DIEM_CHUAN: "nganh_hoc", Intent.TU_VAN_LO_TRINH: "nganh_hoc"}
ASK_INTENT = "intent"
PERSISTED_KEYS = ("intent", "slots", "missing_slot")
TITLE_MAX_CHARS = 120
QUESTION_MAX_CHARS = 1000
MAJOR_EXAMPLES = 3
TOPICS = "điểm chuẩn, học phí, điều kiện tuyển sinh, quy chế học vụ hay lộ trình học"
GREETING = f"Chào bạn! Mình là trợ lý tư vấn tuyển sinh – đào tạo. Bạn có thể hỏi mình về {TOPICS} của từng ngành."
THANKS = "Không có gì đâu! Bạn cần hỏi thêm gì cứ nhắn mình nhé."
GOODBYE = "Tạm biệt bạn, chúc bạn một ngày tốt lành!"
NOT_FOUND_HINT = "Bạn thử hỏi ngành hoặc năm khác, hoặc liên hệ phòng tuyển sinh của trường nhé."
NOT_FOUND = "Không tìm thấy cuộc trò chuyện."
BUSY = "Trợ lý đang trả lời câu trước trong cuộc trò chuyện này. Đợi câu trả lời xong rồi gửi tiếp nhé."
MYSQL_LOCK_NOWAIT = 3572


class DialogueState(TypedDict, total=False):
    text: str
    nlu_intent: str
    confidence: float
    nlu_slots: dict
    turn_intent: str | None
    intent: str | None
    slots: dict
    missing_slot: str | None
    facts: list
    year_used: int | None
    reply: str
    sources: list[str]
    route: str


@dataclass(frozen=True)
class TurnContext:
    db: Session
    known_majors: list[str]


def _owned(conversation: Conversation | None, user_id: int) -> Conversation:
    if conversation is None or conversation.user_id != user_id:
        raise NotFoundError(NOT_FOUND)
    return conversation


def _locked(db: Session, conversation_id: int, user_id: int) -> Conversation:
    try:
        conversation = db.get(Conversation, conversation_id, with_for_update={"nowait": True})
    except OperationalError as error:
        if error.orig.args[0] == MYSQL_LOCK_NOWAIT:
            raise BusinessError(BUSY) from error
        raise
    return _owned(conversation, user_id)


def _question(text: str) -> str:
    text = normalize_text(text)
    if not text:
        raise BusinessError("Hãy nhập câu hỏi trước khi gửi.")
    if len(text) > QUESTION_MAX_CHARS:
        raise BusinessError(f"Mỗi câu hỏi tối đa {QUESTION_MAX_CHARS} ký tự, hãy rút gọn lại.")
    return text


def start_conversation(db: Session, user_id: int) -> int:
    conversation = Conversation(user_id=user_id, state={})
    db.add(conversation)
    db.commit()
    return conversation.id


def list_conversations(db: Session, user_id: int, page: int, size: int) -> Page[ConversationOut]:
    statement = select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    return paginate(db, statement, page, size, ConversationOut.model_validate)


def get_conversation(db: Session, conversation_id: int, user_id: int) -> ConversationDetail:
    return ConversationDetail.model_validate(_owned(db.get(Conversation, conversation_id), user_id))


def create(settings: Settings) -> "DialogueService":
    nlu = NluService.load(Path(settings.nlu_model_dir), settings.nlu_min_confidence)
    llm = LlmService(settings.ollama_base_url, settings.ollama_model, settings.ollama_timeout_seconds, settings.llm_temperature)
    return DialogueService(nlu, llm, settings)


class DialogueService:
    def __init__(self, nlu, llm, settings: Settings):
        self.nlu, self.llm, self.settings = nlu, llm, settings
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(DialogueState, context_schema=TurnContext)
        for name, node in {
            "nlu": self._nlu, "update_state": self._update_state, "greet": self._greet, "fallback": self._fallback,
            "ask_slot": self._ask_slot, "retrieve": self._retrieve, "not_found": self._not_found, "generate": self._generate,
        }.items():
            graph.add_node(name, node)
        graph.add_edge(START, "nlu")
        graph.add_edge("nlu", "update_state")
        graph.add_conditional_edges("update_state", self._route_after_update, ["greet", "fallback", "ask_slot", "retrieve"])
        graph.add_conditional_edges("retrieve", self._route_after_retrieve, ["not_found", "generate"])
        for terminal in ("greet", "fallback", "ask_slot", "not_found", "generate"):
            graph.add_edge(terminal, END)
        return graph.compile()

    def graph_mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()

    def check(self, db: Session, conversation_id: int, user_id: int, text: str) -> None:
        _question(text)
        _owned(db.get(Conversation, conversation_id), user_id)

    def reply(self, db: Session, conversation_id: int, user_id: int, text: str) -> Turn:
        *_, turn = self._turn(db, conversation_id, user_id, text)
        return turn

    def stream_events(self, session_factory: sessionmaker, conversation_id: int, user_id: int, text: str) -> Iterator[dict]:
        """Sự kiện NDJSON cho giao diện: token (từng mảnh câu trả lời) → done (Turn); hội thoại bận/không có ⇒ error."""
        with session_factory() as db:
            try:
                for item in self._turn(db, conversation_id, user_id, text):
                    yield {"type": "token", "text": item} if isinstance(item, str) else {"type": "done", **item.model_dump()}
            except (BusinessError, NotFoundError) as error:
                db.rollback()
                yield {"type": "error", "detail": str(error)}

    def _turn(self, db: Session, conversation_id: int, user_id: int, text: str) -> Iterator[str | Turn]:
        """Một lượt: khoá hội thoại (NOWAIT) → chạy đồ thị, phát từng mảnh của LLM → lưu state + 2 tin nhắn trong một commit."""
        text = _question(text)
        conversation = _locked(db, conversation_id, user_id)
        saved = conversation.state or {}
        final: DialogueState = {}
        for mode, chunk in self.graph.stream(
            {"text": text, **{key: saved.get(key) for key in PERSISTED_KEYS}},
            context=TurnContext(db, [*MAJOR_CATALOG, *search_service.known_majors(db)]),
            stream_mode=["custom", "values"],
        ):
            if mode == "custom":
                yield chunk
            else:
                final = chunk
        slots = final.get("slots") or {}
        sources = final.get("sources") or []
        conversation.state = {key: final.get(key) for key in PERSISTED_KEYS}
        conversation.title = conversation.title or text[:TITLE_MAX_CHARS]
        conversation.updated_at = utc_now()
        conversation.messages.extend([
            Message(role="user", content=text, intent=final.get("turn_intent"), confidence=final["confidence"], slots=slots),
            Message(role="assistant", content=final["reply"], route=final["route"], sources=sources or None),
        ])
        db.commit()
        yield Turn(
            reply=final["reply"], intent=final.get("turn_intent"), sources=sources, route=final["route"], state=conversation.state,
        )

    def _nlu(self, state: DialogueState) -> dict:
        result = self.nlu.predict(state["text"])
        return {"nlu_intent": result.intent, "confidence": result.confidence, "nlu_slots": result.slots}

    def _update_state(self, state: DialogueState, runtime: Runtime[TurnContext]) -> dict:
        """Câu nối tiếp chỉ gồm slot ⇒ giữ chủ đề cũ; đổi chủ đề ⇒ chỉ giữ ngành; slot mới ghi đè slot cũ."""
        known = runtime.context.known_majors
        follow_up = follow_up_slots(state["text"], known)
        if follow_up:
            intent, new_slots = state.get("intent"), follow_up
        elif state["nlu_intent"] in SLOTLESS_INTENTS:
            return {"turn_intent": state["nlu_intent"]}
        else:
            intent, new_slots = state["nlu_intent"], extract_slots(state["nlu_slots"], state["text"], known)
        slots = dict(state.get("slots") or {})
        if intent != state.get("intent"):
            slots = {name: value for name, value in slots.items() if name == "nganh_hoc"}
        slots.update(new_slots)
        required = REQUIRED_SLOTS.get(intent)
        missing = ASK_INTENT if intent is None else (required if required and required not in slots else None)
        return {"turn_intent": intent, "intent": intent, "slots": slots, "missing_slot": missing}

    def _route_after_update(self, state: DialogueState) -> str:
        if state.get("turn_intent") == Intent.CHAO_HOI:
            return "greet"
        if state.get("turn_intent") == Intent.NGOAI_PHAM_VI:
            return "fallback"
        return "ask_slot" if state.get("missing_slot") else "retrieve"

    def _route_after_retrieve(self, state: DialogueState) -> str:
        return "generate" if state["facts"] else "not_found"

    def _greet(self, state: DialogueState) -> dict:
        key = strip_accents(state["text"].lower())
        reply = THANKS if "cam on" in key else GOODBYE if "tam biet" in key else GREETING
        return {"reply": reply, "route": "greet"}

    def _fallback(self, state: DialogueState) -> dict:
        return {"reply": self.settings.out_of_scope_reply, "route": "fallback"}

    def _ask_slot(self, state: DialogueState, runtime: Runtime[TurnContext]) -> dict:
        major = state["slots"].get("nganh_hoc")
        if state["missing_slot"] == ASK_INTENT:
            about = f" về ngành {major}" if major else ""
            reply = f"Bạn muốn biết gì{about}: {TOPICS}?"
        else:
            examples = ", ".join(runtime.context.known_majors[:MAJOR_EXAMPLES]) or "Công nghệ thông tin"
            reply = f"Bạn muốn hỏi {INTENT_LABELS[state['intent']].lower()} của ngành nào? Ví dụ: {examples}."
        return {"reply": reply, "route": "ask_slot"}

    def _retrieve(self, state: DialogueState, runtime: Runtime[TurnContext]) -> dict:
        slots = state["slots"]
        question = " ".join(part for part in (state["text"], slots.get("phuong_thuc")) if part)
        result = search_service.search(
            runtime.context.db, question, state["intent"], slots.get("nganh_hoc"), slots.get("nam"),
            self.settings.search_top_k, self.settings.chunk_max_chars,
        )
        return {"facts": result.facts, "year_used": result.year_used}

    def _not_found(self, state: DialogueState) -> dict:
        slots = state["slots"]
        year = slots.get("nam") or state.get("year_used")
        topic = " ".join(part for part in (
            INTENT_LABELS[state["intent"]].lower(),
            f"ngành {slots['nganh_hoc']}" if slots.get("nganh_hoc") else None,
            f"năm {year}" if year else None,
        ) if part)
        return {"reply": f"Hiện mình chưa có thông tin về {topic}. {NOT_FOUND_HINT}", "route": "not_found"}

    def _generate(self, state: DialogueState) -> dict:
        facts = state["facts"]
        write = get_stream_writer()
        pieces = []
        for piece in self.llm.stream(state["text"], state["intent"], state["slots"], facts, state.get("year_used")):
            write(piece)
            pieces.append(piece)
        sources = list(dict.fromkeys(fact.source_url for fact in facts if fact.source_url))
        return {"reply": "".join(pieces), "sources": sources, "route": "generate"}
