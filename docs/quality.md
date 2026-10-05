# Arbiter quality gates

## What quality means here

Readable small code, correct routing/accounting, explicit failure states, a usable demo, and an honest comparison. No coverage percentage target, enterprise security audit, or load-testing project.

## Every phase

- Only active-phase scope; no unrelated refactor.
- Run relevant offline tests, backend lint, frontend type/lint/build checks once those components exist.
- No credentials in tracked files or frontend bundle; review staged diff.
- Document exact commands and results in STATUS and PR; skipped/live-blocked checks are not passes.
- Incremental commits and one phase PR. UI changes include a quick browser check at desktop and narrow/mobile width.

## Test focus

| Area | Meaningful checks |
| --- | --- |
| API | Blank/oversized/invalid-role requests; bounded history; upstream and DB failures |
| Provider adapters | Correct role translation, usage mapping, finish reason, malformed response, timeout/auth/rate limit |
| Jev | Valid classification; unknown enum; confidence missing/out of range; low confidence; timeout fallback |
| Router | Hand-calculated scores; stable tie; insufficient history; history changes choice; context/budget exclusion; no eligible model |
| Pipeline | Pass first; fail then pass; fail twice; unknown judge; no stronger model; first generation failure; call caps; exhausted deadline/budget |
| Costs | Classifier+both generation+both evaluation included; unknown usage stays unknown; snapshots retained |
| Database | Real PostgreSQL round trip, failed attempt persistence, migration twice safe, per-attempt history correctness |
| Jobs | Resume completed cases without calling again; pending/running semantics; spend ceiling; held-out exclusion |
| UI | Send and reply; loading prevents duplicate submit; route details; error/retry; new chat; keyboard usability |
| Deployment | Login/session, no public run data, no client secrets, same-origin API, persistence after restart |

Do not test React state setters or generated shadcn internals. Do not mock PostgreSQL while claiming PostgreSQL integration coverage. CI uses fakes for external providers and a PostgreSQL service for relevant integration tests; no paid API keys in CI.

## Benchmark protocol

1. Commit 60 small curated text cases: 30 development and 30 held-out, each with 5 cases for each of the six task types. Spread difficulty within each group. Include expected answers/checks or explicit grading rubrics. Record IDs and provenance; use synthetic nonprivate content. This is a student benchmark, not broad evidence of model superiority.
2. Use only development data to choose candidates, tune thresholds, update priors, and debug rubrics. Freeze test cases, config, history snapshot, and grading rules before final evaluation. Never feed held-out outcomes back into routing history.
3. Run the same held-out prompts and bounded context through fixed-cheap, fixed-strong, and routed strategies. Baselines generate once, without online classification/evaluation; routed includes its entire online pipeline. Score final answers with the same independent offline checks/rubric across all three.
4. For objective cases, use exact/normalized text or JSON checks. For writing and open-ended tasks, use a fixed scoring judge blinded to strategy/model labels, plus manually review at least 10 matched prompt triplets. Prefer a judge different from candidate generators when practical; record overlap/bias if unavailable. Never execute generated code. Coding cases use inspection/rubric grading unless a separate sandbox is explicitly added later.
5. Interleave strategy order with a fixed seed. Keep provider parameters/output limits equivalent where supported; record unsupported options. Run sequentially to avoid concurrency distortion. At least one full pass is required; extra repeats only if spend permits.
6. Report number of cases, independent pass rate, error rate, total/mean runtime cost, scoring cost separately, median/p95 end-to-end latency, escalation rate, routing distribution, and unknown-cost count. Include all attempted cases in success denominators. List failed-case latency and do not silently delete failures from summaries.
7. Compute quality difference in percentage points; cost savings `1 - routed_total / strong_total`; median latency savings `1 - routed_median / strong_median`. Compare matched case sets. If any cost is incomplete, flag the cost conclusion inconclusive rather than treating unknowns as zero.
8. State whether the requirements.md target was met, and discuss sample size, judge bias, provider variability, and sequential timing. Do not tune on the held-out results to retroactively meet targets.

The online evaluator determines escalation; it does not determine the headline benchmark quality metric by itself.

## Final acceptance

All requirements R01–R14 have evidence. Live integrations and PostgreSQL actually work. At least two generator candidates are selected in a documented demo/development set. Demonstrate one escalation live if reproducible, or show a clearly labeled offline controlled failure test alongside live normal routing. Do not fabricate a live failure. Deployment works from another machine. The final report may honestly conclude that routing overhead outweighs savings.
