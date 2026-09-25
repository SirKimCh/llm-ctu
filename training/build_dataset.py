import json
import random
import re
from pathlib import Path

from app.models.knowledge_entry import Intent
from app.services.text_service import strip_accents
from training import templates

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "nlu"
SEED = 42
SAMPLES_PER_TEMPLATE = 6
ACCENTLESS_RATE = 0.35
LOWERCASE_RATE = 0.5
TRAIN_SHARE, DEV_SHARE = 0.8, 0.1
SLOT_LABELS = ("nganh_hoc", "nam", "phuong_thuc")
PLACEHOLDER = re.compile(r"\{(N2|N|Y|P)\}")
SLOT_OF = {"N": "nganh_hoc", "N2": "nganh_hoc", "Y": "nam", "P": "phuong_thuc"}


def _value(key: str, rng: random.Random) -> str:
    if key in ("N", "N2"):
        pool = templates.MAJOR_ABBREVIATIONS if rng.random() < 0.15 else templates.CTU_MAJORS_FROM_FEE_TABLE_2026
        return rng.choice(pool)
    return rng.choice(templates.YEARS if key == "Y" else templates.METHODS)


def _fill(template: str, rng: random.Random) -> tuple[str, list[dict]]:
    text, entities, cursor = "", [], 0
    for match in PLACEHOLDER.finditer(template):
        text += template[cursor:match.start()]
        value = _value(match.group(1), rng)
        entities.append({"start": len(text), "end": len(text) + len(value), "label": SLOT_OF[match.group(1)]})
        text += value
        cursor = match.end()
    return text + template[cursor:], entities


def _vary(text: str, rng: random.Random) -> str:
    if rng.random() < LOWERCASE_RATE:
        text = text.lower()
    if rng.random() < ACCENTLESS_RATE:
        text = strip_accents(text)
    return text


def _collect(rng: random.Random) -> dict[str, list[dict]]:
    by_intent: dict[str, list[dict]] = {intent.value: [] for intent in Intent}
    seen: set[str] = set()

    def add(intent: Intent, text: str, entities: list[dict]) -> None:
        if text.lower() not in seen:
            seen.add(text.lower())
            by_intent[intent.value].append({"text": text, "intent": intent.value, "entities": entities})

    for intent, patterns in templates.TEMPLATES.items():
        for pattern in patterns:
            for _ in range(SAMPLES_PER_TEMPLATE):
                framed = f"{rng.choice(templates.QUESTION_PREFIXES)}{pattern}{rng.choice(templates.QUESTION_ENDINGS)}"
                text, entities = _fill(framed, rng)
                add(intent, _vary(text, rng), entities)
    for greeting in templates.GREETINGS:
        for ending in templates.GREETING_ENDINGS:
            add(Intent.CHAO_HOI, _vary(f"{greeting}{ending}", rng), [])
    for question in templates.OUT_OF_SCOPE:
        for prefix in templates.QUESTION_PREFIXES:
            add(Intent.NGOAI_PHAM_VI, _vary(f"{prefix}{question}{rng.choice(templates.QUESTION_ENDINGS)}", rng), [])
    return by_intent


def build(seed: int = SEED) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    splits: dict[str, list[dict]] = {"train": [], "dev": [], "test": []}
    for rows in _collect(rng).values():
        rng.shuffle(rows)
        train_end = int(len(rows) * TRAIN_SHARE)
        dev_end = train_end + int(len(rows) * DEV_SHARE)
        splits["train"] += rows[:train_end]
        splits["dev"] += rows[train_end:dev_end]
        splits["test"] += rows[dev_end:]
    return splits


def labels() -> dict[str, list[str]]:
    return {
        "intents": [intent.value for intent in Intent],
        "slot_labels": ["O", *(f"{prefix}-{slot}" for slot in SLOT_LABELS for prefix in "BI")],
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for split, rows in build().items():
        lines = [json.dumps(row, ensure_ascii=False) for row in rows]
        (DATA_DIR / f"{split}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{split}: {len(rows)} câu")
    (DATA_DIR / "labels.json").write_text(json.dumps(labels(), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
