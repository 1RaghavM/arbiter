# Local setup

Use Node.js 24 (`nvm use` if you use nvm), uv 0.8.0 or newer, and Python 3.12. uv can download Python when needed. Docker with Compose is optional for the foundation and needed for database work in Phase 01.

## Install

From the repository root:

```sh
cp .env.example .env
cd backend
uv sync --locked
cd ../frontend
npm ci
```

Keep `.env` local. Its database credentials are for the local demo container only. Provider keys may stay blank for Phase 00; the health endpoint does not read them. Request and benchmark budget values are placeholders for later paid-call enforcement, not active controls yet.

## Develop

Start the API from `backend/`:

```sh
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, start the frontend from `frontend/`:

```sh
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173 and select **Check connection**. A successful check shows “API connected.” Vite proxies `/api` to port 8000. The health route also responds directly at http://127.0.0.1:8000/api/health with `{"status":"ok"}`. Stop either process with Ctrl+C.

## Check and build

From `backend/`:

```sh
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest
```

From `frontend/`:

```sh
npm run typecheck
npm run lint
npm run build
```

The build writes `frontend/dist/`. `npm run preview` serves it locally for visual inspection; API proxying is configured for the development server. Browser checks currently cover the foundation page and its connection/error states; the chat browser test belongs to Phase 06. CI installs from both lockfiles and runs offline checks without provider secrets.

## Local PostgreSQL

From the repository root, with Docker running:

```sh
docker compose config --quiet
docker compose up -d --wait db
docker compose exec db pg_isready -U arbiter -d arbiter
docker compose down
```

The database listens only on localhost and stores data in the `postgres_data` volume. `down` preserves that volume. The foundation does not connect to PostgreSQL or apply migrations; persistence is Phase 01 work.

## Model configuration

`config/models.json` contains one disabled entry per generation provider. Unknown model IDs, prices, limits, and ranks are `null`; quality priors are empty. `backend/app/config.py` defines and validates this schema, and tests load the committed template. It is not wired into the health endpoint. Before enabling a model in Phase 02, verify its exact ID, pricing, limits, and access; record the date and official source. Jev uses its separate `JEV_API_KEY` setting when integrated in Phase 03.
