from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.resolution_agent import CustomerSupportResolutionAgent
from app.agent.schemas import SupportTicket

TEST_CASES_PATH = Path(__file__).with_name("test_cases.json")


def contains_all(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def contains_none(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return all(term.lower() not in lowered for term in terms)


def evaluate_case(agent: CustomerSupportResolutionAgent, case: dict[str, Any]) -> dict[str, Any]:
    response = agent.resolve(SupportTicket(**case["ticket"]))
    output_text = " ".join([
        response.draft_response or "",
        response.escalation.model_dump_json() if response.escalation else "",
    ])
    tools_called = [tool.tool_name for tool in response.tool_results]
    checks = {
        "decision": response.decision == case["expected_decision"],
        "expected_tools": all(tool in tools_called for tool in case.get("expected_tools", [])),
        "must_include": contains_all(output_text, case.get("must_include", [])),
        "must_not_include": contains_none(output_text, case.get("must_not_include", [])),
        "has_evidence": len(response.evidence) > 0,
        "confidence_valid": 0 <= response.confidence <= 1,
    }
    return {
        "id": case["id"],
        "passed": all(checks.values()),
        "checks": checks,
        "decision": response.decision,
        "confidence": response.confidence,
        "tools_called": tools_called,
    }


def run_evaluation() -> dict[str, Any]:
    cases = json.loads(TEST_CASES_PATH.read_text(encoding="utf-8"))
    agent = CustomerSupportResolutionAgent()
    results = [evaluate_case(agent, case) for case in cases]
    passed = sum(1 for result in results if result["passed"])
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "score": round(passed / len(results), 4) if results else 0,
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluation(), indent=2))
