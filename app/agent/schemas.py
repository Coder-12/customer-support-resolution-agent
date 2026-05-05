from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class SupportTicket(BaseModel):
    subject: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    customer_id: str | None = None
    order_id: str | None = None
    account_id: str | None = None


class TicketAnalysis(BaseModel):
    issue_type: str
    product_area: str
    urgency: Literal["low", "medium", "high"]
    customer_intent: str
    required_context: list[str]
    retrieval_queries: list[str]
    tools_to_call: list[str]
    memory_summary: str | None = None


class EvidenceItem(BaseModel):
    source: str
    source_type: Literal["doc", "historical_ticket", "tool"]
    title: str | None = None
    content: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    status: Literal["success", "failure", "skipped"]
    result: dict[str, Any] | list[dict[str, Any]] | None = None
    error: str | None = None


class GuardrailCheck(BaseModel):
    name: str
    passed: bool
    details: str


class EscalationPacket(BaseModel):
    reason: str
    missing_information: list[str] = Field(default_factory=list)
    evidence_found: list[str] = Field(default_factory=list)
    recommended_next_step: str


class AgentResponse(BaseModel):
    run_id: str
    created_at: datetime
    decision: Literal["respond", "escalate"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    ticket_analysis: TicketAnalysis
    draft_response: str | None = None
    escalation: EscalationPacket | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    guardrail_checks: list[GuardrailCheck] = Field(default_factory=list)
