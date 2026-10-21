# Arbiter technical progress

Updated 21 October 2026.

## Implemented

- **Application:** React/TypeScript chat frontend, FastAPI backend and PostgreSQL storage. Conversation context, loading, retry and new-chat behavior work.
- **Providers:** verified live OpenAI, Anthropic and Google generation, plus Jev task/difficulty classification. Credentials remain server-side.
- **Routing and evaluation:** deterministic selection using quality, estimated cost and latency; confidence fallback; structured judge scores; at most one escalation. Every paid attempt, usage estimate, failure and decision is persisted with bounded time and spending.
- **History and jobs:** per-attempt historical estimates, frozen configuration/history snapshots, and a sequential benchmark CLI. Completed cases are skipped on resume; interrupted calls retain spending reservations. Phase 05 merged in PR #6.

**Verification:** the last recorded full suite passed 261 tests, including real PostgreSQL. Phase 06 adds six passing desktop/mobile browser checks; CI passed all 264 backend tests with PostgreSQL on its API commit. Final PR review/CI is pending. A six-case mock job resumed without duplicates. Live routing worked; escalation was verified with an offline fixture.

## Remaining

- Finish final Phase 06 PR review/CI and merge; answer details and recent-run/benchmark tables are implemented.
- Complete the 60-case dataset, compare routed and fixed-model strategies, independently grade answers, and publish cost/latency/quality results.
- Add container packaging, same-origin serving, password sessions, request/concurrency limits, managed PostgreSQL and HTTPS deployment.
- Finish deployment instructions and the demo handoff.

Judge approval does not prove correctness; savings remain unmeasured. Reuse live evidence to minimize paid testing.

Detailed evidence: [STATUS.md](STATUS.md). Technical contracts: [design.md](design.md).
