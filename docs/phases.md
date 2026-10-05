# Arbiter phase build line

Complete phases in order. Each row is one branch, incremental commits, one PR, and a review/merge boundary. Do not treat this document as authorization to merge. Start every new phase from the updated default branch after its dependency is merged.

| Phase | Branch | Working result |
| --- | --- | --- |
| 00 | phase/00-foundation | Reproducible repo, health API, frontend shell, CI |
| 01 | phase/01-chat-slice | End-to-end mocked chat and PostgreSQL run storage |
| 02 | phase/02-cloud-models | Three working cloud generation adapters |
| 03 | phase/03-jev-routing | Live Jev analysis and deterministic model routing |
| 04 | phase/04-evaluation | Bounded evaluation, escalation, full accounting |
| 05 | phase/05-history-jobs | Historical routing and resumable benchmark jobs |
| 06 | phase/06-demo-ui | Clear chat metadata and runs/results views |
| 07 | phase/07-benchmark | Frozen experiment and honest comparison report |
| 08 | phase/08-deployment | Cloud demo, documentation, complete handoff |

## Phase 00 — Foundation

**Depends on:** repository documentation bootstrap complete and explicit user authorization to start Phase 00.

Tasks: inspect existing repository; initialize only if needed; establish backend Python project and frontend React/Vite/TypeScript; add Tailwind/shadcn using current Vite instructions; add only needed UI primitives. Add health route, env template, ignore rules, local PostgreSQL compose, command documentation, and basic offline CI. Pin and lock compatible dependencies. Define model-config schema with explicit placeholder values, not fake live IDs. Record verified SDK/model documentation links and available credentials without values. README lists install, dev, lint, test, and build commands.

Suggested commits: (1) repo/tooling/environment setup; (2) health API and frontend shell; (3) CI and setup documentation.

Gate/demo: clean dependency installation, health response, frontend renders, frontend build/typecheck and backend lint/basic health test pass. No live calls required. STATUS identifies any missing provider accounts.

## Phase 01 — Mocked vertical slice

**Depends on:** Phase 00 merged.

Tasks: define internal API objects; validate bounded history; implement chat UI/composer/loading/errors/new chat using native fetch; deterministic mock generation through a small function seam. Add ordered SQL migrations, run/call persistence, and recent-run read endpoints. Tag all fake outputs and records mock. Send follow-up context; do not implement a conversations subsystem.

Suggested commits: (1) schemas/migration/persistence; (2) mock chat pipeline and interface; (3) integration tests and setup notes.

Gate/demo: browser sends two context-dependent turns; refresh/new chat behavior is documented; records survive backend restart; real PostgreSQL tests pass; missing DB fails before provider work. Mock records never count as evidence of live integration.

## Phase 02 — Cloud generation

**Depends on:** Phase 01 merged.

Tasks: implement official OpenAI, Anthropic, Google text adapters with normalized results, explicit stage timeouts and disabled SDK retries. Choose three available models spanning intended cost/capability, verifying exact IDs, usage fields, and pricing. Add backend-only fixed model config for temporary end-to-end generation. Missing credentials disable candidates. Persist usage, price snapshots, partial failures. Add live smoke CLI with explicit cost ceiling; keep CI offline.

Suggested commits: (1) model registry and first adapter; (2) remaining two adapters and accounting; (3) adapter tests/live evidence documentation.

Gate/demo: each of three providers returns a real response; mappings and failure cases pass offline tests; no API key in browser or git. If credentials missing, adapters/tests can be ready but live gate remains BLOCKED.

## Phase 03 — Jev and routing

**Depends on:** Phase 02 merged.

Tasks: read official TypeSafe docs; translate typed independent questions into Analysis; include conversation context. Add Jev confidence/failure fallback. Implement pure router with quality threshold, normalized cost/latency score, stable tie breaks, context/budget filtering, and logged candidate estimates. Use provisional registry priors now; history comes in Phase 05. Replace temporary fixed selection with routing. Display basic model and route reason.

Suggested commits: (1) Jev adapter and schema validation; (2) routing algorithm and pipeline integration; (3) score/fallback tests and live trace.

Gate/demo: live Jev request; manually verified score fixture; easy and difficult development prompts show route decisions. Document if priors fail to yield varied routes; tune only with development examples, never hardcode prompt strings to force a demo.

## Phase 04 — Evaluation and escalation

**Depends on:** Phase 03 merged.

Tasks: fixed online judge with rubric and structured validation; deterministic empty/truncated checks; at most one escalation; finite stage/request deadlines and cost reservations. Implement design.md failure/fallback rules. Persist every classifier, generator, judge call and failure. Surface passed/quality_failed/unverified distinctions. Cost aggregates include all stages and unknown usage flags.

Suggested commits: (1) evaluator and rubric tests; (2) bounded pipeline/escalation; (3) accounting/error tests and demo evidence.

Gate/demo: controlled tests cover all listed pipeline branches and maximum five paid calls. Live normal route works. Demonstrate escalation with clearly labeled controlled fixture if a live failure cannot be reproduced. Never guarantee that an answer is factually correct because the judge passed it.

## Phase 05 — Historical performance and jobs

**Depends on:** Phase 04 merged.

Tasks: derive per-bucket per-model aggregates from compatible labeled attempts; apply smoothed quality/median latency/output-length estimates above sample threshold. Add CLI `benchmark` and `report` commands, small development dataset, benchmark job/case tables, cost reservation, resumable progress. Execute outside HTTP; optional scheduler is documentation only. Use frozen snapshots for reproducible jobs. Resume skips completed cases; running/unknown cases after a crash are marked uncertain and require explicit retry since prior spend may already have occurred.

Suggested commits: (1) aggregates and routing update; (2) resumable job runner and persistence; (3) budget/resume tests and small dev run.

Gate/demo: seeded compatible history changes selection; mock/held-out/incompatible records excluded; interrupted job resumes without redoing completed cases; recorded cap stops new paid work. Show completed job persisted in PostgreSQL. No requirement to introduce worker infrastructure.

## Phase 06 — Demo interface

**Depends on:** Phase 05 merged.

Tasks: finish readable chat styling with small shadcn components. Expand per-answer details: task/difficulty, first/final model, short selection reason, quality status, attempts, total cost completeness and latency. Add simple tab/view for recent runs and benchmark summary with basic tables. Poll only on explicit refresh if needed. Handle invalid input, failed request, unknown cost, and absent results.

Suggested commits: (1) chat/details UI; (2) run/benchmark views; (3) focused browser test and UI cleanup.

Gate/demo: desktop/narrow viewport checks, keyboard navigation, one Playwright mock-chat flow, API error state, frontend type/lint/build. No new dashboard framework, charts library, settings console, or persistent chat sidebar.

## Phase 07 — Controlled benchmark

**Depends on:** Phase 06 merged.

Tasks: finish 30 development + 30 held-out cases/rubrics. Freeze data hashes, model IDs, prices, thresholds, and history snapshot before final run. Add fixed-cheap/strong strategies and common offline grading. Run the quality.md protocol within a stated budget, record per-case outcomes, review at least 10 matched triplets manually, and generate `reports/benchmark.md` plus machine-readable results. Separate research grading cost from request runtime costs. Remove private content from committed artifacts.

Suggested commits: (1) cases/scoring/frozen protocol; (2) comparison runner and report generation; (3) actual results and limitations.

Gate/demo: same frozen held-out cases compared across three strategies; overhead/failures accounted for; no test-set history leakage. Report whether targets met. Insufficient funds/access is BLOCKED, not permission to fabricate results. No success metric is a software-completion gate requiring cherry-picking.

## Phase 08 — Deployment and final handoff

**Depends on:** Phase 07 merged.

Tasks: multi-stage container builds frontend and API; managed PostgreSQL setup; migration release command; environment configuration; one API process; same-origin serving; minimal shared-password demo session, request limits, concurrency cap, and provider-side spend limits. Deploy to a suitable existing or user-selected container host; do not invent hosting credentials or purchase services. Configure HTTPS through the host. Write local/cloud README, architecture summary, limitations, final requirement traceability, and 5-minute demo script. Deploy only with available user authorization and credentials; complete reviewable configuration first if deployment is blocked.

Suggested commits: (1) container and demo access protection; (2) deployment instructions and deployment evidence; (3) final traceability/demo/handoff.

Gate/demo: another machine opens HTTPS app, authenticated chat works, route details shown, PostgreSQL persists across restart, benchmark view loads, keys remain server-side. Replay complete offline CI and final narrow smoke checks; do not add a load-testing program. Record URL without secrets, hosted model configuration, cost limits, and shutdown instructions.

## Suggested six-week pacing

Week 1: 00–01. Week 2: 02–03. Week 3: 04. Week 4: 05–06. Week 5: 07. Week 6: 08 and demo preparation. Pacing is adjustable; PR completion gates take priority over calendar dates.
