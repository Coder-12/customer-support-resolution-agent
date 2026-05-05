from __future__ import annotations

from collections import deque
from datetime import date, datetime, timezone
from typing import Any

from app.agent.guardrails import (
    compute_confidence,
    find_missing_identifiers,
    run_guardrails,
    should_escalate,
)
from app.agent.schemas import (
    AgentResponse,
    EscalationPacket,
    EvidenceItem,
    SupportTicket,
    TicketAnalysis,
    ToolResult,
)
from app.observability.run_tracker import new_run_id, track_run
from app.rag.query import classify_issue, formulate_queries
from app.rag.retriever import DocumentationRetriever
from app.tools.log_tool import LogLookupTool
from app.tools.mcp_ticket_tool import HistoricalTicketTool
from app.tools.order_tool import OrderStatusTool


class CustomerSupportResolutionAgent:
    def __init__(self):
        self.retriever = DocumentationRetriever()
        self.historical_ticket_tool = HistoricalTicketTool()
        self.order_tool = OrderStatusTool()
        self.log_tool = LogLookupTool()
        self.memory: deque[dict[str, Any]] = deque(maxlen=20)

    def resolve(self, ticket: SupportTicket) -> AgentResponse:
        run_id = new_run_id()
        with track_run(run_id, {"subject": ticket.subject}) as run_record:
            memory_summary = self._memory_summary(ticket)
            issue_type, product_area = classify_issue(ticket)
            queries = formulate_queries(ticket, issue_type, product_area)
            if memory_summary:
                queries.append(f"recent related context: {memory_summary}")
            tools_to_call = self._select_tools(issue_type, ticket)
            analysis = TicketAnalysis(
                issue_type=issue_type,
                product_area=product_area,
                urgency=self._infer_urgency(ticket),
                customer_intent=self._infer_customer_intent(issue_type),
                required_context=self._required_context(issue_type),
                retrieval_queries=queries,
                tools_to_call=tools_to_call,
                memory_summary=memory_summary,
            )

            doc_evidence = self.retriever.retrieve(queries, product_area=product_area, k_per_query=3)
            historical_tool_result, historical_evidence = self._lookup_historical_tickets(queries[0], issue_type, product_area)
            tool_results = [historical_tool_result]
            tool_results.extend(self._run_context_tools(ticket, tools_to_call))

            missing_information = find_missing_identifiers(ticket, issue_type)
            confidence = compute_confidence(
                issue_type=issue_type,
                doc_evidence=doc_evidence,
                historical_evidence=historical_evidence,
                tool_results=tool_results,
                missing_information=missing_information,
            )
            policy_escalation_flags = self._policy_escalation_flags(issue_type, ticket, tool_results)
            guardrail_checks = run_guardrails(
                confidence=confidence,
                doc_evidence=doc_evidence,
                missing_information=missing_information,
                tool_results=tool_results,
                policy_escalation_flags=policy_escalation_flags,
            )

            evidence = [*doc_evidence, *historical_evidence, *self._tool_results_to_evidence(tool_results)]
            escalate = should_escalate(confidence, guardrail_checks)
            if escalate:
                response = AgentResponse(
                    run_id=run_id,
                    created_at=datetime.now(timezone.utc),
                    decision="escalate",
                    confidence=confidence,
                    ticket_analysis=analysis,
                    draft_response=None,
                    escalation=self._build_escalation(
                        ticket,
                        issue_type,
                        missing_information,
                        doc_evidence,
                        tool_results,
                        policy_escalation_flags,
                    ),
                    evidence=evidence,
                    tool_results=tool_results,
                    guardrail_checks=guardrail_checks,
                )
            else:
                response = AgentResponse(
                    run_id=run_id,
                    created_at=datetime.now(timezone.utc),
                    decision="respond",
                    confidence=confidence,
                    ticket_analysis=analysis,
                    draft_response=self._draft_customer_response(ticket, issue_type, doc_evidence, tool_results),
                    escalation=None,
                    evidence=evidence,
                    tool_results=tool_results,
                    guardrail_checks=guardrail_checks,
                )

            run_record.update({
                "decision": response.decision,
                "confidence": response.confidence,
                "issue_type": issue_type,
                "drafting_mode": "deterministic_local",
                "retrieval_backend": self.retriever.store.mode,
                "historical_ticket_backend": self.historical_ticket_tool.backend,
                "tools_called": [tool.tool_name for tool in tool_results],
                "retrieved_docs": [item.source for item in doc_evidence],
            })
            self._remember(ticket, response, issue_type)
            return response

    def _select_tools(self, issue_type: str, ticket: SupportTicket) -> list[str]:
        tools = ["historical_ticket_lookup"]
        if issue_type in {"billing_refund", "billing_duplicate_charge", "payment_failure", "shipping_delay"}:
            tools.append("order_status_lookup")
        if issue_type in {"login_issue", "payment_failure"}:
            tools.append("log_lookup")
        return tools

    def _infer_urgency(self, ticket: SupportTicket) -> str:
        text = f"{ticket.subject} {ticket.description}".lower()
        if any(term in text for term in ["urgent", "now", "locked", "more than 10 business days", "charged twice"]):
            return "high"
        if any(term in text for term in ["not received", "failed", "cannot", "delayed"]):
            return "medium"
        return "low"

    def _infer_customer_intent(self, issue_type: str) -> str:
        return {
            "billing_refund": "wants refund status or refund timeline",
            "billing_duplicate_charge": "wants billing correction",
            "login_issue": "wants account access restored",
            "shipping_delay": "wants delivery or tracking update",
            "subscription_cancellation": "wants subscription cancellation support",
            "payment_failure": "wants payment issue resolved",
        }.get(issue_type, "needs support triage")

    def _required_context(self, issue_type: str) -> list[str]:
        return {
            "billing_refund": ["refund policy", "order refund status", "similar refund tickets"],
            "billing_duplicate_charge": ["billing policy", "order/payment status", "similar billing tickets"],
            "login_issue": ["login troubleshooting", "account logs", "similar auth tickets"],
            "shipping_delay": ["shipping FAQ", "order tracking status", "similar shipping tickets"],
            "subscription_cancellation": ["subscription policy", "refund policy", "similar cancellation tickets"],
            "payment_failure": ["payment FAQ", "order/payment status", "payment logs"],
        }.get(issue_type, ["relevant documentation", "historical tickets"])

    def _lookup_historical_tickets(self, query: str, issue_type: str, product_area: str) -> tuple[ToolResult, list[EvidenceItem]]:
        try:
            results = self.historical_ticket_tool.run(query=query, issue_type=issue_type, product_area=product_area, limit=3)
            evidence = [
                EvidenceItem(
                    source=item["ticket_id"],
                    source_type="historical_ticket",
                    title=item.get("subject"),
                    content=item.get("resolution", ""),
                    score=float(item.get("similarity", 0.0)),
                    metadata={"issue_type": item.get("issue_type"), "product_area": item.get("product_area")},
                )
                for item in results
            ]
            return ToolResult(tool_name=self.historical_ticket_tool.name, status="success", result=results), evidence
        except Exception as exc:
            return ToolResult(tool_name=self.historical_ticket_tool.name, status="failure", error=str(exc)), []

    def _run_context_tools(self, ticket: SupportTicket, tools_to_call: list[str]) -> list[ToolResult]:
        results: list[ToolResult] = []
        if "order_status_lookup" in tools_to_call:
            try:
                results.append(ToolResult(tool_name=self.order_tool.name, status="success", result=self.order_tool.run(ticket.order_id)))
            except Exception as exc:
                results.append(ToolResult(tool_name=self.order_tool.name, status="failure", error=str(exc)))
        if "log_lookup" in tools_to_call:
            try:
                results.append(ToolResult(tool_name=self.log_tool.name, status="success", result=self.log_tool.run(ticket.account_id)))
            except Exception as exc:
                results.append(ToolResult(tool_name=self.log_tool.name, status="failure", error=str(exc)))
        return results

    def _tool_results_to_evidence(self, tool_results: list[ToolResult]) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        for tool in tool_results:
            if tool.status != "success" or tool.tool_name == "historical_ticket_lookup":
                continue
            evidence.append(EvidenceItem(
                source=tool.tool_name,
                source_type="tool",
                title=tool.tool_name.replace("_", " ").title(),
                content=str(tool.result),
                score=None,
                metadata={"status": tool.status},
            ))
        return evidence

    def _draft_customer_response(
        self,
        ticket: SupportTicket,
        issue_type: str,
        doc_evidence: list[EvidenceItem],
        tool_results: list[ToolResult],
    ) -> str:
        order_result = self._tool_result(tool_results, "order_status_lookup")
        log_result = self._tool_result(tool_results, "log_lookup")

        if issue_type == "billing_refund":
            if isinstance(order_result, dict) and order_result.get("refund_status") == "approved":
                processor_status = str(order_result.get("processor_status") or "").replace("_", " ")
                processor_sentence = (
                    f"The processor currently shows status: {processor_status}. "
                    if processor_status
                    else ""
                )
                return (
                    "Hi, thanks for reaching out. I checked the available refund information and your refund is marked as approved. "
                    "Approved refunds are typically posted by banks and card networks within 5 to 10 business days after approval. "
                    f"{processor_sentence}Please allow the normal bank processing window to complete. "
                    "If the refund still has not appeared after that window, reply to this message and we can have Billing Operations review it further."
                )
            return (
                "Hi, thanks for reaching out. Based on our refund policy, approved refunds usually post within 5 to 10 business days, "
                "depending on the bank or payment processor. I recommend checking the refund status again after that window. "
                "If it has already passed, we can escalate this for a billing review."
            )
        if issue_type == "login_issue":
            errors = []
            if isinstance(log_result, dict):
                errors = log_result.get("recent_errors", [])
            if "AUTH_TOKEN_EXPIRED" in errors:
                return (
                    "Hi, thanks for contacting us. The issue appears consistent with an expired login session. "
                    "Please sign out completely, clear your browser cache, then try signing in again using an incognito or private browser window. "
                    "If the issue continues after those steps, reply here and we can escalate this for additional account review."
                )
            return (
                "Hi, thanks for reaching out. Please try resetting your password, clearing your browser cache, and signing in again from an incognito or private browser window. "
                "If the issue continues, reply with the email address on the account so we can investigate further."
            )
        if issue_type == "shipping_delay":
            return (
                "Hi, thanks for reaching out. Tracking updates can sometimes take up to 48 hours after the carrier receives the package. "
                "Please check the tracking page again after that window. If there is still no movement or the carrier reports an exception, reply here and we can route it to Logistics for review."
            )
        if issue_type == "subscription_cancellation":
            return (
                "Hi, thanks for reaching out. You can cancel the subscription from account settings, and cancellation will stop future renewals. "
                "A cancellation does not automatically create a refund for the current billing period unless the refund policy criteria are met. "
                "If you want us to review refund eligibility, please share the related order or billing reference."
            )
        if issue_type == "payment_failure":
            return (
                "Hi, thanks for reaching out. Payments can fail because of bank declines, expired cards, billing address mismatches, or temporary processor issues. "
                "Please verify your card details, billing address, and available balance, then retry. If you were charged but the order did not complete, reply with the order reference so Billing Operations can review it."
            )
        top = doc_evidence[0].content if doc_evidence else ""
        return f"Hi, thanks for reaching out. Based on the available support information, {top[:220]} Please reply with any additional account or order details so we can help further."

    def _tool_result(self, tool_results: list[ToolResult], name: str) -> Any:
        for tool in tool_results:
            if tool.tool_name == name and tool.status == "success":
                return tool.result
        return None

    def _build_escalation(
        self,
        ticket: SupportTicket,
        issue_type: str,
        missing_information: list[str],
        doc_evidence: list[EvidenceItem],
        tool_results: list[ToolResult],
        policy_escalation_flags: list[str],
    ) -> EscalationPacket:
        failures = [tool for tool in tool_results if tool.status == "failure"]
        reason_parts = []
        if missing_information:
            reason_parts.append("required information is missing")
        if not doc_evidence:
            reason_parts.append("no relevant documentation was retrieved")
        if failures:
            reason_parts.append("one or more support tools failed")
        if issue_type == "unknown":
            reason_parts.append("the issue type is unclear")
        if policy_escalation_flags:
            reason_parts.extend(policy_escalation_flags)
        if not reason_parts:
            reason_parts.append("confidence is below the response threshold")
        evidence_found = [f"{item.source}: {item.content[:140]}" for item in doc_evidence[:3]]
        next_step = "Ask the customer for the missing information and route to the appropriate support queue."
        if issue_type in {"billing_refund", "payment_failure", "billing_duplicate_charge"}:
            next_step = "Route to Billing Operations with order/payment identifiers and retrieved policy context."
        elif issue_type == "login_issue":
            next_step = "Route to Identity Engineering with account ID and recent authentication logs."
        elif issue_type == "shipping_delay":
            next_step = "Route to Logistics with order ID, tracking status, and carrier details."
        return EscalationPacket(
            reason="; ".join(reason_parts).capitalize() + ".",
            missing_information=missing_information,
            evidence_found=evidence_found,
            recommended_next_step=next_step,
        )

    def _memory_summary(self, ticket: SupportTicket) -> str | None:
        related: list[dict[str, Any]] = []
        for item in reversed(self.memory):
            if ticket.customer_id and item.get("customer_id") == ticket.customer_id:
                related.append(item)
                continue
            if ticket.account_id and item.get("account_id") == ticket.account_id:
                related.append(item)
                continue
            if ticket.order_id and item.get("order_id") == ticket.order_id:
                related.append(item)
            if len(related) >= 3:
                break
        if not related:
            return None
        return " | ".join(
            f"{item['issue_type']}->{item['decision']} (confidence {item['confidence']:.2f})"
            for item in related
        )

    def _remember(self, ticket: SupportTicket, response: AgentResponse, issue_type: str) -> None:
        self.memory.append({
            "customer_id": ticket.customer_id,
            "account_id": ticket.account_id,
            "order_id": ticket.order_id,
            "issue_type": issue_type,
            "decision": response.decision,
            "confidence": response.confidence,
            "run_id": response.run_id,
        })

    def _policy_escalation_flags(
        self,
        issue_type: str,
        ticket: SupportTicket,
        tool_results: list[ToolResult],
    ) -> list[str]:
        flags: list[str] = []
        order_result = self._tool_result(tool_results, "order_status_lookup")
        if issue_type == "billing_duplicate_charge":
            flags.append("duplicate charge requires Billing Operations transaction review")
            if ticket.order_id and order_result is None:
                flags.append("order/payment status verification failed")
        if issue_type == "billing_refund":
            if ticket.order_id and order_result is None:
                flags.append("order status verification failed")
            if isinstance(order_result, dict):
                refund_status = order_result.get("refund_status")
                if refund_status == "approved":
                    approved_at = order_result.get("refund_approved_at")
                    if isinstance(approved_at, str):
                        business_days = self._business_days_since(approved_at)
                        if business_days is not None and business_days > 10:
                            flags.append(f"refund approved more than 10 business days ago ({business_days})")
                processor_status = str(order_result.get("processor_status") or "").lower()
                if processor_status in {"unknown", "failed", "error"}:
                    flags.append(f"processor status is {processor_status}")
        return flags

    def _business_days_since(self, iso_date: str) -> int | None:
        try:
            start = datetime.strptime(iso_date, "%Y-%m-%d").date()
        except ValueError:
            return None
        today = date.today()
        if start >= today:
            return 0
        days = 0
        cursor = start
        while cursor < today:
            cursor = cursor.fromordinal(cursor.toordinal() + 1)
            if cursor.weekday() < 5:
                days += 1
        return days
