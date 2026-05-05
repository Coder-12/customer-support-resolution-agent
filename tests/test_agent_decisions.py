import os

os.environ["VECTOR_STORE_MODE"] = "fallback"

from app.agent.resolution_agent import CustomerSupportResolutionAgent
from app.agent.schemas import SupportTicket
from app.rag.ingest import ingest


def _has_failed_check(response, name: str) -> bool:
    for check in response.guardrail_checks:
        if check.name == name and not check.passed:
            return True
    return False


def test_refund_with_old_approved_date_and_unknown_processor_escalates():
    ingest(reset=True)
    agent = CustomerSupportResolutionAgent()
    response = agent.resolve(SupportTicket(
        subject="Refund still missing after 20 business days",
        description="Refund was approved a long time ago and still not received.",
        order_id="ORD-1005",
    ))
    assert response.decision == "escalate"
    assert _has_failed_check(response, "policy_conditions_clear")


def test_refund_with_unknown_order_escalates_on_tool_failure():
    ingest(reset=True)
    agent = CustomerSupportResolutionAgent()
    response = agent.resolve(SupportTicket(
        subject="Refund approved but missing",
        description="I still have not received my refund.",
        order_id="ORD-9999",
    ))
    assert response.decision == "escalate"
    assert _has_failed_check(response, "no_tool_failures")


def test_agent_keeps_limited_memory_for_related_tickets():
    ingest(reset=True)
    agent = CustomerSupportResolutionAgent()
    first = agent.resolve(SupportTicket(
        subject="Cannot log in",
        description="Session expired repeatedly.",
        customer_id="CUS-MEM-1",
        account_id="ACCT-1002",
    ))
    second = agent.resolve(SupportTicket(
        subject="Still cannot log in",
        description="Same issue after cache clear.",
        customer_id="CUS-MEM-1",
        account_id="ACCT-1002",
    ))
    assert first.ticket_analysis.memory_summary is None
    assert second.ticket_analysis.memory_summary is not None
    assert second.ticket_analysis.issue_type == "login_issue"
    assert second.decision == "respond"


def test_subscription_with_refund_language_stays_subscription():
    ingest(reset=True)
    agent = CustomerSupportResolutionAgent()
    response = agent.resolve(SupportTicket(
        subject="Cancel subscription and refund request",
        description="I want to cancel my subscription and understand whether the current billing period is refundable.",
        customer_id="CUS-SUB-1",
    ))
    assert response.ticket_analysis.issue_type == "subscription_cancellation"
    assert response.decision == "respond"
    assert [tool.tool_name for tool in response.tool_results] == ["historical_ticket_lookup"]


def test_charged_twice_classifies_as_duplicate_charge():
    ingest(reset=True)
    agent = CustomerSupportResolutionAgent()
    response = agent.resolve(SupportTicket(
        subject="Charged twice for renewal",
        description="I see two charges for one subscription renewal.",
        customer_id="CUS-DUP-1",
        order_id="ORD-9999",
    ))
    assert response.ticket_analysis.issue_type == "billing_duplicate_charge"
    assert response.decision == "escalate"
