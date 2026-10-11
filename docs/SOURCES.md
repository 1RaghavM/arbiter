# Official references and integration verification

Prepared 2026-10-04. Recheck version-sensitive details during implementation. The internal contracts and thresholds in this package are design choices, not provider API schemas.

## Read during specification preparation

- TypeSafe homepage: https://typesafe.ai/ — links to the official documentation domain.
- TypeSafe introduction: https://docs.typesafe.ai/introduction — Jev accepts state plus typed questions; Choice, Score, and Noul return structured values. Independent questions can be combined in one call. Arbiter will map these into its own Analysis schema.
- shadcn Vite installation: https://ui.shadcn.com/docs/installation/vite — use the current supported setup for the frontend.
- FastAPI background-task guidance: https://fastapi.tiangolo.com/tutorial/background-tasks/ — reference only. Arbiter deliberately uses a separate CLI for resumable benchmark work.

Jev's exact endpoint, authentication, SDK signature, current model ID, and billing fields have not been live-tested in this handoff. Follow Quick Start and API links from docs.typesafe.ai during Phase 03. Do not obtain keys or submit prompts to similarly named third-party Jev domains based on search ranking.

## Starting points to verify during implementation

These are documentation entry points, not claims that every current API detail was inspected here:

- OpenAI: https://platform.openai.com/docs
- Anthropic: https://docs.anthropic.com/
- Google Gemini: https://ai.google.dev/gemini-api/docs
- FastAPI: https://fastapi.tiangolo.com/
- Psycopg: https://www.psycopg.org/psycopg3/docs/
- Vite: https://vite.dev/guide/

For each enabled provider record: actual docs URL, verified date, SDK version, exact model ID, generation/structured-output support, timeout/retry settings, token/usage fields, pricing URL, and a sanitized live smoke-test result. Put prices in config, not scattered source-code constants.


## Phase 00 verification — 2026-10-04

- [Vite guide](https://vite.dev/guide/) and [shadcn Vite setup](https://ui.shadcn.com/docs/installation/vite): used the official React/TypeScript template, Tailwind Vite plugin, import aliases, and shadcn CLI 4.21.1 (`--template vite --base radix --preset nova`). Kept only Button; removed unused CLI, animation, and icon dependencies after generation.
- [uv project guide](https://docs.astral.sh/uv/guides/projects/) and [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/): pinned backend packages and used TestClient for the health gate.
- Verified model documentation entry points: [OpenAI catalog](https://developers.openai.com/api/docs/models), [Claude catalog](https://platform.claude.com/docs/en/models/overview), [Gemini catalog](https://ai.google.dev/gemini-api/docs/models), and [TypeSafe introduction](https://docs.typesafe.ai/introduction). These establish official references only; no account/model access, wire contracts, or prices were verified. Provider SDK installation and exact model selection remain in Phases 02–03.
- Runtime/tool versions: Python 3.12.11, uv 0.8.0; Node 23.11.0 used locally, Node 24 selected for CI/development. Direct package versions are exact in `backend/pyproject.toml` and `frontend/package.json`; both lockfiles include transitive versions.
- Backend: FastAPI 0.142.2, Pydantic 2.13.5, Uvicorn 0.54.0, pytest 9.1.1, Ruff 0.16.10, httpx 0.28.1. The current upstream TestClient emits an httpx deprecation warning; tests pass.
- Frontend: React 19.2.8, Vite 8.3.0, TypeScript 6.0.2, Tailwind 4.3.3, Oxlint 1.81.0. PostgreSQL Compose image: 17.6.
- Credential names checked in the current shell only: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `JEV_API_KEY` are all absent. No secret values were read or logged, and no paid calls were made.

## Phase 01 verification — 2026-10-05

- [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html) and [connection pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html): direct parameterized SQL, JSONB adaptation, short connection-context transactions, explicit pool lifecycle, and finite connection/statement waits. Installed exact `psycopg[binary,pool]==3.3.6`; the lockfile pins `psycopg-pool==3.3.3`.
- PostgreSQL 17.6 was exercised locally through Compose and is now a CI service. No provider endpoint/model/pricing claim was added. Mock zero-cost records describe the absence of paid calls, not live billing measurements.

## Phase 02 verification — 2026-10-11

Documentation verification establishes API contracts and prices, not account access. No live response is claimed without a recorded smoke check.

| Provider | Exact model ID | Standard input / output USD per million | Cached input | Context |
| --- | --- | --- | --- | --- |
| OpenAI | gpt-4.1-mini-2025-04-14 | 0.40 / 1.60 | 0.10 | 1,047,576 |
| Anthropic | claude-sonnet-5-5 | 2.00 / 10.00 | 0.10 | 1,000,000 |
| Google | gemini-3.5-flash-lite | 0.30 / 2.50 | 0.03 | 1,048,576 input |

- [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini), [text generation](https://developers.openai.com/api/docs/guides/text), and [Python SDK reference](https://developers.openai.com/api/reference/python): snapshot ID, prices/context, Responses input roles, usage, incomplete status, and output text. Requests use `store=false`, no tools, `max_output_tokens=1024`, `max_retries=0`. Cached tokens are a subset of input tokens. This candidate has no separate reasoning step.
- [Sonnet 5.5 overview](https://platform.claude.com/docs/en/models/sonnet-5-5/overview), [thinking](https://platform.claude.com/docs/en/build-with-claude/thinking), [Messages API](https://platform.claude.com/docs/en/api/messages/create), and [Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python): `thinking={"type":"between_tools"}` suppresses up-front reasoning with no tools supplied; `disabled` is not supported for this model. `max_tokens=1024` bounds output. Cache reads/writes are separate from uncached input; five-minute writes cost 2.50/M. No cache writes are requested. Unexpected one-hour cache usage is unpriced by this adapter and leaves cost unknown.
- [Gemini 3.5 Flash-Lite model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite), [thinking](https://ai.google.dev/gemini-api/docs/thinking), and [usage metadata](https://ai.google.dev/api/generate-content#UsageMetadata): minimal thinking is configured, not disabled. The 1,024 output cap includes thoughts; billed output sums candidate and thought tokens. Cached input is a subset of prompt tokens. No tools/cache storage are requested; prices use the paid tier even if an account has free quota.
- [Google SDK source](https://github.com/googleapis/python-genai): `HttpRetryOptions(attempts=1)` includes the initial request and disables retries. HTTP timeout uses milliseconds. Public Gemini API is explicitly selected instead of ambient Vertex/Enterprise settings.

Pinned SDKs: OpenAI 3.28.0, Anthropic 1.13.0, google-genai 2.29.0. Installed signatures and actual SDK serialization/parsing are checked with offline async HTTP transports. The SDK async clients run under `asyncio.wait_for`, with tests proving whole-stage cancellation. Official public API endpoints are explicit. No framework wrappers, model-generated code execution, or provider retry loops were added.

Candidate price differences do not prove quality differences. All three exact configured model IDs returned real `smoke OK` responses on 2026-10-11; sanitized run IDs and usage-based costs are recorded in [STATUS.md](STATUS.md). Priors and capability ranking require development evidence in Phase 03.
