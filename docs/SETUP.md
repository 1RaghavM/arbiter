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

Keep `.env` local. Its database credentials are for the local demo container only. Provider keys may stay blank: Phase 01 makes no external model calls. Request and benchmark budget values are placeholders for later paid-call enforcement.

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

The list returns metadata only (limit 1–100); the detail includes messages and call output. All records are labeled mock, with provider `mock`, model `mock-v1`, zero simulated API cost, unknown token counts, and status `unverified`. No analysis, routing, or quality success is fabricated. Failed generation attempts are saved. Missing/unreachable/unmigrated PostgreSQL returns 503 before generation. A write failure after generation returns a persistence error with the allocated run ID; a partial record can remain, so the error does not guarantee absence of data.

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

The build writes `frontend/dist/`. `npm run preview` serves the build; use the development server for the API proxy. Phase 01 browser checks cover two turns, keyboard input, error/retry, clearing chat, limits, and desktop/mobile layouts. A committed Playwright regression flow remains Phase 06 scope.

## Stop local services

Ctrl+C stops the API/frontend. From the root:

```sh
docker compose down
```

This preserves `postgres_data`. Do not add `--volumes` if you want to retain your runs.

## Model configuration

`config/models.json` still has three disabled provider entries with null model IDs/prices/limits/ranks and empty priors. It is not wired into mock generation. Verify model IDs, pricing, limits, and access before enabling providers in Phase 02; Jev remains Phase 03 work.
