from __future__ import annotations

from app.agent.schemas import SupportTicket


def classify_issue(ticket: SupportTicket) -> tuple[str, str]:
    text = f"{ticket.subject} {ticket.description}".lower()
    if any(word in text for word in ["cancel", "subscription", "renewal"]):
        if any(term in text for term in ["charged twice", "double charged", "duplicate charge", "duplicate billing"]):
            return "billing_duplicate_charge", "billing"
        return "subscription_cancellation", "subscriptions"
    if any(word in text for word in ["refund", "charged", "billing", "invoice"]):
        if any(term in text for term in ["duplicate", "charged twice", "double charged", "two charges"]):
            return "billing_duplicate_charge", "billing"
        return "billing_refund", "billing"
    if any(word in text for word in [
        "login",
        "log in",
        "log-in",
        "sign in",
        "signin",
        "password",
        "mfa",
        "session",
        "account locked",
    ]):
        return "login_issue", "auth"
    if any(word in text for word in ["shipping", "package", "tracking", "delivery"]):
        return "shipping_delay", "shipping"
    if any(word in text for word in ["payment", "card", "declined"]):
        return "payment_failure", "billing"
    return "unknown", "general"


def formulate_queries(ticket: SupportTicket, issue_type: str, product_area: str) -> list[str]:
    raw = f"{ticket.subject}. {ticket.description}".strip()
    queries = [raw]
    if issue_type == "billing_refund":
        queries += ["refund approved but not received", "refund processing timeline", "delayed refund after approval"]
    elif issue_type == "billing_duplicate_charge":
        queries += ["duplicate charge transaction review", "charged twice billing operations", "two charges one renewal period"]
    elif issue_type == "login_issue":
        queries += ["login session expired after password reset", "authentication troubleshooting", "AUTH_TOKEN_EXPIRED login"]
    elif issue_type == "shipping_delay":
        queries += ["tracking not updating after shipment", "shipping delay carrier handoff", "package tracking no movement"]
    elif issue_type == "subscription_cancellation":
        queries += ["subscription cancellation refund current billing period", "cancel subscription future renewal"]
    elif issue_type == "payment_failure":
        queries += ["payment failed card declined", "payment processor error troubleshooting"]
    else:
        queries += [f"{product_area} support policy", "customer support escalation criteria"]
    return list(dict.fromkeys(queries))
