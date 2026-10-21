# Local setup

Use Node.js 24 (`nvm use` if available), uv 0.8.0 or newer, Python 3.12, and Docker with Compose. uv can download Python when needed.

## Install

From the repository root:

```sh
cp -n .env.example .env
cd backend
uv sync --locked
cd ../frontend
npm ci
```

Keep `.env` local. Its database credentials are for the local demo container only. Provider keys may stay blank in default mock mode. Live mode requires explicit provider credentials and a positive request budget; benchmark jobs also require a separate positive total ceiling.

## Start PostgreSQL and migrate

From the repository root, with Docker running:

```sh
docker compose up -d --wait db
cd backend
uv run --frozen python -m app.db
```

The API, migrations, smoke CLI, and benchmark/report CLI automatically load the repository-root `.env` at startup, including when launched from `backend/`. Existing shell variables take precedence. Values are literal (no `${VARIABLE}` expansion). A missing `.env` is allowed when configuration is supplied by the environment. Restart the backend after changing `.env`; for another database, set `DATABASE_URL` privately.

Migrations are numbered SQL files, applied in filename order in a transaction and tracked in `schema_migrations`. Running the migration command twice is safe. Run it before starting the API; startup never drops data or automatically changes the schema. The pool holds at most four connections, waits at most three seconds for one, and limits SQL statements to five seconds.

## Develop and try the chat

Start the API from `backend/`:

```sh
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, start the frontend from `frontend/`:

```sh
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173. Send “My project is called Arbiter.” Then send “What did I call my project?” The second mock reply includes the earlier user message. The mock function echoes up to 200 characters of the latest and previous user messages; it does not understand or evaluate them. The complete bounded history is retained in the run record.

Enter sends; Shift+Enter adds a newline. Sending disables duplicate submission and New chat. Failed requests retain the draft and successful conversation so selecting Send retries by user action. Each retry creates a new run; a timeout may have saved the previous run. The API accepts 1–10 nonblank user/assistant messages ending with a user message, totaling at most 12,000 Unicode characters. Invalid Unicode/null characters and unknown fields are rejected. The raw JSON body is capped at 160,000 bytes. The UI offers New chat at the limit instead of discarding earlier context.

Refresh and **New chat** clear the in-memory conversation. Both leave PostgreSQL run records intact; there is no conversation restoration/sidebar. Stop and restart the API to confirm saved runs remain accessible:

```sh
curl 'http://127.0.0.1:8000/api/runs?limit=20'
curl 'http://127.0.0.1:8000/api/runs/REPLACE_WITH_RUN_ID'
```

The list returns metadata only (limit 1–100); the detail includes messages and call output. In mock mode records have provider `mock`, model `mock-v1`, zero simulated API cost, unknown token counts, and status `unverified`. No analysis, routing, or quality success is fabricated. Failed generation attempts are saved. Missing/unreachable/unmigrated PostgreSQL returns 503 before generation. A write failure after generation returns a persistence error with the allocated run ID; a partial record can remain, so the error does not guarantee absence of data.

Vite proxies `/api` to port 8000. `GET /api/health` remains a liveness check independent of database availability. Keep this unauthenticated phase bound to localhost; deployment access protection belongs to Phase 08.

## Check and build

Create a separate test database once, from the repository root:

```sh
docker compose exec -T db psql -U arbiter -d postgres -c 'CREATE DATABASE arbiter_test;'
```

From `backend/`:

```sh
export TEST_DATABASE_URL=postgresql://arbiter:arbiter@localhost:5432/arbiter_test
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest
```

Integration tests apply migrations twice and use real PostgreSQL, including context, persisted failures, and reads through a new pool. Tests add synthetic mock records: use a test database. Without `TEST_DATABASE_URL`, PostgreSQL-dependent tests are explicitly skipped and the Phase 01 gate is **not** satisfied. An unreachable configured test database fails tests. CI supplies a PostgreSQL service and runs all tests without paid API keys.

From `frontend/`:

```sh
npm run typecheck
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

The build writes `frontend/dist/`. `npm run preview` serves the build; use the development server for the API proxy. The Playwright checks intercept API requests with explicit offline fixtures and never call paid providers. They start an isolated Vite server and exercise chat, keyboard input, error/retry, and result views at desktop and narrow widths. CI installs Chromium and runs the same browser suite.

## Stop local services

Ctrl+C stops the API/frontend. From the root:

```sh
docker compose down
```

This preserves `postgres_data`. Do not add `--volumes` if you want to retain your runs.

## Live analysis, generation, and evaluation (Phase 04)

Mock mode is still the template default. For live chat, put `JEV_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `GOOGLE_API_KEY` in the root `.env`, then set these values there:

```dotenv
CHAT_MODE=live
REQUEST_BUDGET_USD=0.25
```

The USD 0.25 ceiling accommodates the conservative generation and judge reservations; it is not expected spend. A USD 0.05 ceiling currently blocks even a short evaluated request before any paid call. Longer conversations can require more reservation and will fail safely if they do not fit.

Start the API from `backend/`:

```sh
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Credentials are `JEV_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `GOOGLE_API_KEY`. Keep them backend-only; never use `VITE_` variables. The root `.env` loads automatically on startup. A previously exported `CHAT_MODE=mock` overrides the file; run `unset CHAT_MODE` before starting live mode. To test for free, use `CHAT_MODE=mock uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000`. Live chat now routes automatically; fixed selection is confined to the provider smoke CLI.

`config/models.json` records exact documented model IDs, context/output limits, Decimal prices, source URLs, and verification dates. Enabled entries still become unavailable without their credentials. Unavailable generators are excluded; live requests never silently switch to mock. `GET /api/config` exposes mode, routed selection, and generation credential availability labels, never key values. The frontend checks it before enabling Send. No model selector is added.

The selected models are `gpt-4.1-mini-2025-04-14`, `claude-sonnet-5-5`, and `gemini-3.5-flash-lite`. All three returned `smoke OK` on 2026-10-11. Usage-based cost estimates were USD 0.0000112 (OpenAI), 0.000106 (Anthropic), and 0.0000068 (Google); persisted run IDs are in STATUS.md. Initial routing priors/ranks are explicit provisional engineering assumptions; the two development examples do not calibrate them. See [SOURCES.md](SOURCES.md) for pricing and provider-specific usage assumptions.

Before each generation call, the pipeline reserves input UTF-8 bytes plus 256 framing tokens per message, multiplied by the highest applicable input/write rate, plus the full 1,024-token output cap. It rejects insufficient budgets or context before generation, and commits a run before calling a provider. SDK retries are disabled. Async requests have both network timeouts and a cancellation deadline (`GENERATION_TIMEOUT_SECONDS`, positive and at most 60 seconds), further reduced by the remaining 90-second request allowance. Database work uses its separate short timeouts; finalization can extend beyond that generation allowance. No transaction stays open during generation. Provider-side cancellation does not guarantee that a timed-out request was unbilled.

Live chat now returns `passed`, `quality_failed`, or `unverified` using a fixed judge; a passing grade does not guarantee correctness. Mock and fixed-provider smoke replies remain `unverified`. Truncated text is returned with a warning. Usage, provider/model IDs, price snapshots, reservation, finish reason, and safe error categories are persisted. Unknown usage/cost stays null with `cost_complete=false`; known costs use Decimal and reflect usage-based estimates, not reconciled invoices. OpenAI cached input, Anthropic separate cache tokens, and Google thought tokens are accounted for. No tools or explicit cache writes are requested. Provider-side spend limits are still recommended because token reservations cannot guarantee final invoices.

## Bounded live smoke check

From `backend/`, with migrations applied and the intended provider keys exported:

```sh
uv run --frozen python -m app.smoke --budget-usd 0.05
# Or test one provider within a separate explicit ceiling:
uv run --frozen python -m app.smoke --budget-usd 0.01 --models openai
```

The CLI sends only “Reply exactly: smoke OK”, once per selected available model, sequentially. It checks the combined reservations against the explicit total ceiling before paid work; it then charges known cost or the full reservation when cost is unknown. It stops on persistence failure and blocks additional calls when the remaining ceiling is insufficient. Missing credentials are printed as `blocked`; failures are not silently retried. Outcomes include the run ID, answer, estimated/unknown cost, and any safe error category. Exit 0 means all selected models returned text; 1 means blocked/error outcomes; 2 means invalid configuration. Never execute response text.

Avoid repeated paid checks: reuse recorded successful evidence and use `--models` to check only unverified or affected providers. All three Phase 02 providers already passed; no further paid check is needed for this phase. Repeat a successful provider check only after a relevant code/config/access change or explicit user request.

All three providers must return a real response to satisfy the Phase 02 live gate. Offline SDK transport fixtures and UI fixtures do not satisfy it. Integration/browser fixtures that mimic live responses belong only in `arbiter_test`, which must never feed research history.


## Routing and Jev

Jev receives the complete bounded conversation plus three independent Choice questions (task, difficulty, reasoning). Confidence is the minimum returned confidence; missing or below 0.60 takes a labeled strong-model fallback. Missing Jev credentials, invalid answers, or errors also fall back. No generator impersonates Jev. The classifier uses a 10-second default stage cap, limited by the remaining request allowance, no retries, and an upfront USD 0.002752512 full-context reservation. Unknown classifier costs consume that reservation and keep the aggregate incomplete. Classification usage is saved before generation; a failed write stops further paid work.

The pure router first filters credentials, context, full generation reservation, priors, and remaining time. Eligible means these hard checks pass; the quality floor applies separately to the scoring pool. It reads `task:difficulty` quality priors when present, otherwise the difficulty prior. Scores normalize projected costs and latency across models meeting the 0.80 floor, then apply weights 0.70/0.30 and a stable key tie-break. If none meet the floor, highest available quality wins with a below-target label. Classifier fallback selects the configured strong model or highest available rank. No fit produces a saved error without generation.

Initial easy/medium/hard priors are OpenAI 0.85/0.80/0.65, Anthropic 0.90/0.85/0.80, Google 0.80/0.70/0.55; latency assumptions are 1500/2500/1000 ms and ranks 2/3/1. These express a provisional policy, not measured pass rates. The cheap baseline is OpenAI for the configured 256-output-token estimate; strong and fixed judge are Anthropic. Compatible history replaces assumptions once five labeled attempts exist for a model/bucket. Development evidence in `phase-03-development.json` produced Google for easy extraction and Anthropic for hard reasoning; the latter hit the output cap, so this is not a quality-success claim. Do not tune on held-out examples.

The provider smoke CLI keeps its fixed-provider behavior and does not call Jev. Phase 03 already has live evidence; use offline fixtures for further reviews. No additional paid check is needed absent a relevant change.


## Bounded evaluation and escalation

The fixed Anthropic judge sees the original bounded conversation and candidate answer as delimited JSON data. It returns native structured JSON scores (correctness, relevance, completeness: strict integers 0–4) and a reason of at most 300 characters. All scores must be at least 3 to pass. Refusal, malformed output, judge timeout, or missing judge leaves the answer unverified; a broken judge never causes another generation just to compensate. Empty/truncated answers fail deterministically without a judge call.

At most one escalation follows a valid failure, to a strictly higher configured capability rank; transient generation failures may instead try another available candidate of equal/higher rank. Every retry uses the original conversation. Two failures select the better minimum score, then total score, then later attempt. Every classifier, generation and paid evaluation attempt is committed before the next paid stage; final aggregates include all of them. Unknown costs consume reservations and remain incomplete. The total cap is five paid calls (one classifier, two generators, two judges).

Each judge response is capped at 256 tokens and its stage at 15 seconds. Candidate judge input is bounded to 8,192 UTF-8 bytes; oversized candidates remain unverified. Before generation, the pipeline reserves the worst-case candidate JSON encoding plus schema/framing and judge output, and reserves evaluation time. With an available judge, insufficient combined reservation stops generation; use the explicit USD 0.25 request ceiling shown above for the conservative default bounds. This is a ceiling, not expected spend. A missing judge can still return a best-effort unverified answer. No additional paid check is needed once recorded phase evidence passes.


## History and resumable development jobs (Phase 05)

Normal live chat loads one compatible history snapshot before any paid work. At least five known per-attempt labels are required per task/difficulty/model bucket. Quality is smoothed with five prior observations; latency and output tokens use medians. Failed generators count against quality; unknown judgments remain separately counted. History excludes mocks, held-out/baseline runs, unfinished runs and incompatible model/judge/policy/rubric versions. The `history-v1` policy intentionally starts fresh: earlier `priors-v1` data remains visible but is not used. Online labels are biased proxies, not independent benchmark grades.

Jobs run from a terminal, never from an HTTP endpoint. Apply migrations first. From `backend/`, run the 30-case synthetic development dataset without paid calls:

```sh
DATABASE_URL=postgresql://arbiter:arbiter@localhost:5432/arbiter_test \
  uv run --frozen python -m app.jobs benchmark \
  --dataset ../benchmarks/dev.jsonl --budget-usd 0.25 \
  --request-budget-usd 0.25 --mock
uv run --frozen python -m app.jobs report JOB_ID
uv run --frozen python -m app.jobs benchmark --resume JOB_ID
```

Use the same `DATABASE_URL` for all three commands. The job stores its dataset/hash, settings, exact registry and history snapshot. Resuming reads these frozen values; changing environment settings does not alter the saved experiment. Mock jobs stay mock on resume. To deliberately run development cases live, omit `--mock`, export the provider keys privately and `REQUEST_BUDGET_USD=0.25`, and choose a separate explicit total `--budget-usd`. Do not repeat existing live evidence just for testing this runner.

Each case reserves its complete request cap before any call. Completed cases are skipped on resume. A crash leaves running cases uncertain and retains their reservations, since they may have been billed. `benchmark --resume JOB_ID --retry-uncertain` explicitly allocates another reservation; old uncertain spend is not refunded. Concurrent runners for the same job are rejected. Known complete costs release unused reservation; incomplete costs retain a conservative charge. A depleted ceiling stops new cases. Reports label mock data and online judge outcomes; the three-strategy held-out research comparison comes in Phase 07.


## Demo interface (Phase 06)

The chat keeps the simple layout and adds expandable answer details: task/difficulty, first/final model, routing reason, attempts, evaluator status, elapsed time, and complete or incomplete cost. Mock answers remain explicitly unverified. A known cost subtotal is not presented as a complete total.

Use the results view for recent runs and persisted benchmark job summaries. Opening the view loads records; refresh is manual, with no background polling or paid job trigger. Empty and unavailable results have explicit states. Benchmark summaries distinguish mock data and online-judge counts from independent research grading, which remains Phase 07.

Read-only benchmark API endpoints:

```sh
curl 'http://127.0.0.1:8000/api/benchmarks?limit=20'
curl 'http://127.0.0.1:8000/api/benchmarks/REPLACE_WITH_JOB_ID'
```

The list accepts a limit from 1 to 100 and omits per-case payloads. The detail report includes persisted case states/results and preserves unknown costs. Neither endpoint exposes frozen settings or starts jobs.


## Frozen three-strategy comparison (Phase 07)

Read [benchmark-protocol.md](benchmark-protocol.md) before a live experiment. `benchmarks/dev.jsonl` and `benchmarks/test.jsonl` contain 30 synthetic cases each, with five per task type. Do not tune settings or rubrics on held-out outcomes. Keep test fixtures and research in separate PostgreSQL databases. The normal development command remains routed-only and rejects held-out cases.

Prepare a free rehearsal, then execute and export it from `backend/`:

```sh
uv run --frozen python -m app.jobs freeze --dataset ../benchmarks/test.jsonl \
  --budget-usd 4.50 --request-budget-usd 0.25 --scorer anthropic \
  --seed 20261021 --mock
uv run --frozen python -m app.jobs benchmark --resume JOB_ID
uv run --frozen python -m app.jobs export JOB_ID --output /tmp/arbiter-rehearsal
```

`freeze` persists the dataset/hash, settings, registry, history, scorer, source revision/fingerprint, targets and seeded strategy order without calling providers. Commit the implementation first, inspect the frozen inputs, then resume to execute. Changed runtime/scoring source or lockfile rejects resume. Keep `DATABASE_URL` consistent across commands. A live job deliberately omits `--mock`; its total ceiling includes both runtime and independent grading. Never run the held-out experiment with test fixtures in its history database.

Fixed-cheap and fixed-strong each generate once, without classification or online evaluation. Routed uses the complete pipeline. Grading runs separately after generation, using fixed exact/JSON checks or a blinded rubric. Runtime and grading share one persisted budget but have separate usage subtotals and completeness flags. Interrupted work retains reservations; ordinary resume skips completed work and does not retry uncertain calls. `--retry-uncertain` is an explicit additional-spend action within the same ceiling.

Exports produce `benchmark.md`, `benchmark.json`, a blinded `manual-review.json`, and a separate `manual-key.json`. Complete verdicts, notes and reviewer identity for at least ten triplets before the final export; do not consult the answer key before judging. Export preserves existing review entries and validates them against the actual answers. An explicit `--manual-reviews PATH` can supply the completed JSON. Agent review must be labeled as agent review, never human review. Unknown grades are nonpasses; unknown runtime costs make cost savings inconclusive. The UI shows compact independent per-strategy results for comparison jobs.
