# Arbiter benchmark

The frozen target was not met; this is a valid research outcome.

Job: `b733763d-7376-434f-a2af-286cd31ab57b`. Mode: **live**.
Dataset hash: `b792786dc71ecc9386bd9452e8b5344532ca82cce8d6701ac655e4d3e98839af`.

Frozen cases: 30; matched cases: 30; manually reviewed triplets: 10.

| Strategy | Attempted | Passes | Errors | Runtime USD | Scoring USD | Median / p95 ms | Escalation | Unknown cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed-cheap | 30 | 23/30 (76.7%) | 0/30 (0.0%) | 0.0023872 | 0.050704 | 813.0 / 1839 | 0.0% | 0 |
| fixed-strong | 30 | 24/30 (80.0%) | 0/30 (0.0%) | 0.025598 | 0.050968 | 1343.5 / 3803 | 0.0% | 0 |
| routed | 30 | 25/30 (83.3%) | 0/30 (0.0%) | 0.092456314 | 0.050784 | 2387.5 / 4896 | 0.0% | 0 |

Pass rates use independent grading, with all attempted runtime cases in pass/error denominators; unknown grades are nonpasses. p95 uses nearest rank. Missing latencies are counted separately; known failed-request latencies are included.

Matched quality difference: 3.3333333333333326 pp. Runtime cost savings: -261.2% (measured). Median latency savings: -77.7%.

The frozen target is quality no more than 5 percentage points below fixed-strong, plus at least 20% lower runtime cost or 15% lower median latency. Scoring is separate research overhead. Unknown cost is not zero.

Known combined cost: USD 0.272897514. Job budget used/held: USD 0.272897514 / 3.74.

## Accounting and failures

- **fixed-cheap**: known runtime USD 0.0023872; mean runtime USD 0.00007957333333333333333333333333; known scoring USD 0.050704; unknown scoring costs 0; unknown grades 0; missing latencies 0.
  First model distribution: `{"openai": 30}`. Final model distribution: `{"openai": 30}`.
  Failed request latencies: `[{"case_id": "held-extract-eligibility", "latency_ms": 1839, "error_category": null, "grade": "fail"}, {"case_id": "held-extract-overrides", "latency_ms": 510, "error_category": null, "grade": "fail"}, {"case_id": "held-extract-stock", "latency_ms": 893, "error_category": null, "grade": "fail"}, {"case_id": "held-extract-address", "latency_ms": 811, "error_category": null, "grade": "fail"}, {"case_id": "held-reason-die", "latency_ms": 567, "error_category": null, "grade": "fail"}, {"case_id": "held-reason-seats", "latency_ms": 521, "error_category": null, "grade": "fail"}, {"case_id": "held-general-sets", "latency_ms": 1404, "error_category": null, "grade": "fail"}]`.
- **fixed-strong**: known runtime USD 0.025598; mean runtime USD 0.0008532666666666666666666666667; known scoring USD 0.050968; unknown scoring costs 0; unknown grades 0; missing latencies 0.
  First model distribution: `{"anthropic": 30}`. Final model distribution: `{"anthropic": 30}`.
  Failed request latencies: `[{"case_id": "held-extract-eligibility", "latency_ms": 1578, "error_category": null, "grade": "fail"}, {"case_id": "held-extract-overrides", "latency_ms": 1124, "error_category": null, "grade": "fail"}, {"case_id": "held-extract-address", "latency_ms": 1305, "error_category": null, "grade": "fail"}, {"case_id": "held-reason-work", "latency_ms": 1222, "error_category": null, "grade": "fail"}, {"case_id": "held-reason-schedule", "latency_ms": 931, "error_category": null, "grade": "fail"}, {"case_id": "held-reason-seats", "latency_ms": 1216, "error_category": null, "grade": "fail"}]`.
- **routed**: known runtime USD 0.092456314; mean runtime USD 0.003081877133333333333333333333; known scoring USD 0.050784; unknown scoring costs 0; unknown grades 0; missing latencies 0.
  First model distribution: `{"anthropic": 7, "haiku": 23}`. Final model distribution: `{"anthropic": 7, "haiku": 23}`.
  Failed request latencies: `[{"case_id": "held-extract-eligibility", "latency_ms": 3528, "error_category": null, "grade": "fail"}, {"case_id": "held-extract-overrides", "latency_ms": 3303, "error_category": null, "grade": "fail"}, {"case_id": "held-extract-address", "latency_ms": 2232, "error_category": null, "grade": "fail"}, {"case_id": "held-reason-schedule", "latency_ms": 2365, "error_category": null, "grade": "fail"}, {"case_id": "held-general-sets", "latency_ms": 2485, "error_category": null, "grade": "fail"}]`.

## Frozen setup and limitations

Seed: `20261021`; scorer: `anthropic`; scoring version: `independent-v1`. Full model IDs, prices, settings, dataset, history, and per-case results: benchmark.json.

Source revision: `5f70d5621962a3dcd0486ed0a40b2629e293e025`. Runtime fingerprint: `7cd80843be9398fd2c3c8a564d7e8fd36710453b3b2513c54c3c47a40578e769`. History snapshot: `0cac2cc9cb002261c4d8bde8ddeadadf5570eeb4ef29304b397d5d2ceac2ff37`.

Fixed scorer: `anthropic/claude-sonnet-5-5`. Strong baseline: `anthropic/claude-sonnet-5-5`. Exact scorer overlap with candidates: anthropic. This overlap can bias grading toward a candidate's own outputs.

Manual reviewers: Codex gpt-6.1-sol coding agent; blinded qualitative text inspection, not human review. The preserved verdicts and notes are in manual-review.json.

This synthetic 30-case held-out student benchmark is small and does not establish statistical equivalence or general model superiority. Judge grading is a biased proxy; scorer overlap is listed above, and model-family preferences remain despite hiding strategy/model labels. Manual review records the reviewer's identity separately and does not replace frozen automated grades. Provider variability and sequential timing affect results; seeded interleaving reduces order bias without removing it. Costs use frozen prices and reported usage, not invoices. Held-out results never tune routing or history. Generated code is inspected, never executed. Mock rehearsals are not research evidence.

## Recovery provenance and qualitative review

The original temporary research database was lost. User-authorized replacement
development completed all 30 cases in two jobs; original evidence remains in
development.json and its unknown USD 0.5026437 allowance is retained. The new
28-case report is replacement-development-remaining.json. Total new work is
USD 0.369899094; combined with historical allowance USD 0.872542794 of USD 5.
The private replacement database was backed up after execution.

Ten seeded triplets were reviewed by a coding agent, blinded to the strategy key,
not by an independent human. Notes flag JSON fences/explanatory prose, an omitted
qualifying record, and correct summaries/code. Cosmetic Markdown around code
was accepted by qualitative inspection; strict JSON outputs were judged by their
requested wire format. These qualitative judgments do not alter frozen automated
grades. The small selected subset does not estimate whole-benchmark error rates.
