# Arbiter implementation status

Updated: 2026-11-06 UTC.

## Benchmark start button and live defaults (2026-11-06)

Standalone user-requested change directly on the current `master` branch, based on
`e1726f7` (merged dropdown PR #14). The user explicitly requested current-branch
changes and a push; no new phase branch, PR, merge, or Phase 08 progression.

- Added **Run benchmark** in Runs & benchmarks. A short POST persists the existing
  30-case development job with frozen settings/history and server-configured
  `BENCHMARK_BUDGET_USD` / `REQUEST_BUDGET_USD` ceilings, then schedules the existing
  runner in the API process. The job appears automatically; active jobs refresh
  every two seconds until completed, blocked, or uncertain. Duplicate clicks and
  overlapping web launches are blocked. Configuration and start/read errors are
  explicit; background failures release the slot and retain reservations.
- Changed Settings, environment fallback/template, ChatResult, and saved-run
  defaults to live. Updated the ignored local `.env` to `CHAT_MODE=live`, preserving
  all other values. CLI new jobs and the launcher already defaulted to live.
  Explicit offline fixtures and historical mock data retain truthful labels.
- Updated requirements/steering/design/setup/quality together to replace the
  former CLI-only development-job contract. Held-out comparisons remain CLI-only.
  No dependencies, worker service, schema changes, or paid requests were added.
- Backend focused check: `TEST_DATABASE_URL=postgresql://arbiter@127.0.0.1:55439/arbiter_test .venv/bin/pytest tests/test_web_benchmarks.py tests/test_jobs.py tests/test_config.py tests/test_db.py`:
  **51 passed**. Full same-database `.venv/bin/pytest`: **353 passed** with real
  PostgreSQL in a separate temporary test cluster and offline provider fixtures.
  `.venv/bin/ruff check .` / `.venv/bin/ruff format --check .`: passed (35 files).
  Initial lint found long new lines; formatting fixed them before tests.
- Frontend `npm run typecheck`, `npm run lint`, `npm run build`: passed.
  `CAPTURE_SCREENSHOTS=1 SCREENSHOT_PHASE=benchmark-button npm run test:e2e`:
  **14 passed** at desktop/mobile widths. After the final explanatory-text change
  and live-mode screenshot fixture, the affected `--grep 'benchmark button|benchmark start errors|results show'`
  checks passed again: **6 passed**; type/lint/build passed again.
- Visually checked [desktop completed](screenshots/phase-benchmark-button-benchmark-completed-desktop.png)
  and [mobile running](screenshots/phase-benchmark-button-benchmark-running-mobile.png).
  Screenshots are explicit offline fixtures; no live benchmark was started.
  Local research DB credentials did not allow a test connection, so all tests
  used the independent temporary cluster; research data was untouched.
- No implementation blockers. Changes are recorded by
  `feat(benchmarks): launch jobs from results and default to live`, followed by
  the immediately pushed status commit recording the exact implementation SHA.
  Next action: restart the API and refresh the frontend, then use
  **Runs & benchmarks → Run benchmark**. Keep the API running during jobs; after
  interruption use CLI resume with the existing uncertain-spend rules.

## Saved run and benchmark dropdown details (2026-11-06)

Standalone user-requested fix on `fix/run-detail-dropdowns`, based on updated
`master` at `4da846f` after summary PR #13 merged. Only the dropdown fix,
its tests, and evidence are included; the merged summary feature is preserved.
Phase 08 remains pending.

- Replaced ID-only dropdowns with on-demand reads of the existing run/job
  endpoints. Runs show saved conversation/answer, task and analysis, exact model
  IDs, routing reasons, escalation, evaluations, call errors, tokens, latency,
  and complete/incomplete costs. Benchmark jobs expose dataset/history IDs,
  case progress, and expandable linked runs. Failed loads have explicit retries.
- Frontend `npm run typecheck`, `npm run lint`, `npm run build`: passed.
  `npm run test:e2e`: **10 passed**, desktop/mobile, including the already merged
  summary download flow. An initial attempt was blocked by an orphaned test
  server from this session; stopping that server resolved the port conflict.
- `CAPTURE_SCREENSHOTS=1 SCREENSHOT_PHASE=restore-details npm run test:e2e -- --grep 'run and benchmark dropdowns'`:
  **2 passed**. Visually checked run [desktop](screenshots/phase-restore-details-run-details-desktop.png)
  / [mobile](screenshots/phase-restore-details-run-details-mobile.png) and benchmark
  [desktop](screenshots/phase-restore-details-benchmark-details-desktop.png)
  / [mobile](screenshots/phase-restore-details-benchmark-details-mobile.png).
  Expanded text fits narrow screens while summary tables remain scrollable.
- Backend `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`: passed
  (34 files). No backend code or schema changes; backend tests and paid provider
  checks were not repeated. All browser API traffic used offline fixtures.
- Implementation/evidence commit: `0ae4a7f`, immediately pushed. No blockers.
  R10/R13 evidence updated. Next action: open and review the separate fix PR
  against `master`; no merge or phase progression is included in this request.

## App-name capitalization (2026-11-06)

Standalone user-requested fix on `fix/capitalize-app-name`, based on `master`
at `8190fec`. The app header now displays **Arbiter**, matching the existing page
title and composer. Phase 08 remains pending.

- Frontend `npm run typecheck`, `npm run lint`, `npm run build`: passed.
- `CAPTURE_SCREENSHOTS=1 SCREENSHOT_PHASE=capitalize-name npm run test:e2e -- --grep 'keyboard chat'`:
  **2 passed**, desktop/mobile, offline API fixtures only.
- Visually checked [desktop](screenshots/phase-capitalize-name-chat-desktop.png)
  and [mobile](screenshots/phase-capitalize-name-chat-mobile.png) screenshots.
- No backend or paid checks needed for this text-only change. No blockers.
  Commit: `fix(ui): capitalize Arbiter in the app header`, with immediate push.
  Next action: review the standalone fix PR; no phase progression.

- Current phase: 07 — controlled benchmark, **complete and merged**. Phase 08 is pending.
- Repository/default branch: [1RaghavM/arbiter](https://github.com/1RaghavM/arbiter), `master`.
- Phase 06 [PR #7](https://github.com/1RaghavM/arbiter/pull/7) merged at `8b681e8` after independent review and [final CI](https://github.com/1RaghavM/arbiter/actions/runs/39680736653): **264 backend tests with real PostgreSQL and six browser tests passed**, with all lint/type/build gates green. Merge author and committer are the configured user.
- Current branch: `master`, containing Phase 07 merge `683c0d6`; completed phase branch: `phase/07-benchmark`.
- Authorization: user resumed delegated phase progression on 2026-10-21, approved **USD 5 total** for benchmark API work including independent grading, and selected **Vercel** for Phase 08. No hosting purchase is authorized or required by this selection.
- Phase 07 [PR #8](https://github.com/1RaghavM/arbiter/pull/8) merged at `683c0d601c0696c95c219b7e3ee0a0885899a2cb` after independent final review and passing required CI on `d654697`.
- Next action: Phase 08 may start from updated `master` when resumed. No Phase 08 work was included in this completion.
- Active replacement research database: private ignored `.local/research-20261105`, port 55434, `arbiter_research`; separate `arbiter_test` for fixtures. Root .env and other clusters were preserved. The original temporary database was lost; historical evidence and its spending allowance remain retained.
- All configured provider access gates have live evidence. The Google/Haiku recovery checks and full development/held-out experiment completed successfully. Final research results and limitations are recorded below and in `reports/benchmark.md`.

## Haiku easy-task candidate (2026-10-22)

User-requested addition on `phase/07-benchmark`: `haiku` / `claude-haiku-5-5` uses the existing Anthropic key and adapter, with a provisional easy-only quality prior of 0.85, 1,000 ms latency and rank 1. Medium/hard buckets exclude it. The ordinary weighted router selects it for the easy fixture; no prompt-specific rule was added. Sonnet remains the judge/strong baseline and OpenAI the fixed-cheap baseline. Verified ID/pricing/thinking references are in SOURCES.md. Haiku uses `thinking=disabled`; Sonnet keeps `between_tools`. Its 100k configured context ceiling bounds requests to the documented lower price tier.

- `.venv/bin/pytest tests/test_config.py tests/test_routing.py tests/test_providers.py`: **94 passed**, including Haiku SDK payload/cost and easy/medium/hard routing cases. `.venv/bin/pytest tests/test_evaluated.py tests/test_evaluation.py`: **72 passed**. All provider traffic was faked. An initial command referenced nonexistent `tests/test_pipeline.py` and collected no tests; the correct pipeline suite is `test_evaluated.py`.
- `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`: passed (31 files). No frontend code changed.
- Restarted local backend at `127.0.0.1:8000`; startup succeeded and `GET /api/config` lists Haiku with configured credentials. This is not proof of live Haiku account access: no paid call was made. Next action: try an easy prompt in the local UI; the new adapter is loaded.
- Commit `feat(models): add Haiku 5.5 for easy tasks`, immediately pushed to existing draft [PR #8](https://github.com/1RaghavM/arbiter/pull/8). Phase 07's Google billing blocker remains. Existing benchmark jobs retain their frozen three-model configuration; the protocol records the user-requested four-model change before any held-out freeze. No merge or next-phase work.

## Model-name display fix (2026-10-22)

User-requested small UI correction on `phase/07-benchmark`: answer summaries, first/final model fields, routing explanations, and attempts now display the exact `model_id` already returned by the API instead of the internal routing key. No backend, provider, or benchmark behavior changed.

- `npm run typecheck`, `npm run lint`, and `npm run build` from `frontend`: passed.
- `CAPTURE_SCREENSHOTS=1 SCREENSHOT_PHASE=model-ids npm run test:e2e -- --grep 'invalid input'`: **2 passed**, desktop and mobile, offline fixtures only. The sandbox initially blocked the local test server; the permitted rerun passed. [Desktop](screenshots/phase-model-ids-details-desktop.png) and [mobile](screenshots/phase-model-ids-details-mobile.png) screenshots visually checked.
- Fix and evidence committed together as `fix(ui): show exact model IDs in answer details` and immediately pushed to existing draft [PR #8](https://github.com/1RaghavM/arbiter/pull/8). No paid checks. Phase 07 remains blocked on billing; no merge or next-phase work is included. Next UI action: view an answer with the updated frontend.

## Phase 07 results and live blocker

Implemented 30 development + 30 held-out synthetic cases, objective and blinded rubric grading, fixed-cheap/fixed-strong/routed comparison, seeded order, frozen source/config/history, one durable runtime/scoring budget, resumable jobs, report export and independent strategy metrics in the UI. Independent pre-live review found no remaining code blockers after JSON numeric-equivalence and consistent database snapshot fixes. The final experiment is not complete.

- [CI on 953852a](https://github.com/1RaghavM/arbiter/actions/runs/39682496504): **318 backend tests passed with real PostgreSQL; six desktop/mobile browser tests passed**. Ruff lint/format and frontend type/lint/build passed. Offline providers only. Prior full local run: 317 passed; the subsequent snapshot fix passed 22 focused tests and final CI adds the regression. No repeated broad paid integration suite.
- Free CLI rehearsal in the test database: job `3205ac0b-9587-4b3f-aee4-d2b502bd941f` completed **90 runtime rows and 90 grading rows**, USD 0, with mock/no-research-conclusion labeling. Research records are in a separate database.
- Paid development command: `DATABASE_URL=postgresql://arbiter@127.0.0.1:55432/arbiter_benchmark .venv/bin/python -m app.jobs benchmark --dataset ../benchmarks/dev.jsonl --budget-usd 0.50 --request-budget-usd 0.25`. Job `1a09bbc5-f8f0-470e-be44-f1ea50bc7b8b` stopped as blocked after two completed cases, with 28 pending. Both Google generation attempts failed without usage, then Anthropic escalation passed its online judge. Known cost **USD 0.005209634**, incomplete; the job correctly retains **USD 0.50**, not the known subtotal, against its ceiling. [Full synthetic development evidence](../reports/development.json).
- One free official Google model metadata request returned HTTP 200 and supports generateContent. One affected-provider-only generation diagnostic through the existing smoke pipeline, capped at USD 0.01, returned **HTTP 402**. Run `54bdc268-0bb9-49a0-9b24-a1371c0130aa`; no usage, retained reservation **USD 0.0026437**. No retries. [Sanitized diagnostic](../reports/google-diagnostic.json). The exact error of the first two calls was not retained beyond `unavailable`; do not claim those statuses were observed as 402.
- The original development job has exhausted its immutable USD 0.50 ceiling: `--resume` alone cannot advance it after billing is fixed. Preserve that job and its reservations. Prepare a separately capped continuation dataset/job containing exactly its 28 pending case IDs, with the revised total allocation recorded first; do not rerun the two completed cases or silently increase the frozen ceiling.
- Aggregate conservative amount retained: **USD 0.5026437**; known usage subtotal **USD 0.005209634**. Actual charges remain incomplete. USD 4.4973563 remains below the approved USD 5 aggregate ceiling; reserve at most USD 4.49 for all subsequent work until an explicit revised allocation is recorded. No held-out calls, independent live grades, or manual triplet reviews exist yet. [Blocked benchmark report](../reports/benchmark.md).
- UI checks include [desktop](screenshots/phase-07-results-desktop.png) and [mobile](screenshots/phase-07-results-mobile.png), visually reviewed and explicitly fixture evidence.
- Commits, immediately pushed with user author/committer: `6430b64` protocol/pricing verification; `e2b283d` dataset/grading/runner/report; `4c69d8f` result UI; `953852a` consistent read snapshot. `b2d8517` preserves reviewed evidence/status, immediately pushed. A follow-up documentation commit records the created draft PR link.
- Requirements advanced: R09–R11 and R14; R11's actual three-strategy experiment remains blocked. Vercel CLI is installed and authenticated, but deployment is Phase 08 and has not started. No hosting purchase or project creation.

## Phase 06 results

Expanded answer details show task/difficulty/source/confidence, first/final model, attempt count and outcomes, routing reasons, escalation, latency, cost completeness and run ID. Recent-run and benchmark tables load on first visit and explicit refresh, retain chat state, handle empty/error states, and label mock data and online judge proxies. Read-only benchmark endpoints use persisted accounting and bounded list limits; no HTTP route starts jobs.

- Local `env -u TEST_DATABASE_URL .venv/bin/pytest`: **218 passed, 46 skipped**. `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`: passed, 26 files. Docker Desktop could not start; no local PostgreSQL pass is claimed.
- [CI e5e4389](https://github.com/1RaghavM/arbiter/actions/runs/39680222921): **264 passed**, real PostgreSQL; lint/format and frontend checks passed. Final UI/browser head CI remains the merge gate.
- Frontend `npm run typecheck`, `npm run lint`, `npm run build`: passed, zero lint warnings. Pinned Playwright 1.64.1; Vite patched from 8.3.0 to 8.3.5 after npm audit identified advisories; install audit reports zero vulnerabilities.
- Final serial `CAPTURE_SCREENSHOTS=1 npm run test:e2e`: **6 passed** (three flows at 1280px desktop and 390px mobile). Covers two-turn context, keyboard input, duplicate prevention, new chat, invalid input, 503/retry, incomplete cost/escalation metadata, result empty/populated/error states, manual refresh and narrow-table keyboard scrolling. A preceding concurrent test attempt collided in temporary trace artifacts; the serial rerun passed. All API traffic is intercepted, including an unmatched-request blocker; no paid calls.
- Eight screenshots visually inspected: [chat desktop](screenshots/phase-06-chat-desktop.png), [mobile](screenshots/phase-06-chat-mobile.png), [details desktop](screenshots/phase-06-details-desktop.png), [mobile](screenshots/phase-06-details-mobile.png), [error desktop](screenshots/phase-06-error-desktop.png), [mobile](screenshots/phase-06-error-mobile.png), [results desktop](screenshots/phase-06-results-desktop.png), [mobile](screenshots/phase-06-results-mobile.png). Fixtures are explicit offline evidence, not live research results. Earlier cleanup screenshots are preserved.
- Delegation: API agent implemented benchmark reads/tests; UI agent implemented components; browser agent implemented regression suite and CI; separate reviewer audits the full PR and owns merge. API agent's independent frontend review and separate reviewer's initial full review found no blockers.
- Commits, each immediately pushed with configured user as author/committer: `e5e4389` benchmark API, `2bc74b9` interface, `a299293` browser suite/evidence. Documentation follows in its own immediately pushed commit.
- Requirements advanced: R01, R10, R13, R14. No changes to provider integrations, routing policy, or paid checks. Independent scoring/three-strategy results remain Phase 07; deployment access protection remains Phase 08.

## Local live setup fix (2026-10-11)

User requested automatic `.env` loading and a working local live system while phase progression remains paused. API startup, migrations, provider smoke, and benchmark/report entry points now load the root `.env` before configuration/database reads. Shell variables retain precedence; interpolation is disabled. Tests redirect env-file loading to a temporary path. python-dotenv 1.2.4 is pinned and locked; existing provider integrations are unchanged.

- Checks: `TEST_DATABASE_URL=postgresql://arbiter:arbiter@localhost:5432/arbiter_test .venv/bin/pytest` from backend: **261 passed**, real PostgreSQL and offline providers. `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`: passed, 26 files. Frontend `npm run typecheck`, `npm run lint`, `npm run build`: passed. Independent subagent review found no blockers. No UI behavior changed.
- `env -u DATABASE_URL -u CHAT_MODE .venv/bin/python -m app.db` succeeded using the root `.env`. Backend restarted with DATABASE_URL, CHAT_MODE and REQUEST_BUDGET_USD unset in its launch environment to verify file loading; frontend proxy `/api/config` reports live and all three generators available.
- Initial USD 0.05 request ceiling rejected the arithmetic test before paid work; run `6882683b-f6fa-48a9-a7e2-6973ca9969bc` has zero calls and zero cost. The worst-case judge reservation alone was USD 0.133955. User explicitly approved increasing local REQUEST_BUDGET_USD to **0.25** and one live check.
- One live request through Vite `/api/chat`: “What is 6 multiplied by 7? Reply with only the number.” Run `934a7910-165c-4e84-82f1-b5239dfb3949`: Jev → Google answer `42` → Anthropic judge, status passed, 3,002 ms, complete reported usage, estimated **USD 0.002020092**. Persisted run inspected through `/api/runs/{id}`. No extra provider smoke or benchmark calls.
- Local `.env` remains ignored, credentials preserved, CHAT_MODE=live. Backend at `127.0.0.1:8000`, frontend at `127.0.0.1:5173`; refresh the browser to load live configuration. Budget is a conservative reservation ceiling, not expected spend or an invoice guarantee.
- Branch: `phase/05-history-jobs`; fix and evidence are included together in the next commit (`git log -1` identifies it), immediately pushed to existing [PR #6](https://github.com/1RaghavM/arbiter/pull/6). No merge or next-phase work in this request. Next action: test the live UI; resume phase progression only when requested.

## Phase 05 results

Live requests load one content-addressed compatible history snapshot. Routing uses per-attempt smoothed quality and median latency/output after five known labels. Unknown judgments remain unknown; provider errors count against reliability. The sequential benchmark/report CLI freezes dataset, settings, registry, history and runtime versions, reserves before calls, skips completed cases, retains uncertain spend and requires explicit uncertain retries.

- `TEST_DATABASE_URL=postgresql://arbiter:arbiter@localhost:5432/arbiter_test .venv/bin/pytest`: **259 passed** with real PostgreSQL and offline providers. `.venv/bin/ruff check .` / `.venv/bin/ruff format --check .`: passed, 25 files. Prior focused checks: 38 history/routing, 57 integration/pipeline, 12 jobs tests passed. No extra paid checks.
- History tests prove seeded compatible attempts change selection, threshold fallback, per-attempt failures versus later success, unknown denominators, exact model/judge compatibility and excluded mock/held-out/baseline/old-policy records. `history-v1` intentionally excludes `priors-v1`; the policy starts cold instead of silently mixing versions.
- Jobs tests cover persisted reservation caps, unknown costs, crash/uncertain recovery, immutable settings/history, incompatible runtime versions, concurrent-run rejection, no completed-case replay, and retained prior run IDs/known partial costs after an explicit retry.
- One actual CLI job: `DATABASE_URL=postgresql://arbiter:arbiter@localhost:5432/arbiter_test .venv/bin/python -m app.jobs benchmark --dataset ../benchmarks/dev.jsonl --budget-usd 0.25 --request-budget-usd 0.25 --mock`. Job `f5b544f2-221f-4f0f-8926-e5a93dbba501` completed all six cases, all mock/unverified, USD 0. Separate `benchmark --resume ID` and `report ID` processes returned the identical report with one attempt per case. [Sanitized evidence](phase-05-mock-job.json). This is persistence/runner evidence, not a live research benchmark.
- Independent reviews fixed SQL bucket precedence, frozen policy/rubric/classifier validation before resume, retention of uncertain attempt provenance and partial known costs, and incorrect complete-cost reporting before crash recovery. Reviewers found no remaining material code issue; final PR CI/head remains the merge gate.
- Delegation: history agent implemented history/router with PostgreSQL tests and independently reviewed job transaction/accounting logic; jobs agent implemented CLI/schema/dataset/tests; reviewer audited both and owns merge. Root integrated storage/pipeline, ran full gates and CLI evidence.
- Commits, each immediately pushed: `19b694b` historical routing, `a960305` frozen resumable jobs/integration. Documentation/evidence follows; `git log -1` identifies that commit.
- [CI on a960305](https://github.com/1RaghavM/arbiter/actions/runs/38163774356) passed backend and frontend. Secret-value and whitespace checks passed. Demo database migrated and ordinary API restored in mock mode.
- No frontend behavior changed in this phase; prior browser evidence applies and CI reruns frontend gates. No paid API calls. The job command has no HTTP trigger; independent scoring/three-strategy held-out experiment remains Phase 07. Online history is a biased proxy and reservations are not invoice guarantees.

## Phase 04 results

Fixed Anthropic structured evaluation now checks each usable answer, with deterministic empty/truncated failures, explicit unknown grades, and at most one escalation. Classifier, generation and judge attempts commit before another paid stage. Generation reserves judge time/cost in advance; unknown cost consumes its reservation. Maximum paid calls are five. The UI distinguishes judge-passed, quality-failed and unverified answers, and shows escalation.

- Full offline CI on `6179d61`: **222 passed**, PostgreSQL included; backend Ruff and frontend gates passed. [CI evidence](https://github.com/1RaghavM/arbiter/actions/runs/38162879069). Local first full run had 218 passes and two failures: retry filtering replaced original timeout/empty-response error categories. Fixed that cause, added two regressions, and reran 28 focused pipeline tests and four affected PostgreSQL tests successfully before CI.
- `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`: passed, 21 Python files. From frontend, `npm run typecheck`, `npm run lint`, `npm run build`: passed after UI changes. Storage tests confirm attempt durability through a fresh connection; evaluator/provider fixtures validate strict scores, malformed output, native SDK schema serialization and usage preservation.
- One normal live request on 2026-10-11 under USD 0.25: Jev → Google answer `42` → Anthropic judge scores 4/4/4. Run `69429b42-4431-47e6-a5f4-4415a9dee1ed`, three paid calls, complete reported usage, total estimated USD **0.002014434**, 3,848 ms. [Sanitized evidence](phase-04-live.json). No repeated provider smoke calls.
- Offline controlled escalation in `arbiter_test`: initial Google failure → Anthropic pass, five stages and two attempts; simulated costs/grades clearly labeled and excluded from research. [Fixture](phase-04-controlled.json). Keyboard submission and desktop/mobile labels passed using this replay without new paid calls. [Desktop](screenshots/phase-04-desktop.png), [mobile](screenshots/phase-04-mobile.png). Normal free mock API restored afterward.
- Delegation: provider agent implemented evaluator and structured provider output; UI/pipeline agent implemented bounded orchestration and focused tests; review agent independently reviewed storage, evaluator and connected pipeline. Root integrated, checked PostgreSQL/UI, and ran the one bounded live request.
- Review fixed missing judge reservation before generation and preservation of original provider errors when escalation is unavailable. Final code review found no remaining blockers; final PR head/CI review remains the merge gate.
- Commits, immediately pushed: `eea2b69` storage, `bef97bd` evaluator, `6179d61` bounded pipeline, `e655cce` UI/screenshots. Documentation/evidence follows; `git log -1` identifies that commit.
- Limits: online judge approval is a biased quality signal, not factual proof; provisional priors remain uncalibrated. USD 0.25 is a conservative ceiling, not expected spend. Timeout billing may be unknown; provider limits remain necessary. No history/jobs or benchmark comparison yet.

## Phase 03 results

Live chat now classifies with official Jev and selects a model using a pure, inspectable router. Full context, explicit confidence fallback, context/budget/deadline filters, stable ties, and candidate scores are implemented. Classifier usage persists before generation; both costs aggregate, with unknowns retained. Mock remains free and the provider CLI still calls only its selected generators. The UI shows selected model and routing reason.

- Offline suite: `TEST_DATABASE_URL=postgresql://arbiter:arbiter@localhost:5432/arbiter_test .venv/bin/pytest` passed 145 tests before review fixes; 24 affected integration tests then passed including two new regressions. The Jev model-mismatch fix passed four focused cases. [CI on 93dce0f](https://github.com/1RaghavM/arbiter/actions/runs/38162025040) passed the final 147-test suite and frontend checks. Initial local PostgreSQL tests were blocked by sandbox networking; rerunning with approved local access passed.
- Backend Ruff lint/format passed for 18 files. Frontend typecheck/lint/build passed. Browser keyboard submission and desktop/mobile route labels passed using an explicitly labeled offline replay of existing evidence, avoiding new paid calls. Screenshots: [desktop](screenshots/phase-03-desktop.png), [mobile](screenshots/phase-03-mobile.png). Vite required restart after the branch switch; no code workaround was needed.
- Two live development examples on 2026-10-11: easy extraction → Jev confidence 1.0 → Google, answer Boston, total USD 0.00003496; difficult reasoning → Jev confidence 0.69 → Anthropic, total USD 0.010464308. Four calls total (two classifier, two generator), no retries, combined USD 0.010499268 under USD 0.10. Full sanitized run IDs, usage, scores and answers are in [phase-03-development.json](phase-03-development.json).
- The difficult answer reached 1,024 tokens and is labeled truncated/unverified. Priors are engineering assumptions, not measured pass rates; no quality/savings claim or held-out tuning. No evaluator/escalation implementation yet.
- Delegation: provider agent implemented/tested Jev; UI agent implemented/tested the pure router and independently reviewed Jev; review agent reviewed pipeline/persistence and merged prior PR #3. Root integrated, checked UI, and made the bounded live calls.
- Reviews fixed unexpected-model pricing (unknown cost), exhausted post-classifier deadline (504), and added persistence-failure coverage before generation. Follow-up review found no blockers. No extra paid checks were used.
- Commits, each pushed immediately: `809641b` standing workflow/start; `602172a` Jev; `dcb7f82` routing/persistence; `93dce0f` UI/screenshots. Final documentation/evidence commit follows; `git log -1` identifies it.
- Mock API restored at localhost:8000 and Vite at localhost:5173; replay fixture stopped. Keys remain in ignored local .env, never committed or exposed in the frontend.

## Previous phase evidence (Phase 02)

### What works

Three official SDK adapters normalize text, finish reason, tokens, raw usage, price snapshots, latency, and safe error categories. OpenAI cached input, Anthropic separate cache usage, and Google thinking output have distinct accounting. Costs use Decimal; unknown usage stays unknown. No retries occur. Async SDK calls have a whole-stage cancellation deadline as well as network timeouts.

The backend selects one configured model for temporary live chat. It checks credentials, context, explicit spend ceiling, and remaining generation time. It creates the run before paid work and stores successes and failures in the existing PostgreSQL schema. A shared small pipeline serves the API and sequential smoke CLI. Mock mode remains the default and never silently substitutes for unavailable live models. The UI loads safe server configuration, shows missing credentials, distinguishes mock/live replies, and displays unverified quality, estimated/unknown cost, and truncation warnings.

Official model IDs/prices and current SDK behavior are documented in [SOURCES.md](SOURCES.md). Setup, environment, local smoke, and shutdown commands are in [SETUP.md](SETUP.md). No routing, Jev, evaluator, escalation, benchmark jobs, or deployment was added.

## Evidence

Commands run from `backend/` unless otherwise indicated. `.venv/bin` uses the lockfile-installed environment.

| Check | Result |
| --- | --- |
| `UV_PROJECT_ENVIRONMENT=/tmp/arbiter-phase02-runtime uv sync --locked --no-dev` | PASS: clean runtime-only install; app import and three registry entries validate without test packages |
| `.venv/bin/ruff check .` / `.venv/bin/ruff format --check .` | PASS: 14 Python files |
| `TEST_DATABASE_URL=postgresql://arbiter:arbiter@localhost:5432/arbiter_test .venv/bin/pytest` | PASS: 97 tests, none skipped |
| Provider tests within that suite | PASS: 46 tests using real SDK serialization/parsing with offline async HTTP transports; all three roles/usage/cache/thinking mappings, timeout/auth/rate-limit/invalid/blocked/empty/truncated paths, and cancellation |
| Real PostgreSQL integration | PASS: existing migrations/round trip, mock chat, fixed-live fixtures, known/unknown costs and failed calls, no call before DB success, invalid output cleared while usage persists |
| Smoke safety tests | PASS: aggregate preflight, missing credentials, invalid CLI budgets, unknown-cost reservations, observed-cost exhaustion, stop after persistence failure, expired pre-call deadline |
| Initial smoke with `--budget-usd 0.05` | BLOCKED: all three credentials initially missing; no paid calls made |
| `.venv/bin/python -m app.smoke --budget-usd 0.01 --models openai`, with local `.env` values supplied privately | BLOCKED: real OpenAI request returned `rate_limit`, no answer; run `2d6fb547-3d42-44ff-8319-478fc39097d2` persisted, cost unknown, reservation USD 0.00175; no retry |
| User-authorized OpenAI retry with the same `--budget-usd 0.01 --models openai` command after access was resolved | PASS: `smoke OK`; run `a96f5fec-c598-4d4a-8167-1c2abe75c8ff`; observed-usage cost estimate USD 0.0000112, complete usage; reservation USD 0.00175. Exactly one call, no automatic retries |
| `.venv/bin/python -m app.smoke --budget-usd 0.05 --models anthropic google`, after the user supplied keys | PASS: one call each, both returned `smoke OK`; complete usage. Anthropic USD 0.000106, Google USD 0.0000068; combined estimate USD 0.0001128, no retries |
| `npm run typecheck`, `npm run lint`, `npm run build` from frontend | PASS |
| `docker compose up -d --wait db` from root | PASS: local PostgreSQL 17.6 healthy; existing arbiter_test database reused |
| Browser, 1280×900 and 390×844 | PASS: mock two-turn context, pending controls, live missing-key disablement, config failure/retry, factual known/unknown cost and truncation labels using an explicitly labeled offline UI fixture |
| `git diff --check`, relative documentation links, staged files/attribution | PASS: named files reviewed; configured user author/committer, no private artifacts |
| [GitHub CI on UI commit 01bce09](https://github.com/1RaghavM/arbiter/actions/runs/38159114544) | PASS: backend with PostgreSQL and frontend; final documentation commit also runs CI |

Screenshots: [desktop mock](screenshots/phase-02-desktop.png), [mobile mock](screenshots/phase-02-mobile.png), [live credentials blocked](screenshots/phase-02-live-blocked.png), [configuration error](screenshots/phase-02-config-error.png), [offline UI fixture](screenshots/phase-02-offline-fixture.png). The last screenshot is **not** live provider evidence; its synthetic records are confined to `arbiter_test`.

## Delegation and review

- Provider subagent researched current Anthropic/Google official contracts and implemented the three adapters with offline SDK transport tests.
- UI subagent implemented the minimal mock/live-compatible screen, ran frontend gates, then independently reviewed the other agent's provider code.
- Review subagent independently reviewed configuration, pipeline, API, persistence, smoke budgets, and connected tests; reran eight smoke-focused tests.
- Root integrated the work, reviewed connected code, ran the complete PostgreSQL suite and browser checks, and owns every commit/push.

Reviews found and fixed: inactivity timeouts that did not bound the whole call; NUL/surrogate output that could lose usage during persistence; a second partial-parse path bypassing that sanitation; nullable disabled model IDs rejected by the UI; and invalid CLI budgets producing a traceback. Regression tests cover each backend finding, and the UI nullable contract passes type/lint/build checks. Final independent reviews reported no remaining blocking code findings. An initial surrogate test fixture failed while encoding its fake HTTP response; emitting escaped JSON corrected the fixture and all 97 tests passed. No required check was waived.

## Live evidence and limits

All three configured generation providers returned real `smoke OK` responses on 2026-10-11. Keys were supplied privately from the ignored local `.env`; no values were printed or committed. Jev remains Phase 03 work.

| Provider/model | Persisted run ID | Usage-based cost estimate (USD) | Reservation (USD) |
| --- | --- | --- | --- |
| OpenAI / gpt-4.1-mini-2025-04-14 | `a96f5fec-c598-4d4a-8167-1c2abe75c8ff` | 0.0000112 | 0.00175 |
| Anthropic / claude-sonnet-5-5 | `3306785c-99cf-41db-a981-c1ccaac4e469` | 0.000106 | 0.0109375 |
| Google / gemini-3.5-flash-lite | `86e0af99-6638-4742-9671-36318233d299` | 0.0000068 | 0.0026437 |

Each successful check used exactly one call with complete reported usage and no automatic retries. OpenAI used a USD 0.01 command ceiling; Anthropic/Google shared USD 0.05. Their combined new cost estimate is USD 0.0001128; the three successful checks total USD 0.0001240. The earlier failed OpenAI rate-limit attempt remains recorded with unknown cost, so these totals exclude that unknown charge. Reuse this evidence instead of making more paid calls.

Record sanitized output/run IDs and actual costs or access failures. Unknown billing after timeout consumes a reservation and stays incomplete. Reservations and API-usage prices are estimates; use provider-side limits too. The async generation cap is at most 60 seconds and reduced by the remaining 90-second request allowance; separate DB finalization can extend beyond it. No claim of a hard HTTP request deadline is made in this phase.

All live-shaped test records are synthetic and remain in the test database, which must never feed benchmark/history evidence. Capability ranks/quality priors are unset until Phase 03 development evidence. All answers remain unverified. Process crashes may leave a running record; persistence errors can leave partial records, with no automatic retry. Local access remains unauthenticated and bound to localhost; deployment protection belongs to Phase 08.

The ordinary mock API/frontend and PostgreSQL were restored and left running at `http://127.0.0.1:5173`. The temporary offline fixture server is stopped.

## Commits and publishing

Each commit uses `1RaghavM` as author/committer and was immediately pushed before making another commit.

| Commit | Change |
| --- | --- |
| `7e2d784` | Verified model registry, Decimal pricing, safe settings/reservations, SDK locks |
| `970f0e5` | Official provider adapters, whole-stage deadlines, usage accounting, offline transport tests |
| `b1eeb46` | Fixed-model pipeline, persistence, bounded smoke CLI, integration/safety tests |
| `01bce09` | Availability-aware UI, honest cost/quality labels, labeled browser evidence |

`ce42a33` recorded the initial handoff; `fdc337e` recorded OpenAI success and the minimal-paid-testing preference. The final evidence update records Anthropic/Google success; its hash is available with `git log -1 --oneline`. These updates change no runtime code, so prior 97-test/frontend results remain applicable. Documentation diff review and a secret-value check are the relevant local checks. CI on `fdc337e` passed both backend and frontend.

## Phase ledger

| Phase | State | Branch | PR | Evidence |
| --- | --- | --- | --- | --- |
| 00 | merged | phase/00-foundation | [#1](https://github.com/1RaghavM/arbiter/pull/1) | Foundation checks in merged history |
| 01 | merged | phase/01-chat-slice | [#2](https://github.com/1RaghavM/arbiter/pull/2) | Merged history and passing CI |
| 02 | merged | phase/02-cloud-models | [#3](https://github.com/1RaghavM/arbiter/pull/3) | Offline gates and all three live checks pass |
| 03 | merged | phase/03-jev-routing | [#4](https://github.com/1RaghavM/arbiter/pull/4) | Offline checks and live Jev/routing trace pass |
| 04 | merged | phase/04-evaluation | [#5](https://github.com/1RaghavM/arbiter/pull/5) | 222 offline tests, normal live flow and controlled escalation pass |
| 05 | merged | phase/05-history-jobs | [#6](https://github.com/1RaghavM/arbiter/pull/6) | Merged at 15dc2b4; offline and persisted mock-job gates pass |
| 06 | merged | phase/06-demo-ui | [#7](https://github.com/1RaghavM/arbiter/pull/7) | Merged at 8b681e8; 264 backend and six browser tests pass |
| 07 | merged | phase/07-benchmark | [#8](https://github.com/1RaghavM/arbiter/pull/8) | Merged at 683c0d6; required CI and independent review passed; full live comparison and ten agent triplet reviews complete |
| 08 | pending | — | — | — |

Allowed states: pending, in_progress, blocked, ready_for_review, merged. A phase becomes a dependency only after its PR is merged.


## Benchmark continuation infrastructure (2026-11-04)

User requested benchmark-only work on a new branch and a concise PR. Branch
`benchmark/pending-development` starts from `phase/07-benchmark` at `edc1d6e`;
its PR targets that branch so the existing incomplete experiment remains separate.
This is an explicit exception to the usual one-branch-per-phase workflow.

- Added `export-pending JOB_ID --output PATH`: exports frozen, unattempted
  development cases under the runner lock without changing records or reservations.
  Rejects uncertain/running work and existing files. Commit `b43a8b3`, pushed immediately.
- Focused PostgreSQL job tests: 22 passed. Ruff lint and format checks passed.
- The prior `/private/tmp/arbiter-phase07-postgres` directory is absent and port
  55432 is unavailable. Tests use a new isolated cluster on port 55433 and only
  `arbiter_test`. No research database was created or reconstructed.
- Live experiment remains BLOCKED: recorded Google billing failure, unverified
  Haiku access, and unavailable original research database. No paid calls made.
- Next action: restore research database records from a durable backup; inspect
  the original job/accounting, restore Google billing, export the pending cases,
  record the revised allocation, and verify affected providers before continuation.
  No deployment or Phase 08 work. Preserve the pre-existing uncommitted restart note.

- Final verification: 328 backend tests passed with real PostgreSQL and offline
  providers; Ruff lint/format passed. Initial full run had one stale smoke-budget
  fixture after Haiku was added; corrected it to exhaust the budget explicitly.

- PR: https://github.com/1RaghavM/arbiter/pull/9 (base `phase/07-benchmark`).
  Frontend typecheck/lint/build passed. Independent review found no code blockers
  and passed 47 focused PostgreSQL tests. PR #9 merged into Phase 07 at `d40881c`; live gates remain blocked.
  Implementation commits: `b43a8b3`, `63d68c0`, each immediately pushed.
## Requested local setup shortcut (2026-11-04)

Standalone user-requested change on `feat/make-app`, based on `origin/master`
(the repository has no `main` branch); no phase progression or benchmark work.
`make app` checks the local env, requires Jev plus one generator, installs locked
packages, migrates PostgreSQL, builds and serves the frontend with an API proxy,
and prints the localhost URL after a successful database-backed readiness read.
Busy ports use alternatives. Ctrl+C cleans up app servers; database data persists.

Validation: `uv run --frozen pytest tests/test_launcher.py`: 7 passed;
Ruff check and format check for launcher/tests passed. Frontend `npm run typecheck`,
`npm run lint`, `npm run build`: passed. No paid requests or full Docker startup
rehearsal performed. Next step: review the setup PR and try `make app` with Docker
running and configured keys. Existing uncommitted benchmark STATUS work is
preserved in stash `pre-make-app-status` on its original branch.

## Merge-readiness repair (2026-11-05)

Merged current master (`e9e9b8f`) into `phase/07-benchmark`, preserving both
benchmark and one-command setup documentation. Resolved the two append conflicts
in SETUP and STATUS. Added `.local/` to gitignore to exclude local database files.
User confirmed Google billing restored; this supersedes the earlier billing blocker,
but is not a successful generation check. No paid calls were made.

Original temporary research cluster remains absent. No dump/backup was found
in Downloads or Documents within four directory levels. A local cluster at
`.local/postgres-55432` is running and requires password authentication; the
configured DATABASE_URL connection failed. Its contents are unverified and its
access controls were preserved. Restore access to the original research records
before exporting pending cases; do not fabricate records from report summaries.

Latest pre-merge CI at `d40881c` passed backend/frontend. The previous review's
master-only test results are not Phase 07 validation. This merge changes no
Phase 07 runtime code; whitespace/conflict checks are the local validation,
and CI must validate the combined branch. Required live comparison, grading,
and ten triplet reviews remain incomplete. PR #8 stays draft and must not merge.

## Replacement live records (2026-11-05)

User explicitly authorized fresh calls after loss of the original database.
Created a separate password-protected cluster in ignored `.local/research-20261105`,
localhost port 55434, database `arbiter_research`; credentials remain private.
No existing cluster or root .env was changed. Applied all migrations successfully.

- `python -m app.smoke --budget-usd 0.02 --models google haiku`: both passed,
  one call each, complete usage, USD 0.0000121 combined.
- `python -m app.jobs benchmark --dataset ../.local/research-20261105/dev-two.jsonl
  --budget-usd 0.50 --request-budget-usd 0.25`: completed two live development
  cases, both routed to Haiku and passed the online judge; USD 0.004676734,
  complete usage. Job `4d913175-a250-44f7-9f23-62810acb1efb`.
- New estimated cost USD 0.004688834. Retaining old unknown-cost allowance
  USD 0.5026437 leaves USD 4.492667466 of the approved USD 5 total.
- `pg_dump -Fc` succeeded; private backup `.local/research-20261105/research.dump`,
  mode 0600. Provider and development results committed under reports/.
- This is replacement work, not recovered records. The two passes are online
  proxies, not independent held-out quality. Remaining 28 development cases,
  90 held-out strategy rows, independent grading and ten reviews still required.
  PR #8 must remain draft. No runtime code changed; JSON/whitespace checks passed.

## Phase 07 completed experiment (2026-11-06)

All 30 replacement development cases completed across jobs
`4d913175-a250-44f7-9f23-62810acb1efb` (first 2) and
`1bcdd027-23cc-4bf1-86eb-85fa26ad8197` (remaining 28). The latter cost
USD 0.092312746 with complete usage and 27/28 online-proxy passes.
Historical lost-job evidence and its retained USD 0.5026437 remain preserved.

Held-out job `b733763d-7376-434f-a2af-286cd31ab57b` froze source `5f70d56`,
dataset/config/prices/history/scorer and seed 20261021 before calls.
`python -m app.jobs freeze --dataset ../benchmarks/test.jsonl --budget-usd 3.74
--request-budget-usd 0.25 --scorer anthropic --seed 20261021`, then
`benchmark --resume ID` completed 90 runtime + 90 grading rows. Exported
`reports/benchmark.json`, `benchmark.md`, `manual-review.json` and `manual-key.json`.
Ten triplets were inspected blinded before reading the key, explicitly labeled
Codex agent review, not human review. Generated code was inspected, never run.

Independent passes: fixed-cheap 23/30, fixed-strong 24/30, routed 25/30.
Runtime USD: 0.0023872 / 0.025598 / 0.092456314 respectively. Median latency
ms: 813 / 1343.5 / 2387.5. Routed quality difference +3.33 pp; cost savings
-261.2%, median latency savings -77.7%. The frozen target was NOT met.
No runtime errors, unknown grades or unknown new costs. Scoring cost USD
0.152456 separately; total comparison USD 0.272897514.
New calls this recovery total USD 0.369899094; adding historical retained
allowance yields USD 0.872542794 against USD 5. No further paid checks needed.
Private `pg_dump -Fc` backup refreshed after jobs/export, mode 0600.

Checks: 335 backend tests passed with real PostgreSQL in separate arbiter_test;
Ruff check/format passed (32 files). Frontend typecheck/lint/build passed;
six Playwright desktop/mobile tests passed. Independent reviewer passed 47
focused tests and found no code blocker. JSON/whitespace/secret checks passed.
Final CI/current-head independent review remain the merge boundary.

The report discloses small synthetic sample size, scorer/candidate overlap,
agent-review limitations, strict-output formatting effects, price estimates,
sequential timing and replacement database provenance. No tuning on held-out
results, no paid replay, no deployment work.
## Local launcher database fix (2026-11-05)

User-requested follow-up on `feat/make-app`, independent of the blocked Phase 07 experiment. Local DATABASE_URL values now provision PostgreSQL using installed native binaries (including Homebrew 17), falling back to Compose. Native clusters persist under ignored `.local/postgres-PORT`; existing reachable databases are reused, occupied inaccessible ports and remote failures are reported without replacing them. New clusters do not restore historical research data.

Validation: `uv run pytest tests/test_launcher.py -q`: 9 passed; Ruff check/format passed. A real temporary PostgreSQL cluster passed creation, stop/restart with a preserved row, and reuse. `make app` completed migrations, npm install/build, and API/proxied database-read readiness; app available on localhost:5173. No paid calls. Docker fallback was not exercised on this machine. Fix will be committed and immediately pushed; next action is review the launcher PR. Phase 07 billing gate remains unchanged.

Final merge synchronization: merged master `49b349c` (PR #11 local setup fix),
preserving both appended status sections. Benchmark runtime/frozen artifacts unchanged;
final combined-head CI remains required.

## Phase 07 merge verification (2026-11-06 UTC)

Independent reviewer verified final head `d654697`, reproduced every reported
metric from the frozen export and validated all ten qualitative reviews. All
180 comparison rows finished in exactly one attempt; dataset hash/balance,
development separation, complete grading, costs and source freeze passed.
Focused review checks: 47 grading/report tests and Ruff passed. No unresolved
blocking finding remained.

Required backend/frontend CI passed on both push and PR runs at that head:
[runs/42164282981](https://github.com/1RaghavM/arbiter/actions/runs/42164282981) and
[runs/42164287691](https://github.com/1RaghavM/arbiter/actions/runs/42164287691).
Reviewer merged PR #8 with a normal merge commit `683c0d6`, using the configured
user as sole author and committer, and immediately pushed to master. GitHub
confirms MERGED. No additional paid calls or Phase 08 work.

## Selected-run Markdown summaries (2026-11-06)

Standalone requested feature on feat/run-summaries; Phase 08 remains pending.
Adds completed-run selection, older-run loading and one Sonnet 5.5 Markdown report
with saved conversations/results and project context. Separate durable summary
reservations/results prevent contamination of benchmark/history accounting.

- Backend Ruff check passed; four focused fake-provider summary tests passed.
- Frontend typecheck/lint/build passed; focused Playwright download test passed
  on desktop and mobile (2 tests). Screenshots: phase-summary-summary-*.png.
- Combined summary/DB/chat test invocation: 7 passed, 5 database setup errors:
  PostgreSQL requires a password on both documented port 55434 and configured
  port 55432. Migration/real PostgreSQL summary persistence is not yet verified.
- No paid requests. Existing Sonnet adapter reused; summary output quality/live
  workflow remains unverified. Apply migration 005 before use.
- Concurrent expandable-details work was preserved separately. The user stopped
  that task and requested focus on summaries.
- Integration isolation: the stopped task had changed the checkout branch during
  this session. Summary commit dfd97da was pushed to feat/run-summaries; follow-up
  removes leftover expandable-detail markup from the isolated commit. Other task
  edits remain uncommitted. The isolated summary frontend build and two browser
  download tests passed after correction; screenshots were regenerated.
- Next action: review the summary PR, supply a working test-database connection,
  verify migration/persistence, then apply migration 005 to the app database.

## Summary CI fixes (2026-11-06)

PR #13 at 05c59cc failed on two stale test assumptions introduced by the summary
feature: test_db expected four migrations after adding migration 005, and the
existing results browser fixture matched the runs URL without its new offset=0.
CI had 340 backend passes/one failure and six browser passes/two failures
(desktop/mobile instances of the same result-view fixture). These were missed
by the earlier focused checks; the CI failures were not database-access errors.

Updated the migration count and exact browser fixture URL. Verification used a
clean tracked-file snapshot plus these fixes, excluding preserved concurrent edits:

- Fresh disposable PostgreSQL 17 on loopback port 55439, database arbiter_test;
  full backend pytest -q: **341 passed**. Cluster stopped after the run.
  Ruff check and format --check: passed (34 files).
- Frontend npm run typecheck, npm run lint, npm run build: passed.
  npm run test:e2e: **8 passed**, desktop/mobile, all provider traffic faked.
  Linked node_modules caused Vite font allow-list warnings in the temporary copy;
  no UI changes/screenshots were evaluated in this test-only update.
- The first archive-based backend rehearsal lacked Git metadata needed by six
  comparison tests (335 passed, six failed); providing read-only GIT_DIR metadata
  for the full rerun produced the 341-pass result above.
- No paid calls. Actual Sonnet summary quality and live summary persistence remain
  unverified. PR stays draft; Phase 08 remains pending.
- Next action: verify CI on the fix commit, then review the summary feature.
