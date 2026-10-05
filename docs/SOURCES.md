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
