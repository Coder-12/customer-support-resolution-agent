from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app.config import PROMPT_VERSION, RUN_LOG_PATH


def new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:12]


@contextmanager
def track_run(run_id: str, extra: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    start = time.perf_counter()
    record: dict[str, Any] = {
        "run_id": run_id,
        "prompt_version": PROMPT_VERSION,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "estimated_cost_usd": 0.0,
        **(extra or {}),
    }
    try:
        yield record
        record["error"] = None
    except Exception as exc:
        record["error"] = repr(exc)
        raise
    finally:
        record["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        with RUN_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
