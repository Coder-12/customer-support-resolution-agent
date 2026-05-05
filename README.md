# Customer Support Resolution Agent

An internal AI-powered customer support resolution copilot that analyzes incoming support tickets, retrieves documentation and historical ticket context, uses support tools, and returns either a customer-ready draft response or a structured escalation packet.

This project is intentionally CLI/API-first because the assignment prioritizes agent design, RAG correctness, tool usage, guardrails, code quality, and production/LLMOps thinking over UI polish.

## Architecture

```text
Incoming support ticket
  -> ticket analysis and issue classification
  -> retrieval query formulation
  -> RAG retrieval over docs/FAQs
  -> MCP historical ticket lookup over local stdio server
  -> context tools: order status and logs
  -> evidence merge
  -> confidence scoring and guardrails
  -> customer-ready draft OR structured escalation
```

## How the project maps to the evaluation criteria

### Agent design & reasoning quality

The main orchestration lives in `app/agent/resolution_agent.py`. The agent has explicit stages: ticket analysis, issue classification, query formulation, tool selection, RAG retrieval, historical ticket lookup, context tool calls, confidence scoring, guardrails, and final decision.
It also maintains limited in-process task memory (recent related tickets) and uses that memory as additional retrieval context.

### RAG implementation correctness

The RAG implementation lives in `app/rag/`.

- `ingest.py`: markdown-aware loading, frontmatter parsing, section splitting, chunking, and indexing.
- `vector_store.py`: ChromaDB persistent vector store using `sentence-transformers/all-MiniLM-L6-v2`.
- `retriever.py`: metadata-aware retrieval with fallback to global search.
- `query.py`: issue classification and retrieval query formulation.

Chunking strategy:

- Split markdown by headings.
- Chunk long sections into approximately 140 words with 25-word overlap.
- Preserve metadata: `source`, `title`, `doc_type`, `product_area`, `section`, `updated_at`, and `chunk_index`.

### Tool usage and guardrails

Tools live in `app/tools/`.

- `mcp_ticket_tool.py`: historical ticket lookup client that calls a local stdio MCP server.
- `order_tool.py`: mock order/refund/shipping/payment status lookup.
- `log_tool.py`: mock account log lookup.
- `app/mcp/ticket_server.py`: lightweight MCP server exposing `historical_ticket_lookup`.

Guardrails live in `app/agent/guardrails.py`.

Implemented guardrails:

- Minimum confidence threshold.
- Documentation evidence requirement.
- Required identifier checks such as `order_id` or `account_id`.
- Hard escalation on tool failures.
- Hard escalation on policy-risk signals (for example: refund approved more than 10 business days ago or unknown processor state).
- Escalation when evidence is insufficient.

### Code quality and clarity

The code is modular, typed, and schema-driven with Pydantic models in `app/agent/schemas.py`. The agent output is structured and easy to inspect.

### Production & LLMOps mindset

The project includes lightweight production thinking:

- Prompt version constant in `app/agent/prompts.py`.
- Environment-driven configuration in `app/config.py`.
- Run tracking in `app/observability/run_tracker.py`.
- Latency, decision, confidence, retrieval backend, MCP backend, tools called, and retrieved docs are logged to `runs.jsonl`.
- Cost field is tracked in the run record and is `0.0` for the deterministic local drafting path.
- Deterministic heuristic evaluation in `app/evals/evaluator.py`.

In production, run records could be shipped to LangSmith, Arize Phoenix, Datadog, OpenTelemetry, or a data warehouse. The included local MCP server can be replaced with an external MCP service connected to Zendesk, Salesforce Service Cloud, Jira Service Management, or a support database.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

In `VECTOR_STORE_MODE=auto`, the agent uses Chroma embeddings when the local model cache is available and otherwise falls back cleanly to the lexical store. You can also force lexical mode with `VECTOR_STORE_MODE=fallback`.

## Ingest documentation

```bash
python -m app.rag.ingest
```

## Run the CLI

Human-readable output:

```bash
python -m app.main resolve \
  --subject "Refund approved but not received" \
  --description "My refund was approved 12 days ago but I still have not received the money." \
  --customer-id CUS-1 \
  --order-id ORD-1001
```

JSON output for inspecting the full structured agent state:

```bash
python -m app.main resolve \
  --subject "Refund approved but not received" \
  --description "My refund was approved 12 days ago but I still have not received the money." \
  --order-id ORD-1001 \
  --json
```

Run a sample ticket:

```bash
python -m app.main sample --index 0
```

## Run evaluation

```bash
python -m app.evals.evaluator
```

The evaluator checks:

- respond vs escalate decision
- expected tool usage
- required safe phrases
- prohibited unsafe phrases
- evidence presence
- confidence validity

## Reviewer demo sequence

Run these commands to demonstrate the required behavior end to end:

```bash
python -m compileall -q app tests
python -m app.rag.ingest
python -m pytest -q
python -m app.evals.evaluator
```

Then show representative tickets in human-readable mode. This output is best for a live demo because it shows the decision, confidence, customer-ready draft or escalation packet, and evidence table without requiring the reviewer to read raw JSON:

```bash
python -m app.main resolve --subject "Refund approved but not received" --description "My refund was approved 12 days ago but I still have not received the money." --customer-id CUS-1 --order-id ORD-1001
python -m app.main resolve --subject "Refund still missing after 20 business days" --description "My refund was approved long ago and still has not arrived." --customer-id CUS-5 --order-id ORD-1005
python -m app.main resolve --subject "Cannot log in" --description "I reset my password but the app keeps saying my session expired." --customer-id CUS-6 --account-id ACCT-1002
python -m app.main resolve --subject "Tracking not moving" --description "My package tracking has not updated since yesterday." --customer-id CUS-2 --order-id ORD-1002
python -m app.main resolve --subject "Cancel subscription and refund request" --description "I want to cancel my subscription and understand whether the current billing period is refundable." --customer-id CUS-SUB-1
python -m app.main resolve --subject "Card declined" --description "My payment failed but I see a pending bank charge." --customer-id CUS-3 --order-id ORD-1003 --account-id ACCT-1001
python -m app.main resolve --subject "Charged twice for renewal" --description "I see two charges for one subscription renewal." --customer-id CUS-DUP-1 --order-id ORD-9999
python -m app.main resolve --subject "Something is broken" --description "Nothing works and I need help now."
```

These examples exercise customer-ready drafting, structured escalation, RAG evidence, MCP historical ticket retrieval, order lookup, log lookup, payment handling, duplicate-charge escalation, confidence checks, policy-risk guardrails, and unknown-issue escalation.

Use `--json` on any of the same commands when you want to inspect the full machine-readable response, including `ticket_analysis`, retrieved `evidence`, `tool_results`, and `guardrail_checks`.

Confidence is not treated as a vanity metric. It is one input to the final decision: high confidence with clear evidence can produce a customer-ready draft, while low confidence, missing identifiers, tool failures, or policy-risk signals force a structured escalation.

## Optional API

```bash
uvicorn app.api:app --reload
```

Then call:

```http
POST /resolve-ticket
```

Example body:

```json
{
  "subject": "Cannot log in",
  "description": "I reset my password but the app keeps saying my session expired.",
  "customer_id": "CUS-6",
  "account_id": "ACCT-1002"
}
```

## Example output shape

```json
{
  "decision": "respond",
  "confidence": 0.84,
  "ticket_analysis": {
    "issue_type": "billing_refund",
    "product_area": "billing",
    "retrieval_queries": ["..."]
  },
  "draft_response": "Hi, thanks for reaching out...",
  "escalation": null,
  "evidence": [],
  "tool_results": [],
  "guardrail_checks": []
}
```

## Known limitations

- Historical ticket retrieval uses a lightweight local scoring function rather than a real ticket database.
- The historical ticket MCP server is local and lightweight; it is not yet connected to an external ticketing platform.
- Customer response drafting is deterministic by default for reliability in the assignment demo. A production system could add an LLM drafting layer constrained by the same evidence and guardrails.

## Future improvements

- Add hybrid retrieval with BM25 + vector search.
- Add reranking for retrieved chunks.
- Replace the local MCP server with a ticketing-system-backed MCP service.
- Add AI-as-a-judge evaluation.
- Add continuous regression evals in CI.
- Add OpenTelemetry traces and cost tracking.
