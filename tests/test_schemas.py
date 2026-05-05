from app.agent.schemas import SupportTicket


def test_support_ticket_schema():
    ticket = SupportTicket(subject="Refund", description="Where is my refund?", order_id="ORD-1001")
    assert ticket.subject == "Refund"
    assert ticket.order_id == "ORD-1001"
