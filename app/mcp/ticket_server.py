from __future__ import annotations

import json
import sys
from typing import Any

from app.tools.historical_ticket_search import search_historical_tickets

TOOL_NAME = "historical_ticket_lookup"
SERVER_NAME = "historical-ticket-mcp"
SERVER_VERSION = "0.1.0"


def _result(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _handle_request(payload: dict[str, Any]) -> dict[str, Any]:
    message_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if method == "initialize":
        return _result(message_id, {
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"tools": {}},
        })

    if method == "tools/list":
        return _result(message_id, {
            "tools": [{
                "name": TOOL_NAME,
                "description": "Retrieve similar historical support tickets from structured records.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "issue_type": {"type": ["string", "null"]},
                        "product_area": {"type": ["string", "null"]},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": ["query"],
                },
            }],
        })

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if name != TOOL_NAME:
            return _error(message_id, -32602, f"Unknown tool: {name}")
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return _error(message_id, -32602, "query must be a non-empty string")
        issue_type = arguments.get("issue_type")
        product_area = arguments.get("product_area")
        limit = int(arguments.get("limit", 3))
        results = search_historical_tickets(
            query=query,
            issue_type=issue_type,
            product_area=product_area,
            limit=limit,
        )
        return _result(message_id, {
            "content": [{
                "type": "json",
                "json": results,
            }],
            "isError": False,
        })

    return _error(message_id, -32601, f"Method not found: {method}")


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            response = _handle_request(payload)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
