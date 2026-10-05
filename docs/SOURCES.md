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
