from __future__ import annotations

from app.agent.schemas import EvidenceItem, GuardrailCheck, SupportTicket, ToolResult
from app.config import CONFIDENCE_THRESHOLD


def required_identifiers(issue_type: str) -> list[str]:
    if issue_type in {"billing_refund", "billing_duplicate_charge", "payment_failure", "shipping_delay"}:
        return ["order_id"]
    if issue_type == "login_issue":
        return ["account_id"]
    return []


def find_missing_identifiers(ticket: SupportTicket, issue_type: str) -> list[str]:
    missing = []
    for field in required_identifiers(issue_type):
        if getattr(ticket, field, None) is None:
            missing.append(field)
    return missing


def compute_confidence(
    *,
    issue_type: str,
    doc_evidence: list[EvidenceItem],
    historical_evidence: list[EvidenceItem],
    tool_results: list[ToolResult],
    missing_information: list[str],
) -> float:
    confidence = 0.30
    if issue_type != "unknown":
        confidence += 0.10
    if doc_evidence:
        best_doc = max((item.score or 0 for item in doc_evidence), default=0)
        confidence += min(0.22, best_doc * 0.22)
    if historical_evidence:
        best_hist = max((item.score or 0 for item in historical_evidence), default=0)
        confidence += min(0.16, best_hist * 0.16)
    successful_tools = [tool for tool in tool_results if tool.status == "success"]
    failed_tools = [tool for tool in tool_results if tool.status == "failure"]
    if successful_tools:
        confidence += min(0.18, 0.09 * len(successful_tools))
    if not failed_tools:
        confidence += 0.06
    else:
        confidence -= min(0.18, 0.09 * len(failed_tools))
    if not missing_information:
        confidence += 0.08
    else:
        confidence -= min(0.24, 0.12 * len(missing_information))
    return round(max(0.0, min(1.0, confidence)), 2)


def run_guardrails(
    *,
    confidence: float,
    doc_evidence: list[EvidenceItem],
    missing_information: list[str],
    tool_results: list[ToolResult],
    policy_escalation_flags: list[str] | None = None,
) -> list[GuardrailCheck]:
    flags = policy_escalation_flags or []
    failures = [tool for tool in tool_results if tool.status == "failure"]
    return [
        GuardrailCheck(
            name="minimum_confidence",
            passed=confidence >= CONFIDENCE_THRESHOLD,
            details=f"confidence={confidence:.2f}; threshold={CONFIDENCE_THRESHOLD:.2f}",
        ),
        GuardrailCheck(
            name="documentation_evidence_present",
            passed=len(doc_evidence) > 0,
            details=f"documentation evidence count={len(doc_evidence)}",
        ),
        GuardrailCheck(
            name="required_identifiers_present",
            passed=len(missing_information) == 0,
            details="missing=" + (", ".join(missing_information) if missing_information else "none"),
        ),
        GuardrailCheck(
            name="no_tool_failures",
            passed=len(failures) == 0,
            details="failures=" + (", ".join(tool.tool_name for tool in failures) if failures else "none"),
        ),
        GuardrailCheck(
            name="policy_conditions_clear",
            passed=len(flags) == 0,
            details="flags=" + ("; ".join(flags) if flags else "none"),
        ),
    ]


def should_escalate(confidence: float, checks: list[GuardrailCheck]) -> bool:
    if confidence < CONFIDENCE_THRESHOLD:
        return True
    hard_failures = {
        "documentation_evidence_present",
        "required_identifiers_present",
        "no_tool_failures",
        "policy_conditions_clear",
    }
    return any((check.name in hard_failures and not check.passed) for check in checks)
