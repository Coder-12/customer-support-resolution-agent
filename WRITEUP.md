# Customer Support Resolution Agent Write-up

## Objective

The goal is to build an internal support copilot that assists support engineers by analyzing tickets, retrieving relevant context, using tools where useful, and producing either a customer-ready response draft or a structured escalation packet.

## Agent architecture

The agent follows a deliberate multi-stage workflow:

1. Accept a support ticket with subject, description, and optional identifiers.
2. Classify the issue type and product area.
3. Formulate retrieval queries.
4. Retrieve relevant documentation through RAG.
5. Retrieve similar historical tickets through a local stdio MCP server.
6. Use context tools such as order status and log lookup when applicable.
7. Merge evidence.
8. Compute confidence.
9. Run guardrails, including policy-risk checks and tool-failure checks.
10. Return a customer-ready draft or escalation packet.

This design makes the agent behavior inspectable and avoids hiding the entire workflow inside a single prompt.
The agent also keeps a limited in-process memory of recent related tickets and uses that as additional retrieval context.

## RAG choices

The RAG pipeline uses ChromaDB with `sentence-transformers/all-MiniLM-L6-v2` embeddings. Documentation is stored as markdown files with frontmatter metadata.
In restricted environments, the implementation falls back cleanly to a local lexical store when the embedding model cache is unavailable, so the agent remains runnable for demo and evaluation.

### Chunking

The ingestion pipeline splits markdown documents by section headings first. Long sections are further split into overlapping chunks. This keeps semantic units together while avoiding overly long chunks.

### Metadata

Each chunk stores:

- source file
- document title
- document type
- product area
- section heading
- updated date
- chunk index

This metadata supports filtering, result explanation, and production debugging.

### Query formulation

The agent uses the original ticket plus issue-specific expanded queries. For example, a refund ticket may generate queries such as `refund approved but not received`, `refund processing timeline`, and `delayed refund after approval`.

## Tool usage

The agent uses three tools:

1. Historical ticket lookup: local MCP-exposed tool for structured historical ticket records.
2. Order status lookup: mock business tool for refund, payment, and shipping state.
3. Log lookup: mock diagnostic tool for auth/payment errors.

The historical ticket tool is exposed through a lightweight local stdio MCP server so the agent can retrieve structured past tickets through an actual server boundary, while still remaining self-contained for the assignment.

## Guardrails

The guardrail layer checks:

- whether confidence meets the configured threshold
- whether documentation evidence exists
- whether required identifiers are present
- whether required tools failed (hard escalation)
- whether policy-risk conditions were detected (hard escalation), such as refund approved beyond policy window or unknown processor state

The agent escalates instead of drafting when evidence is weak, identifiers are missing, confidence is below threshold, required tools fail, or a policy condition requires human review. Confidence is therefore used as a decision signal, not as the only decision-maker: a high-confidence duplicate-charge case can still escalate if the billing policy requires transaction review.

The CLI supports two demo modes. Human-readable mode is intended for support-engineer review and shows the decision, confidence, draft or escalation packet, and evidence table. JSON mode is intended for debugging and automated evaluation because it exposes the complete structured state.

## Evaluation approach

The evaluation suite is deterministic and heuristic-based. Each test case defines:

- expected decision
- expected tools
- phrases that should appear
- phrases that must not appear

The evaluator reports total pass/fail score and per-test diagnostics. This is lightweight, reproducible, and suitable for a timed assignment.

Response quality is measured through:

- correctness: the agent chooses respond vs escalate as expected
- groundedness: retrieved documentation and historical ticket evidence are present
- tool appropriateness: expected tools are called for the issue type
- safety: prohibited phrases such as unsupported guarantees do not appear
- usefulness: required phrases verify that the draft includes the key customer-facing guidance
- confidence validity: confidence remains bounded and drives escalation behavior

A future version could add AI-as-a-judge scoring for empathy, clarity, and grounding, but the current approach intentionally favors reproducible regression checks.

## Production and LLMOps considerations

The project includes lightweight LLMOps concepts:

- prompt versioning
- environment-driven model/config settings
- structured run logging
- latency tracking
- zero-cost accounting for deterministic local drafting
- tools-called tracking
- retrieved-doc tracking
- evaluation regression tests

In production, this could be expanded with:

- centralized tracing
- prompt experiment tracking
- cost monitoring
- model version rollout
- human feedback collection
- offline evaluation dashboards
- alerting for tool failures and low-confidence spikes

## Why this design fits the assignment

The solution prioritizes correctness and clarity over unnecessary UI polish. It demonstrates real RAG, explicit tool usage, guardrails, evaluation, and production-oriented code structure while remaining small enough to complete and explain within the time limit.
