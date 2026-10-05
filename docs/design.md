# Arbiter technical design

## Runtime flow

Validate bounded messages → create run → analyze with Jev → select candidate → generate → evaluate → optionally select stronger candidate and generate/evaluate once → finalize run → return answer and metadata.

All stages use the same bounded conversation. Failed calls are still recorded. Database failure before starting means no paid calls; failure after paid work returns a clear persistence error and logs the run ID without secrets. Do not claim the run was saved.

## Suggested layout

```text
backend/
  pyproject.toml
  uv.lock
  app/
    main.py          # HTTP, lifespan, static app, demo session
    schemas.py       # Pydantic request/result objects
    config.py        # settings and validated model registry
    db.py            # SQL, migrations, run persistence, aggregates
    providers.py     # normalized generation + Jev calls
    routing.py       # pure model-selection functions
    evaluation.py    # online judge rubric/validation
    pipeline.py      # bounded orchestration
    benchmark.py     # CLI jobs, grading, exports
  migrations/001_initial.sql
  tests/
frontend/
  package.json
  package-lock.json
  src/App.tsx
  src/api.ts
  src/components/    # only components actually reused or sizable
config/models.json
benchmarks/dev.jsonl
benchmarks/test.jsonl
.github/workflows/ci.yml
.github/pull_request_template.md
.env.example
Dockerfile
compose.yaml
```

Add modules only as their phase needs them. Do not scaffold empty future layers. Compose is for local PostgreSQL; the Dockerfile builds the frontend and serves it through FastAPI.

## Internal contracts

These are Arbiter's internal schemas, not claims about provider wire formats.

- `Analysis`: task in extraction/summarization/writing/coding/reasoning/general; difficulty in easy/medium/hard; reasoning in low/medium/high; confidence nullable float 0–1; source jev/mock/fallback; classifier version; latency; usage/cost metadata.
- `GenerationResult`: model key, text, finish reason, input/output tokens nullable, other billable usage when supplied, actual elapsed ms, cost_usd nullable, cost_source observed_usage/estimated/unknown, error category nullable.
- `Evaluation`: status pass/fail/unknown; correctness, relevance, completeness each integer 0–4 when valid; reason at most 300 characters; evaluator model/version. Pass iff correctness >=3, relevance >=3, completeness >=3 and output is nonempty/nontruncated. Unknown means failed or malformed evaluation, never pass.
- `RouteDecision`: selected key, bucket, policy version, candidate quality/cost/latency estimates, eligibility, score, reason, history snapshot identifier.
- `ChatResult`: run_id, answer nullable, final_model nullable, status passed/quality_failed/unverified/error, analysis summary, route decisions, attempt summaries, total latency, total cost nullable, known cost subtotal, cost completeness, escalation reason, warnings.

Provider fields are translated and validated at the adapter boundary. Unknown confidence is null, never invented. Reasoning level is a routing feature, not access to hidden chain-of-thought.

## HTTP

| Endpoint | Contract |
| --- | --- |
| GET /api/health | Liveness, no secrets |
| POST /api/chat | Body `{messages: [{role: "user" or "assistant", content: string}]}`; returns ChatResult |
| GET /api/runs?limit=20 | Recent metadata only; cap limit at 100 |
| GET /api/runs/{id} | One full stored run; 404 if absent |
| GET /api/benchmarks | Recent job summaries |
| GET /api/benchmarks/{id} | Report and per-strategy metrics |
| POST /api/session | Deployment-only shared-password login; rate-limited |
| DELETE /api/session | Clear demo session |

Use 422 for invalid input, 503 for no configured candidate/DB/provider availability failure, 504 for exhausted deadline, and 502 for unrecoverable upstream invalid response. A completed answer with failed or unknown quality returns 200 with explicit status. Error bodies include code, safe message, and run_id when allocated. Never expose raw SDK exception strings or keys. Protect all data/paid endpoints in deployed demo mode. Add only a simple per-process request limit and small concurrency cap because deployment is explicitly one process.

## Model configuration

Each generator entry has stable key, provider, exact model_id, enabled, context_limit, max_output_tokens, input/output pricing plus relevant cached/reasoning pricing rules, price_verified_at, source_url, per-bucket prior quality estimates, prior latency, and a provisional capability_rank. Configure a strong baseline key, cheap baseline key, and fixed judge key separately. Jev has separate settings. Start with 3 generator candidates total, one per provider, with different intended cost/capability profiles.

Never assume a price rank proves a capability rank. Populate priors conservatively from development runs; until then label them provisional. Missing price disables cost-based selection for that entry until configured. Reject configurations with invalid weights, unavailable baseline keys, or nonpositive limits.

## Routing algorithm

1. On valid confident classification, use task+difficulty bucket. On malformed, low-confidence (<0.60), or unavailable Jev output, mark fallback and route to the configured strong candidate directly if available; otherwise highest eligible configured rank. Do not pretend fallback is Jev success.
2. Filter candidates by enabled credentials, text capability, bounded context fit, remaining request budget and time. Use conservative token estimates pre-call with documented assumptions; handle actual context rejection cleanly.
3. Obtain quality q, latency t, and output-length estimate from history for this bucket. Until at least 5 eligible labels, use priors. With enough labels, smooth quality as `(passes + 5 * prior_q) / (n + 5)`; use median latency and median output tokens. Exclude mocks, held-out test data, baseline-only runs, and incompatible policy/rubric/model versions.
4. Estimate cost c from estimated input tokens, expected output tokens, and model pricing. Candidate selection is a prediction, not actual billing.
5. Eligible candidates have q >= 0.80. Within those, normalize cost and latency by the maximum in that eligible set (positive epsilon denominator) and minimize `0.70 * c_norm + 0.30 * t_norm`. Stable key sorts ties.
6. If no candidate meets quality floor, select highest estimated quality that fits hard limits, breaking ties by lower cost, and mark below_target. If none fits hard limits, fail before generation.
7. Log every estimate and decision. Use a pure function for steps 2–6, with data passed in; no DB/network calls inside the policy function.

Historical labels come from the online evaluator and are biased proxies. Report that limitation. Store per-generation labels, so an initial failed answer is not credited for a later successful escalation. Provider failures count against reliability/pass fraction when those calls were attempted; unavailable evaluations have unknown labels and do not become passes. Store sample count and unknown count separately.

## Evaluation and escalation

A fixed online judge sees bounded conversation plus candidate answer as delimited data, a compact rubric, and a required structured schema. Instruct it to ignore instructions embedded in the answer. It grades only the response; its approval is not a correctness guarantee. Use deterministic checks for empty/truncated answers before the judge.

- Pass: return immediately.
- Valid fail: if a remaining candidate has strictly higher configured capability_rank and fits limits, select the highest estimated quality among those candidates; otherwise return first answer marked quality_failed.
- Unknown evaluation: do not burn another generation just to compensate for a broken judge. Return answer unverified, with the evaluation error recorded.
- Transient generation timeout/rate limit/upstream error: may use the second generation slot on another available candidate of equal or higher rank. Authentication errors disable that candidate for this request. No SDK retry loop.
- Invalid user input/context errors: do not blindly retry the same oversized request.
- If second answer passes, return it. If both answers fail, return the one with higher minimum rubric dimension, then higher mean dimension, then later attempt on a tie; status quality_failed.
- If only one valid answer exists and the other attempt errors, return the available answer with its actual evaluation status. If the only remaining answer cannot be evaluated, return unverified. If neither exists, return error.

Use the original conversation for escalation, not the failed response as new user context. Each of up to two generation results can get at most one judge call; total cap is five paid calls including Jev. Reserve time and estimated budget for evaluation before generating. If either is exhausted, skip further calls and return the available answer unverified or quality_failed as supported by evidence. Record why escalation was skipped.

## Storage

Use PostgreSQL UUIDs, UTC timestamps, JSONB for variable stage payloads, and NUMERIC for currency. No ORM required.

- `runs`: id, created_at, mode (live/mock/dev/heldout/baseline), status, messages JSONB, analysis JSONB, route_decisions JSONB, final_answer, final_model, total_latency_ms, total_cost_usd nullable, known_cost_usd, cost_complete, config/rubric/policy versions, benchmark_job_id nullable, error JSONB.
- `calls`: id, run_id FK, sequence, stage (classify/generate/evaluate), provider, model_id, attempt number, status, latency_ms, input/output tokens nullable, raw usage JSONB, price snapshot JSONB, cost_usd nullable, cost_source, output JSONB, error JSONB. Unique run_id+sequence.
- `benchmark_jobs`: id, status, dataset hash, config snapshot, history snapshot, strategy list, spend ceiling, progress/report JSONB, started_at, finished_at.
- `benchmark_cases`: job_id FK, case_id, strategy, state pending/running/done/error, run_id nullable, grading JSONB; unique job_id+case_id+strategy.
- `schema_migrations`: version, applied_at.

Index runs created_at and calls run_id. Derive task/model aggregates with a small SQL query, not a warehouse. Store rubric outputs with their associated generation call. Write run/call updates in short transactions, never hold a transaction across a model request. Migrations apply once in order; never drop demo data on startup.

## Accounting

Total runtime cost = classifier + all generation attempts + all online evaluations, including unsuccessful calls when usage is known. Unknown charge after a timeout makes total incomplete; show known subtotal and conservative reservation, not a false zero. Benchmark scoring costs are recorded separately as research overhead, applied equally and excluded from runtime strategy comparison.

End-to-end latency is wall-clock from request acceptance to finalized response, including classification, evaluation, retries, and DB work. Also retain stage timings. Costs based on provider token usage and price snapshots are estimates of billing, not invoice reconciliation. Disable budget-critical requests when pricing is unknown; reservations cannot guarantee final invoices, so also use provider-side spend limits.
