from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from app.tools.historical_ticket_search import search_historical_tickets


class HistoricalTicketTool:
    """Historical ticket lookup via a local stdio MCP server."""

    name = "historical_ticket_lookup"
    backend = "mcp_stdio"

    def __init__(self, server_module: str = "app.mcp.ticket_server"):
        self.server_module = server_module

    def run(self, query: str, issue_type: str | None = None, product_area: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "resolution-agent", "version": "0.1.0"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": self.name,
                    "arguments": {
                        "query": query,
                        "issue_type": issue_type,
                        "product_area": product_area,
                        "limit": limit,
                    },
                },
            },
        ]
        payload = "\n".join(json.dumps(request) for request in requests) + "\n"
        try:
            completed = subprocess.run(
                [sys.executable, "-m", self.server_module],
                input=payload,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
            return self._extract_results(responses)
        except Exception:
            return search_historical_tickets(
                query=query,
                issue_type=issue_type,
                product_area=product_area,
                limit=limit,
            )

    def _extract_results(self, responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tools_list = next((item for item in responses if item.get("id") == 2), None)
        if not tools_list:
            raise ValueError("MCP tools/list response missing")
        tools = tools_list.get("result", {}).get("tools", [])
        if self.name not in {tool.get("name") for tool in tools}:
            raise ValueError(f"MCP server did not expose expected tool: {self.name}")
        tool_call = next((item for item in responses if item.get("id") == 3), None)
        if not tool_call:
            raise ValueError("MCP tools/call response missing")
        if "error" in tool_call:
            raise ValueError(tool_call["error"].get("message", "Unknown MCP error"))
        content = tool_call.get("result", {}).get("content", [])
        if not content:
            return []
        return list(content[0].get("json", []))


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "refund pending"
    print(HistoricalTicketTool().run(query=query))
