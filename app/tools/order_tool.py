from __future__ import annotations

from typing import Any

from app.config import DATA_DIR
from app.tools.utils import load_json


class OrderStatusTool:
    name = "order_status_lookup"

    def __init__(self, path=DATA_DIR / "orders.json"):
        self.records = load_json(path)

    def run(self, order_id: str | None) -> dict[str, Any]:
        if not order_id:
            raise ValueError("order_id is required for order status lookup")
        for record in self.records:
            if record.get("order_id") == order_id:
                return record
        raise LookupError(f"No order found for order_id={order_id}")
