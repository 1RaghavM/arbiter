# Local setup

Use Node.js 24 (`nvm use` if available), uv 0.8.0 or newer, Python 3.12, and Docker with Compose. uv can download Python when needed.

## Install

From the repository root:

```sh
cp .env.example .env
cd backend
uv sync --locked
cd ../frontend
npm ci
```

Keep `.env` local. Its database credentials are for the local demo container only. Provider keys may stay blank in default mock mode. Live mode requires explicit provider credentials and a positive request budget; benchmark budgets remain Phase 05 work.

## Start PostgreSQL and migrate

From the repository root, with Docker running:

```sh
docker compose up -d --wait db
export DATABASE_URL=postgresql://arbiter:arbiter@localhost:5432/arbiter
cd backend
uv run --frozen python -m app.db
```

The application reads environment variables; it does not automatically load `.env`. Export `DATABASE_URL` in each terminal that runs migrations or the API. The command above uses the bundled local demo credentials. For another database, set its URL privately.

Migrations are numbered SQL files, applied in filename order in a transaction and tracked in `schema_migrations`. Running the migration command twice is safe. Run it before starting the API; startup never drops data or automatically changes the schema. The pool holds at most four connections, waits at most three seconds for one, and limits SQL statements to five seconds.

## Develop and try the chat

Start the API from `backend/`, in the terminal with `DATABASE_URL` exported:

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
```

The build writes `frontend/dist/`. `npm run preview` serves the build; use the development server for the API proxy. Browser checks cover two turns, keyboard input, error/retry, clearing chat, limits, and desktop/mobile layouts. A committed Playwright regression flow remains Phase 06 scope.

## Stop local services

Ctrl+C stops the API/frontend. From the root:

```sh
docker compose down
```

This preserves `postgres_data`. Do not add `--volumes` if you want to retain your runs.

## Live analysis and generation (Phase 03)

Mock mode is still the default. For live chat, configure Jev and the available generation keys privately in the backend environment, then start the API with:

```sh
export CHAT_MODE=live
export CLASSIFICATION_TIMEOUT_SECONDS=10
export REQUEST_BUDGET_USD=0.05
export GENERATION_TIMEOUT_SECONDS=30
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Credentials are `JEV_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `GOOGLE_API_KEY`. Keep them backend-only; never use `VITE_` variables. The app does not load `.env` automatically; export values in the process that starts it. Restart with `CHAT_MODE=mock` for free deterministic replies. Live chat now routes automatically; fixed selection is confined to the provider smoke CLI.

`config/models.json` records exact documented model IDs, context/output limits, Decimal prices, source URLs, and verification dates. Enabled entries still become unavailable without their credentials. Unavailable generators are excluded; live requests never silently switch to mock. `GET /api/config` exposes mode, routed selection, and generation credential availability labels, never key values. The frontend checks it before enabling Send. No model selector is added.

The selected models are `gpt-4.1-mini-2025-04-14`, `claude-sonnet-5-5`, and `gemini-3.5-flash-lite`. All three returned `smoke OK` on 2026-10-11. Usage-based cost estimates were USD 0.0000112 (OpenAI), 0.000106 (Anthropic), and 0.0000068 (Google); persisted run IDs are in STATUS.md. Initial routing priors/ranks are explicit provisional engineering assumptions; the two development examples do not calibrate them. See [SOURCES.md](SOURCES.md) for pricing and provider-specific usage assumptions.

Before each generation call, the pipeline reserves input UTF-8 bytes plus 256 framing tokens per message, multiplied by the highest applicable input/write rate, plus the full 1,024-token output cap. It rejects insufficient budgets or context before generation, and commits a run before calling a provider. SDK retries are disabled. Async requests have both network timeouts and a cancellation deadline (`GENERATION_TIMEOUT_SECONDS`, positive and at most 60 seconds), further reduced by the remaining 90-second request allowance. Database work uses its separate short timeouts; finalization can extend beyond that generation allowance. No transaction stays open during generation. Provider-side cancellation does not guarantee that a timed-out request was unbilled.

Every generation remains `unverified`: live chat runs Jev and the router, but no quality evaluator yet. Truncated text is returned with a warning. Usage, provider/model IDs, price snapshots, reservation, finish reason, and safe error categories are persisted. Unknown usage/cost stays null with `cost_complete=false`; known costs use Decimal and reflect usage-based estimates, not reconciled invoices. OpenAI cached input, Anthropic separate cache tokens, and Google thought tokens are accounted for. No tools or explicit cache writes are requested. Provider-side spend limits are still recommended because token reservations cannot guarantee final invoices.

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

Initial easy/medium/hard priors are OpenAI 0.85/0.80/0.65, Anthropic 0.90/0.85/0.80, Google 0.80/0.70/0.55; latency assumptions are 1500/2500/1000 ms and ranks 2/3/1. These express a provisional policy, not measured pass rates. The cheap baseline is OpenAI for the configured 256-output-token estimate; strong and future judge are Anthropic. History will replace assumptions in Phase 05. Development evidence in `phase-03-development.json` produced Google for easy extraction and Anthropic for hard reasoning; the latter hit the output cap, so this is not a quality-success claim. Do not tune on held-out examples.

The provider smoke CLI keeps its fixed-provider behavior and does not call Jev. Phase 03 already has live evidence; use offline fixtures for further reviews. No additional paid check is needed absent a relevant change.
