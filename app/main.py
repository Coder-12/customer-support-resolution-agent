from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.agent.resolution_agent import CustomerSupportResolutionAgent
from app.agent.schemas import SupportTicket

cli = typer.Typer(help="Customer Support Resolution Agent CLI")
console = Console()


@cli.command()
def resolve(
    subject: str = typer.Option(..., help="Support ticket subject"),
    description: str = typer.Option(..., help="Support ticket description"),
    customer_id: Optional[str] = typer.Option(None, help="Customer ID"),
    order_id: Optional[str] = typer.Option(None, help="Order ID"),
    account_id: Optional[str] = typer.Option(None, help="Account ID"),
    json_output: bool = typer.Option(False, "--json", help="Print raw JSON output"),
):
    """Resolve one support ticket."""
    ticket = SupportTicket(
        subject=subject,
        description=description,
        customer_id=customer_id,
        order_id=order_id,
        account_id=account_id,
    )
    response = CustomerSupportResolutionAgent().resolve(ticket)
    payload = response.model_dump(mode="json")
    if json_output:
        print(json.dumps(payload, indent=2))
        return
    console.print(Panel.fit(f"Decision: [bold]{response.decision.upper()}[/bold]\nConfidence: {response.confidence:.2f}", title="Agent Result"))
    console.print("[bold]Issue analysis[/bold]")
    console.print(json.dumps(response.ticket_analysis.model_dump(), indent=2))
    if response.draft_response:
        console.print(Panel(response.draft_response, title="Customer-ready draft"))
    if response.escalation:
        console.print(Panel(json.dumps(response.escalation.model_dump(), indent=2), title="Escalation packet"))
    table = Table(title="Evidence")
    table.add_column("Type")
    table.add_column("Source")
    table.add_column("Score")
    table.add_column("Preview")
    for item in response.evidence[:8]:
        table.add_row(item.source_type, item.source, str(item.score), item.content[:120].replace("\n", " "))
    console.print(table)


@cli.command()
def sample(index: int = typer.Option(0, help="Sample ticket index"), json_output: bool = typer.Option(False, "--json")):
    """Resolve a ticket from data/sample_tickets.json."""
    samples_path = Path("data/sample_tickets.json")
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    ticket_data = samples[index]
    response = CustomerSupportResolutionAgent().resolve(SupportTicket(**ticket_data))
    if json_output:
        print(response.model_dump_json(indent=2))
    else:
        console.print(Panel.fit(f"Sample {index}: {ticket_data['subject']}"))
        console.print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    cli()
