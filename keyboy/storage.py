from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import SearchDocument


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SEED_PATH = DATA_DIR / "corpus.json"
EVAL_PATH = DATA_DIR / "eval_queries.json"


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def load_documents(path: Path = SEED_PATH) -> list[SearchDocument]:
    rows = load_json(path, [])
    return [SearchDocument.from_dict(row) for row in rows]


def save_documents(documents: list[SearchDocument], path: Path = SEED_PATH) -> None:
    save_json(path, [doc.to_dict() for doc in documents])


def load_eval_queries(path: Path = EVAL_PATH) -> list[dict[str, Any]]:
    return load_json(path, [])

