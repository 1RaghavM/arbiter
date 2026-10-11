# Arbiter progress

Updated 11 October 2026. Phases 00–04 are merged. Phase 05 is implemented and tested, with [PR #6](https://github.com/1RaghavM/arbiter/pull/6) awaiting final review and merge.

## Done

- React chat, FastAPI, PostgreSQL storage and CI.
- Verified live OpenAI, Anthropic, Google and Jev integrations.
- Routing, fixed-judge evaluation, one escalation, spending/time limits and full attempt accounting. Basic route/quality/cost labels work.
- Phase 05: historical estimates and resumable CLI jobs with frozen inputs and retained reservations after crashes.

**259 offline tests and CI passed.** A six-case mock job resumed without duplicates. Live routing passed; escalation used a labeled offline fixture.

## Remaining

1. **Phase 05:** finish PR review and merge.
2. **Phase 06:** expand answer metadata, add recent runs and benchmark results views, and complete browser checks.
3. **Phase 07:** finish 30 development and 30 held-out cases; run one budgeted comparison of routed, cheap and strong strategies; independently grade results and publish an honest report.
4. **Phase 08:** add deployment protection and container setup, deploy with managed PostgreSQL and HTTPS, and finish the demo/handoff documentation.

Paid checks should stay minimal. Judge approval does not prove correctness; savings remain unmeasured. Implementation is paused.

Detailed evidence: [STATUS.md](STATUS.md). Planned scope: [phases.md](phases.md).
