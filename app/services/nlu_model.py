import json
from dataclasses import dataclass
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file
from torch import nn
from transformers import AutoConfig, AutoModel, AutoTokenizer

WEIGHTS_FILE = "model.safetensors"
LABELS_FILE = "labels.json"
REQUIRED_FILES = (WEIGHTS_FILE, LABELS_FILE, "config.json", "vocab.txt", "bpe.codes")
IGNORE_INDEX = -100
MAX_LEN = 64


class JointPhoBERT(nn.Module):
    def __init__(self, encoder: nn.Module, n_intents: int, n_slots: int, dropout: float = 0.1):
        super().__init__()
        self.encoder = encoder
        hidden = encoder.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.intent_head = nn.Linear(hidden, n_intents)
        self.slot_head = nn.Linear(hidden, n_slots)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        hidden = self.dropout(self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state)
        return self.intent_head(hidden[:, 0]), self.slot_head(hidden)


@dataclass(frozen=True)
class Encoded:
    input_ids: list[int]
    first_positions: list[int]


def encode_words(tokenizer, words: list[str], max_len: int) -> Encoded:
    input_ids, first_positions = [tokenizer.cls_token_id], []
    for word in words:
        pieces = tokenizer.encode(word, add_special_tokens=False) or [tokenizer.unk_token_id]
        if len(input_ids) + len(pieces) > max_len - 1:
            break
        first_positions.append(len(input_ids))
        input_ids.extend(pieces)
    return Encoded([*input_ids, tokenizer.sep_token_id], first_positions)


def pad_batch(batch: list[Encoded], pad_id: int) -> tuple[torch.Tensor, torch.Tensor]:
    width = max(len(item.input_ids) for item in batch)
    input_ids = torch.full((len(batch), width), pad_id, dtype=torch.long)
    attention_mask = torch.zeros((len(batch), width), dtype=torch.long)
    for row, item in enumerate(batch):
        input_ids[row, :len(item.input_ids)] = torch.tensor(item.input_ids)
        attention_mask[row, :len(item.input_ids)] = 1
    return input_ids, attention_mask


def save_artifacts(model: JointPhoBERT, tokenizer, labels: dict, path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    model.encoder.config.save_pretrained(path)
    tokenizer.save_pretrained(path)
    save_file({name: tensor.contiguous() for name, tensor in model.state_dict().items()}, path / WEIGHTS_FILE)
    (path / LABELS_FILE).write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")


def load_artifacts(path: Path, device: str = "cpu") -> tuple[JointPhoBERT, object, dict]:
    path = Path(path)
    labels = json.loads((path / LABELS_FILE).read_text(encoding="utf-8"))
    encoder = AutoModel.from_config(AutoConfig.from_pretrained(path))
    model = JointPhoBERT(encoder, len(labels["intents"]), len(labels["slot_labels"]))
    model.load_state_dict(load_file(path / WEIGHTS_FILE, device=device))
    return model.to(device).eval(), AutoTokenizer.from_pretrained(path), labels


def missing_artifacts(path: Path) -> list[str]:
    return sorted(name for name in REQUIRED_FILES if not (Path(path) / name).exists())
