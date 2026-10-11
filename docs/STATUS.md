# Arbiter implementation status

Updated: 2026-10-11.

- Current phase: 03 — Jev and routing, in progress.
- Repository/default branch: [1RaghavM/arbiter](https://github.com/1RaghavM/arbiter), `master`.
- Phase 01 [PR #2](https://github.com/1RaghavM/arbiter/pull/2) merged on 2026-10-11 after explicit user authorization. Its checks passed.
- Phase 02 PR #3 merged by the review subagent at `2793f1b` after all gates passed.
- Phase branch: `phase/03-jev-routing`, from updated `origin/master` at `2793f1b`.
- Authorization: user gives standing authorization for subagent review/merge of passing phase PRs and continuation to the next phase.
- Previous PR: [#3](https://github.com/1RaghavM/arbiter/pull/3), merged. Phase 03 PR not yet opened.
- Next action: implement verified Jev analysis, deterministic routing, persistence/UI integration and focused offline tests; then minimal bounded live development checks. No further Phase 02 paid checks.
- Testing preference: keep paid checks minimal; reuse successful evidence, use offline fakes for failure paths, and rerun only affected checks after changes. Recorded in AGENTS.md and quality.md.

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
| `git diff --check`, relative documentation links, staged files/attribution | PASS: named files reviewed; sole configured user author/committer, no assistant trailers or private artifacts |
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

Each commit uses `1RaghavM` as sole author/committer, with no assistant co-author trailers, and was immediately pushed before making another commit.

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
| 03 | in_progress | phase/03-jev-routing | — | Official Jev contract research underway |
| 04 | pending | — | — | — |
| 05 | pending | — | — | — |
| 06 | pending | — | — | — |
| 07 | pending | — | — | — |
| 08 | pending | — | — | — |

Allowed states: pending, in_progress, blocked, ready_for_review, merged. A phase becomes a dependency only after its PR is merged.
