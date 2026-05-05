from __future__ import annotations

from typing import Any

from app.config import DATA_DIR
from app.tools.utils import load_json


class LogLookupTool:
    name = "log_lookup"

    def __init__(self, path=DATA_DIR / "logs.json"):
        self.records = load_json(path)

    def run(self, account_id: str | None) -> dict[str, Any]:
        if not account_id:
            raise ValueError("account_id is required for log lookup")
        for record in self.records:
            if record.get("account_id") == account_id:
                return record
        raise LookupError(f"No logs found for account_id={account_id}")
