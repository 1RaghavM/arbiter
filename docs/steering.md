# Arbiter steering

## Chosen stack

| Area | Decision |
| --- | --- |
| Frontend | React + TypeScript + Vite, Tailwind CSS, shadcn/ui, native fetch |
| UI state | React useState; no global state library or data-fetch framework |
| Backend | Python 3.12, FastAPI, Pydantic, Uvicorn |
| Storage | PostgreSQL; psycopg with parameterized SQL and a small connection pool |
| Schema changes | Numbered SQL files plus a tiny migration command and schema_migrations table |
| Providers | Official Python SDKs where straightforward; httpx for documented APIs when simpler |
| Testing | pytest, Ruff, TypeScript checks, frontend lint/build, one focused Playwright flow |
| Jobs | Python CLI; sequential and resumable; optional host scheduler later |
| Deployment | One container serves built frontend and API; managed PostgreSQL |
| Repository | One small monorepo; uv Python lockfile and npm package-lock |

Exact versions and provider model IDs are recorded during Phase 00/02/03 against current documentation. Do not hardcode unverified SDK signatures from this specification.

## Code budget

Write the smallest clear implementation that satisfies the student-project requirements. There is no minimum line count: fewer lines are welcome when the code remains readable. Treat 1,500–2,500 hand-written runtime LOC as a rough planning estimate, never a target to fill. Count generated shadcn files, tests, migrations, and documentation separately. Keep necessary validation, spend limits, and tests; avoid code golf or compressed one-liners.

Use a clean junior-developer style: descriptive names, small focused functions, explicit steps, and familiar loops and conditionals. Prefer code a junior developer can explain and maintain. Avoid clever language tricks, speculative flexibility, and production-level infrastructure. Comments and docstrings are only for non-obvious reasons, constraints, or workarounds; do not restate the code.

Start with a flat app package and a few React components. Split a file when it has distinct responsibilities that are hard to follow. Avoid one-line forwarding modules, generic service/repository classes, dependency-injection containers, and plugin registries.

## MVP decisions

- Non-streaming chat: evaluate before returning the final response. One HTTP request handles the complete bounded pipeline.
- Stateless conversation API: the browser sends bounded history. PostgreSQL stores request runs, not a separate conversation product.
- Simple policy: filter by quality eligibility, then minimize normalized cost/latency. No learned router training pipeline.
- Jev only classifies. Start with a separately configured cloud generator as the online judge; this judge is fixed across candidate generators and never chosen by the router.
- Online evaluation is a heuristic. Held-out benchmark grading is separate from the online pass signal.
- Historical adaptation reads aggregate statistics; no retraining service. Freeze history snapshots for final experiments.
- No web endpoint that starts an expensive benchmark. Run the CLI from a controlled environment.
- Final deployment uses one API process. A small shared demo password/session protects provider spend; no user-account system. Do not bake the password into browser assets. Store only a session indicator in a signed HttpOnly cookie.
- Serve frontend and API on the same origin in deployment. Local development uses a Vite proxy. SPA fallback must not swallow /api errors.

## UI direction

Neutral colors, readable type, centered conversation, simple composer. Add only needed shadcn components: Button, Textarea, Card, Badge, and a collapsible details element if useful. Display plain text or safely rendered Markdown without raw HTML. Use semantic controls, keyboard submission, visible focus, and clear error states.

No model selector in normal chat. Show a short policy-generated explanation such as “Eligible quality estimate; lowest weighted cost/latency.” Do not display invented chain-of-thought.

## Defaults to record and tune only on development data

Quality floor 0.80; history threshold 5 labeled attempts per bucket; confidence threshold 0.60; cost weight 0.70 and latency weight 0.30. These are provisional engineering settings, not validated facts.

Use configurable stage timeouts with a 90-second request deadline. Configure a conservative request spend limit and a separate benchmark spend ceiling before live calls. No default unlimited billing. If a host's request timeout is shorter, reduce stage limits or choose appropriate hosting; do not add an asynchronous job architecture just to preserve a long request.

Any larger architectural change needs a concrete failing requirement and a short rationale in STATUS. Ordinary implementation decisions within these constraints do not need repeated permission requests.
