from __future__ import annotations

from fastapi import FastAPI

from app.agent.resolution_agent import CustomerSupportResolutionAgent
from app.agent.schemas import AgentResponse, SupportTicket

app = FastAPI(title="Customer Support Resolution Agent", version="0.1.0")
agent = CustomerSupportResolutionAgent()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/resolve-ticket", response_model=AgentResponse)
def resolve_ticket(ticket: SupportTicket) -> AgentResponse:
    return agent.resolve(ticket)
