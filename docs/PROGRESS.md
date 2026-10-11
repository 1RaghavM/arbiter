# Arbiter technical progress

Updated 11 October 2026.

## Implemented

- **Application:** React/TypeScript chat frontend, FastAPI backend and PostgreSQL storage. Conversation context, loading, retry and new-chat behavior work.
- **Providers:** verified live OpenAI, Anthropic and Google generation, plus Jev task/difficulty classification. Credentials remain server-side.
- **Routing and evaluation:** deterministic selection using quality, estimated cost and latency; confidence fallback; structured judge scores; at most one escalation. Every paid attempt, usage estimate, failure and decision is persisted with bounded time and spending.
- **History and jobs:** per-attempt historical estimates, frozen configuration/history snapshots, and a sequential benchmark CLI. Completed cases are skipped on resume; interrupted calls retain spending reservations. This code awaits final PR review.

**Verification:** 259 offline tests and CI passed, including real PostgreSQL. A six-case mock job resumed without duplicates. Live routing worked; escalation was verified with an offline fixture.

## Remaining

- Expand answer details and add recent-run/benchmark tables with browser regression coverage.
- Complete the 60-case dataset, compare routed and fixed-model strategies, independently grade answers, and publish cost/latency/quality results.
- Add container packaging, same-origin serving, password sessions, request/concurrency limits, managed PostgreSQL and HTTPS deployment.
- Finish deployment instructions and the demo handoff.

Judge approval does not prove correctness; savings remain unmeasured. Reuse live evidence to minimize paid testing.

Detailed evidence: [STATUS.md](STATUS.md). Technical contracts: [design.md](design.md).
