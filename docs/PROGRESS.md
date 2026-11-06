# Arbiter technical progress

Updated 21 October 2026.

## Implemented

- React/TypeScript chat, FastAPI and PostgreSQL; context, loading, retry and new chat.
- OpenAI, Anthropic and Google adapters, Jev classification, deterministic historical routing, bounded online evaluation and one escalation. Prior successful live checks are preserved.
- Durable paid-call accounting, frozen resumable CLI jobs, expanded answer details, and recent-run/benchmark views. Phases 00–06 are merged.
- Phase 07 code: 30 development + 30 held-out cases, three strategies, independent grading, seeded execution, frozen snapshots, shared spending ledger, report exports and strategy metrics.

**Verification:** final runtime CI passed 318 backend tests with real PostgreSQL and six desktop/mobile browser tests, plus lint/type/build checks. A full free comparison rehearsal completed 90 runtime and 90 grading rows.

## Remaining and blocker

- **Phase 07 is blocked:** Google generation returned HTTP 402 (Payment Required). Development stopped after two completed cases and 28 pending. Known usage is USD 0.005209634, incomplete; USD 0.5026437 is retained conservatively including the diagnostic. No held-out comparison or independent live grade exists.
- Restore Google API billing, record the remaining budget allocation within the approved USD 5 total, finish the 28 pending cases in a separately capped continuation job (the original frozen ceiling is exhausted), freeze/run the three strategies, review ten matched triplets, and publish the measured report. Review and merge Phase 07.
- Phase 08: Vercel deployment (user selected; CLI authenticated), container packaging, same-origin serving, password sessions, request/concurrency limits, managed PostgreSQL and HTTPS verification. Final instructions, requirement traceability and demo handoff remain. No hosting service purchased.

Judge approval does not prove correctness; savings remain unmeasured. [Detailed status](STATUS.md), [blocked report](../reports/benchmark.md), [technical contracts](design.md).
