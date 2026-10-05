# Arbiter requirements

## Goal

Determine whether routing requests across cloud models can preserve response quality while reducing total API cost or end-to-end latency compared with a fixed strong model. A negative result is a valid project outcome if measured honestly.

## Scope

A single-user/demo chat app with React, shadcn/ui, FastAPI, PostgreSQL, Jev prompt analysis, and generation integrations for OpenAI, Anthropic, and Google. Text only. No local GPU required.

## Functional requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| R01 | Chat supports sending text, visible history, loading, error, retry by user action, and new conversation | Browser smoke test; context-dependent follow-up works |
| R02 | Server analyzes the bounded conversation using Jev | Live sanitized decision plus offline schema/error tests |
| R03 | Analysis includes task, difficulty, reasoning level, confidence when available, and analysis source | Validated internal Analysis schema; unknown confidence stays null |
| R04 | Custom deterministic router selects an enabled model using quality estimate, cost estimate, and latency estimate | Same inputs/config give same result; candidate scores inspectable |
| R05 | Integrate at least one live text-generation model from each of OpenAI, Anthropic, Google | Three explicit live smoke checks; model IDs and dates recorded |
| R06 | Evaluate each generated answer with a bounded rubric; escalate at most once when appropriate | Passing, failing, unknown, exhausted, and provider-error cases tested |
| R07 | Persist input messages, analysis, candidates, decisions, all paid attempts, answers, usage, latency, cost, evaluator outcomes, errors, and config versions | PostgreSQL round-trip tests; failed attempts retained |
| R08 | Use historical task/difficulty/model performance in later routing | Seeded aggregate changes expected selection; live demonstration |
| R09 | Run benchmark/evaluation jobs outside the interactive request path | CLI job stores progress and results; interrupted job can resume |
| R10 | Show route metadata under each assistant message and a small recent-runs/benchmark view | Selected model, rationale, escalation, quality, total latency and cost visible |
| R11 | Compare routed, fixed-cheap, and fixed-strong strategies on a frozen held-out set | Reproducible report including overhead, failures, and sample size |
| R12 | Deploy on cloud CPU infrastructure with PostgreSQL and browser access | HTTPS demo from a second machine; deployment instructions |
| R13 | Work in separate phase branches with meaningful incremental commits, an immediate push after each commit, sole user authorship, and phase PRs | Git history, push results, author metadata, and PR links recorded |
| R14 | Provide local setup, environment template, tests, limitations, and final demo steps | Fresh setup from README succeeds |

## Input and behavior limits

- Client supplies the current conversation; server owns routing and provider instructions. Keep at most 10 messages (user and assistant roles only), ending with a user message. Reject larger input rather than silently losing context. Combined content limit: 12,000 characters. Empty messages are invalid.
- Frontend offers New chat when the limit is reached. Chat history lives in memory for this MVP; no persistent account/sidebar history is required. Run records are persisted for analysis.
- Default generation output limit: 1,024 tokens, mapped to each provider's supported option. Detect truncation; it cannot pass quality evaluation by default.
- Before every paid call, check remaining timeout and projected cost. At most 2 generation calls, 1 classification call, and 2 evaluation calls per request. Disable SDK automatic retries for this budget model.
- No hidden recursive retries. A user retry is a new request and may incur a new charge.
- A request may return a best-effort answer marked quality_failed or unverified; do not falsely mark it passed. All-provider failure returns a structured error.
- API keys, model IDs, prices, and limits come from backend configuration. Unknown price/usage must never display as zero.
- Missing provider credentials disable that provider with an explicit status. The final integration gate still requires evidence for all three providers and Jev.

## Simplicity and exclusions

No accounts, billing, organization roles, RAG, vector database, uploads, browsing/tools, autonomous code execution, streaming, Redis, Celery, Kubernetes, distributed workers, automatic model discovery, fine-tuning, reinforcement learning, or model marketplace. No claim of production reliability.

Use one chat screen, one compact runs/benchmark screen, one API service, one database, and a CLI for jobs. Manual or scheduled invocation of the CLI satisfies background work; no job-management UI is needed.

## Completion versus research success

The software can be complete even if routing fails to save money. The experiment's provisional success criterion is held-out pass rate within 5 percentage points of the fixed-strong baseline and either at least 20% lower total runtime API cost or at least 15% lower median end-to-end latency. Freeze these targets before the final run. Report uncertainty and p95 latency; do not imply statistical equivalence from this small experiment.
