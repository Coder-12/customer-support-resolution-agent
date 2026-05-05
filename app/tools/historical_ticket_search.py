from __future__ import annotations

from typing import Any

from app.config import DATA_DIR
from app.tools.utils import keyword_score, load_json


def load_historical_records(path=DATA_DIR / "historical_tickets.json") -> list[dict[str, Any]]:
    return load_json(path)


def search_historical_tickets(
    *,
    query: str,
    issue_type: str | None = None,
    product_area: str | None = None,
    limit: int = 3,
    path=DATA_DIR / "historical_tickets.json",
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for record in load_historical_records(path):
        haystack = " ".join([
            record.get("subject", ""),
            record.get("description", ""),
            record.get("resolution", ""),
            " ".join(record.get("tags", [])),
        ])
        score = keyword_score(query, haystack)
        if issue_type and record.get("issue_type") == issue_type:
            score += 0.35
        if product_area and record.get("product_area") == product_area:
            score += 0.15
        if score > 0:
            item = dict(record)
            item["similarity"] = round(min(score, 1.0), 4)
            scored.append(item)
    scored.sort(key=lambda row: row["similarity"], reverse=True)
    return scored[:limit]
