from app.tools.mcp_ticket_tool import HistoricalTicketTool


def test_historical_ticket_tool_uses_mcp_server_contract():
    tool = HistoricalTicketTool()
    results = tool.run(
        query="refund approved but not received",
        issue_type="billing_refund",
        product_area="billing",
        limit=2,
    )
    assert tool.backend == "mcp_stdio"
    assert len(results) == 2
    assert results[0]["ticket_id"] == "TCK-1001"
