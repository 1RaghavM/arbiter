# Phase 07 experiment protocol

Prepared 2026-10-21, before paid development or held-out evaluation. The user approved USD 5 total for the experiment, including independent scoring. A negative result is valid.

## Data and frozen choices

Use 30 synthetic development cases and 30 separate held-out cases. Each split has five cases in each task category: extraction, summarization, writing, coding, reasoning, and general. Cases carry difficulty, provenance, expected answer/check when objective, and an explicit rubric otherwise. Generated code is inspected as text and is never executed.

The initial development job used three generator IDs. On 2026-10-22, before any held-out freeze or calls, the user requested Haiku 5.5 as an additional easy-task candidate. Its verified prices and provisional priors are recorded in SOURCES.md and design.md. Existing frozen jobs retain their original registry; new jobs capture the four-model registry. Preserve the original two completed development cases and disclose this configuration change when combining development evidence. OpenAI remains the fixed-cheap baseline and Sonnet the fixed-strong baseline and judge; the baseline name identifies the chosen comparison, not the cheapest current candidate. Routing weights, confidence threshold, online rubric and generation limits are unchanged. No policy or rubric changes may be based on held-out outputs. The development set is available for debugging before the held-out freeze.

Run the development dataset once through the routed pipeline, capped at USD 0.50. Use a dedicated research database, separate from all test fixtures. Freeze the resulting compatible history snapshot before any held-out request. Sparse buckets continue to use documented priors; no synthetic test outcomes enter research history.

Freeze the held-out dataset/hash, registry/prices, settings, history snapshot, scorer version/prompt, strategy order and runtime versions in the comparison job before execution. Record the source commit in the exported evidence. Use seed `20261021` and one sequential pass through all three strategies: fixed-cheap, fixed-strong, and routed. Interleave strategy order per case. Baselines generate once with no online classifier/judge; routed includes its full bounded pipeline. Supported output limits/provider options are the same for a model across strategies; unsupported parameters are documented in SOURCES.md.

## Spending and interruptions

The held-out comparison has a USD 4.50 combined runtime/scoring ceiling, leaving the development ceiling within the approved USD 5 total. Reserve before each operation. Unknown or interrupted costs retain their reservation; completed cases must not replay on resume. No automatic retry of uncertain paid work, no extra full pass, and no post-hoc tuning. Any separately authorized retries must fit the remaining approved total.

Use the existing USD 0.25 request ceiling for runtime requests. Independent grading uses its own conservative reservation and finite timeout, charged to the same comparison ceiling but reported separately. Provider usage and frozen prices produce billing estimates, not invoice guarantees.

## Independent quality and reporting

Objective tasks use fixed normalized-text or JSON comparisons. Other tasks use a fixed blinded rubric scorer: it sees the bounded conversation, case rubric/reference and final answer without strategy/model labels. Its prompt/version differ from the online evaluator. The scorer uses the existing Anthropic structured adapter; it overlaps the strong generator and online judge, so independence is procedural rather than model identity and bias must be reported. Unknown grades do not count as passes. Provider errors, truncation and missing answers remain in the denominators.

Report attempted cases, independently graded pass rate, error rate, total/mean runtime cost, separate scoring cost, median/p95 end-to-end latency, failed-case latency, escalation rate, routing distribution and unknown-cost counts. Compute comparisons only on matched case sets. Any incomplete runtime costs make the savings conclusion inconclusive. Keep full per-case machine-readable outcomes.

The frozen target is routed pass rate no more than five percentage points below fixed-strong, plus either at least 20% lower total runtime cost or at least 15% lower median latency. Record failure to meet it without cherry-picking. This small benchmark does not establish statistical equivalence or broad model superiority.

Review at least ten matched prompt triplets qualitatively using a deterministic blinded export. Record reviewer identity/type and judgments transparently; a coding-agent inspection must not be presented as an independent human review. Preserve the review and comparison artifacts. Discuss sample size, rubric bias, repeated model identity, provider variability, token-limit effects and sequential timing.

## Pre-held-out interruption, 2026-10-21

The USD 0.50 development pass stopped after two cases because Google failures supplied no usage and retained both USD 0.25 request reservations. An affected-provider diagnostic used the existing smoke pipeline with a USD 0.01 ceiling and retained USD 0.0026437; it returned HTTP 402. This extra diagnostic is included in the user's USD 5 total. No held-out job has been frozen or run. Known charges are incomplete; do not release unknown reservations or repeat finished development cases. Restore Google billing before further generation. At most USD 4.49 is available for subsequent work under the original aggregate ceiling; record the revised split between unfinished development, affected-provider verification, and held-out grading before execution. Do not silently retain the original USD 4.50 held-out allocation after this diagnostic. No thresholds, models or rubrics changed in response to these outcomes.

The blocked development job cannot advance with `--resume` because its frozen ceiling is fully retained. Preserve the original job and create a separately capped continuation job containing exactly its 28 pending case IDs after billing is restored and the budget allocation is recorded. Both jobs and the diagnostic count toward the same USD 5 authorization. Do not silently alter frozen ceilings or replay the two completed cases.
