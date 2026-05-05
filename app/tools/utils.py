from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def keyword_score(query: str, text: str) -> float:
    query_terms = {term.strip().lower() for term in query.replace("_", " ").split() if len(term.strip()) > 2}
    text_terms = {term.strip(".,:;!?()[]\"'").lower() for term in text.replace("_", " ").split()}
    if not query_terms:
        return 0.0
    overlap = query_terms.intersection(text_terms)
    return len(overlap) / len(query_terms)
