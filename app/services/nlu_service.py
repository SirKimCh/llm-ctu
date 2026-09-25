from dataclasses import dataclass, field
from pathlib import Path

import torch

from app.models.knowledge_entry import Intent
from app.services.nlu_model import MAX_LEN, encode_words, load_artifacts, pad_batch
from app.services.text_service import bio_to_spans, normalize_text, segment_lowercased

SLOTLESS_INTENTS = {Intent.CHAO_HOI, Intent.NGOAI_PHAM_VI}


@dataclass(frozen=True)
class NluResult:
    intent: str
    confidence: float
    slots: dict[str, str] = field(default_factory=dict)


class NluService:
    def __init__(self, model, tokenizer, labels: dict, min_confidence: float, device: str = "cpu"):
        self.model, self.tokenizer, self.labels = model, tokenizer, labels
        self.min_confidence, self.device = min_confidence, device

    @classmethod
    def load(cls, path: Path, min_confidence: float, device: str = "cpu") -> "NluService":
        model, tokenizer, labels = load_artifacts(path, device)
        return cls(model, tokenizer, labels, min_confidence, device)

    def predict(self, text: str) -> NluResult:
        normalized = normalize_text(text)
        tokens = segment_lowercased(normalized)
        if not any(char.isalnum() for token in tokens for char in token.word):
            return NluResult(Intent.NGOAI_PHAM_VI, 0.0)
        encoded = encode_words(self.tokenizer, [token.word for token in tokens], MAX_LEN)
        input_ids, attention_mask = pad_batch([encoded], self.tokenizer.pad_token_id)
        with torch.inference_mode():
            intent_logits, slot_logits = self.model(input_ids.to(self.device), attention_mask.to(self.device))
        confidence, index = intent_logits.softmax(-1)[0].max(0)
        intent = self.labels["intents"][int(index)]
        if float(confidence) < self.min_confidence:
            return NluResult(Intent.NGOAI_PHAM_VI, float(confidence))
        if intent in SLOTLESS_INTENTS:
            return NluResult(intent, float(confidence))
        slot_ids = slot_logits[0].argmax(-1).tolist()
        word_labels = [self.labels["slot_labels"][slot_ids[position]] for position in encoded.first_positions]
        slots = bio_to_spans(normalized, tokens[:len(word_labels)], word_labels)
        return NluResult(intent, float(confidence), slots)
