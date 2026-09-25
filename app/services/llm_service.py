import json
import logging
from collections.abc import Iterator
from dataclasses import asdict

import httpx

from app.services.search_service import Fact

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Bạn là trợ lý tư vấn tuyển sinh và đào tạo của trường đại học. "
    "Chỉ trả lời dựa trên DỮ KIỆN được cung cấp; không thêm số liệu, tên ngành, mốc thời gian hay thông tin nào ngoài DỮ KIỆN. "
    "Nếu DỮ KIỆN không đủ để trả lời thì nói rõ là hiện chưa có thông tin đó. "
    "Giữ nguyên các con số như trong DỮ KIỆN. Nếu có NĂM_DỮ_LIỆU thì nói rõ số liệu thuộc năm đó. "
    "Trả lời bằng tiếng Việt, ngắn gọn, thân thiện, xưng \"mình\", không dùng tiêu đề markdown."
)
BUSY_PREFIX = "Hệ thống sinh câu trả lời đang bận, mình gửi bạn dữ kiện tìm được:"


def build_messages(question: str, intent: str, slots: dict, facts: list[Fact], year_used: int | None) -> list[dict]:
    payload = {
        "CÂU_HỎI": question,
        "CHỦ_ĐỀ": intent,
        "THÔNG_TIN_ĐÃ_BIẾT": slots,
        "NĂM_DỮ_LIỆU": year_used,
        "DỮ_KIỆN": [{key: value for key, value in asdict(fact).items() if key != "source_url"} for fact in facts],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)},
    ]


def facts_as_list(facts: list[Fact]) -> str:
    return "\n".join([BUSY_PREFIX, *(f"- {fact.title}: {fact.content}" for fact in facts)])


class LlmService:
    def __init__(self, base_url: str, model: str, timeout: float, temperature: float, transport: httpx.BaseTransport | None = None):
        self.base_url, self.model, self.timeout, self.temperature, self.transport = base_url, model, timeout, temperature, transport

    def stream(self, question: str, intent: str, slots: dict, facts: list[Fact], year_used: int | None) -> Iterator[str]:
        """Từng mảnh câu trả lời của Ollama; lỗi hoặc câu rỗng ⇒ mảnh cuối là danh sách dữ kiện (không mất câu trả lời)."""
        body = {
            "model": self.model,
            "stream": True,
            "options": {"temperature": self.temperature},
            "messages": build_messages(question, intent, slots, facts, year_used),
        }
        started = False
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout, transport=self.transport) as client:
                with client.stream("POST", "/api/chat", json=body) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line.strip():
                            continue
                        piece = json.loads(line)["message"]["content"]
                        if piece and (started or piece.strip()):
                            started = True
                            yield piece
            if not started:
                raise ValueError("empty")
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
            logger.warning("Ollama lỗi, trả dữ kiện dạng liệt kê: %s", type(error).__name__)
            yield ("\n\n" if started else "") + facts_as_list(facts)
