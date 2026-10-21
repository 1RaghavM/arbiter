import json
import math
import random
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import median

STRATEGIES = ("fixed-cheap", "fixed-strong", "routed")


def was_attempted(row):
    return row["state"] != "pending" or row.get("attempts", 0) > 0


def summarize(rows, grades):
    attempted = [row for row in rows if was_attempted(row)]
    n = len(attempted)
    results = [row.get("result") or {} for row in attempted]
    passed = sum(
        result.get("status") != "error"
        and row["state"] == "done"
        and grades.get(row["case_id"], {}).get("status") == "pass"
        for row, result in zip(attempted, results)
    )
    latencies = sorted(
        result["total_latency_ms"]
        for result in results
        if result.get("total_latency_ms") is not None
    )
    known, unknown, errors, failed = Decimal(0), 0, 0, []
    for row, result in zip(attempted, results):
        known += Decimal(str(result.get("known_cost_usd", "0")))
        for prior in row.get("uncertain_attempts", []):
            known += Decimal(str(prior["known_cost_usd"]))
        if (
            not result.get("cost_complete", False)
            or result.get("total_cost_usd") is None
            or row.get("uncertain_attempts")
            or row["state"] in {"running", "uncertain"}
        ):
            unknown += 1
        runtime_error = row["state"] != "done" or result.get("status") == "error"
        errors += runtime_error
        grade = grades.get(row["case_id"], {}).get("status", "unknown")
        if runtime_error or grade != "pass":
            failed.append(
                {
                    "case_id": row["case_id"],
                    "latency_ms": result.get("total_latency_ms"),
                    "error_category": result.get("error_category"),
                    "grade": grade,
                }
            )
    return {
        "attempted_count": n,
        "pass_count": passed,
        "pass_rate": passed / n if n else None,
        "unknown_grade_count": sum(
            grades.get(row["case_id"], {}).get("status") not in {"pass", "fail"}
            for row in attempted
        ),
        "error_count": errors,
        "error_rate": errors / n if n else None,
        "total_runtime_cost_usd": str(known) if n and not unknown else None,
        "mean_runtime_cost_usd": str(known / n) if n and not unknown else None,
        "known_runtime_cost_usd": str(known),
        "unknown_cost_count": unknown,
        "median_latency_ms": median(latencies) if latencies else None,
        "p95_latency_ms": latencies[math.ceil(len(latencies) * 0.95) - 1]
        if latencies
        else None,
        "unknown_latency_count": n - len(latencies),
        "failed_case_latencies": failed,
        "escalation_rate": sum(bool(row.get("escalated")) for row in results) / n
        if n
        else None,
        "first_model_distribution": dict(
            sorted(Counter(row.get("first_model") or "none" for row in results).items())
        ),
        "final_model_distribution": dict(
            sorted(Counter(row.get("final_model") or "none" for row in results).items())
        ),
    }


def build_report(experiment, manual_reviews=None):
    dataset_ids = {case["id"] for case in experiment["dataset"]}
    keyed = {}
    for row in experiment["cases"]:
        key = (row["case_id"], row["strategy"], row["stage"])
        if key in keyed or row["strategy"] not in STRATEGIES:
            raise ValueError("Duplicate comparison row or unknown strategy.")
        if row["case_id"] not in dataset_ids or row["stage"] not in {
            "runtime",
            "grading",
        }:
            raise ValueError("Comparison row does not match the frozen dataset.")
        keyed[key] = row
    metrics, matching = {}, set(dataset_ids)
    for strategy in STRATEGIES:
        runtime = [
            row
            for (_, name, stage), row in keyed.items()
            if name == strategy and stage == "runtime"
        ]
        grading = [
            row
            for (_, name, stage), row in keyed.items()
            if name == strategy and stage == "grading"
        ]
        grades = {row["case_id"]: row.get("result") or {} for row in grading}
        metrics[strategy] = summarize(runtime, grades)
        scoring = summarize(grading, {})
        metrics[strategy].update(
            total_scoring_cost_usd=scoring["total_runtime_cost_usd"],
            known_scoring_cost_usd=scoring["known_runtime_cost_usd"],
            unknown_scoring_cost_count=scoring["unknown_cost_count"],
        )
        matching &= {row["case_id"] for row in runtime if was_attempted(row)}
    matched = {}
    for strategy in STRATEGIES:
        rows = [keyed[case_id, strategy, "runtime"] for case_id in sorted(matching)]
        grades = {
            case_id: keyed.get((case_id, strategy, "grading"), {}).get("result") or {}
            for case_id in matching
        }
        matched[strategy] = summarize(rows, grades)
    routed, strong = matched["routed"], matched["fixed-strong"]
    difference = 100 * (routed["pass_rate"] - strong["pass_rate"]) if matching else None
    cost_savings = None
    if (
        matching
        and all(matched[s]["unknown_cost_count"] == 0 for s in STRATEGIES)
        and Decimal(strong["total_runtime_cost_usd"]) > 0
    ):
        cost_savings = float(
            1
            - Decimal(routed["total_runtime_cost_usd"])
            / Decimal(strong["total_runtime_cost_usd"])
        )
    latency_savings = None
    if (
        matching
        and not routed["unknown_latency_count"]
        and not strong["unknown_latency_count"]
        and strong["median_latency_ms"] > 0
    ):
        latency_savings = 1 - routed["median_latency_ms"] / strong["median_latency_ms"]
    complete = (
        bool(dataset_ids)
        and len(matching) == len(dataset_ids)
        and all(
            keyed.get((case_id, strategy, stage), {}).get("state") in {"done", "error"}
            for case_id in dataset_ids
            for strategy in STRATEGIES
            for stage in ("runtime", "grading")
        )
    )
    template, _ = manual_template(experiment)
    reviewed = validate_reviews(manual_reviews, template)
    numerical_target = (
        difference is not None
        and difference >= -5 - 1e-10
        and (
            cost_savings is not None
            and cost_savings >= 0.20
            or latency_savings is not None
            and latency_savings >= 0.15
        )
    )
    heldout = len(dataset_ids) == 30 and all(
        case.get("split") == "heldout" for case in experiment["dataset"]
    )
    ready = (
        complete and heldout and experiment["mode"] == "live" and len(reviewed) >= 10
    )
    known_total = sum(
        Decimal(m["known_runtime_cost_usd"]) + Decimal(m["known_scoring_cost_usd"])
        for m in metrics.values()
    )
    return {
        "research_evidence": experiment["mode"] == "live" and heldout,
        "dataset_case_count": len(dataset_ids),
        "complete_comparison": complete,
        "strategies": metrics,
        "matched_case_ids": sorted(matching),
        "matched_strategies": matched,
        "quality_difference_pp": difference,
        "runtime_cost_savings": cost_savings,
        "runtime_cost_conclusion": "inconclusive"
        if cost_savings is None
        else "measured",
        "median_latency_savings": latency_savings,
        "numerical_target_met": numerical_target if complete else None,
        "manual_review_count": len(reviewed),
        "manual_review_case_ids": sorted(reviewed),
        "manual_reviewers": sorted(
            {
                row["reviewer"]
                for row in (manual_reviews or {}).get("cases", [])
                if row["case_id"] in reviewed
            }
        ),
        "known_combined_cost_usd": str(known_total),
        "target_met": numerical_target if ready else None,
        "conclusion": "Mock rehearsal; no research conclusion."
        if experiment["mode"] == "mock"
        else "Development or incomplete held-out dataset; no final conclusion."
        if not heldout
        else "Incomplete comparison; no final conclusion."
        if not complete
        else "Manual review of at least 10 matched triplets is still required."
        if len(reviewed) < 10
        else "The frozen target was met."
        if numerical_target
        else "The frozen target was not met; this is a valid research outcome.",
    }


def validate_reviews(review, template):
    if review is None:
        return set()
    if review.get("job_id") != template["job_id"]:
        raise ValueError("Manual review belongs to another experiment.")
    expected = {row["case_id"]: row for row in template["cases"]}
    reviewed = set()
    for row in review["cases"]:
        answers = row["answers"]
        if all(answer.get("verdict") is None for answer in answers):
            continue
        if (
            row["case_id"] not in expected
            or row["case_id"] in reviewed
            or {answer["label"] for answer in answers} != {"A", "B", "C"}
            or len(answers) != 3
            or not row.get("reviewer", "").strip()
            or any(
                answer.get("verdict") not in {"pass", "fail", "unknown"}
                or not answer.get("notes", "").strip()
                for answer in answers
            )
        ):
            raise ValueError("Complete each manual triplet with reviewer and notes.")
        original = expected[row["case_id"]]
        if (
            row["messages"] != original["messages"]
            or row["rubric"] != original["rubric"]
        ):
            raise ValueError("Manual review prompts differ from frozen cases.")
        if {a["label"]: a["answer"] for a in answers} != {
            a["label"]: a["answer"] for a in original["answers"]
        }:
            raise ValueError("Manual review answers differ from frozen results.")
        reviewed.add(row["case_id"])
    return reviewed


def manual_template(experiment):
    runtime = {
        (row["case_id"], row["strategy"]): row
        for row in experiment["cases"]
        if row["stage"] == "runtime"
    }
    rng = random.Random(experiment["config_snapshot"].get("seed", 0))
    candidates = [
        case
        for case in experiment["dataset"]
        if all(
            runtime.get((case["id"], strategy), {}).get("state") in {"done", "error"}
            for strategy in STRATEGIES
        )
    ]
    rng.shuffle(candidates)
    cases, keys = [], []
    for case in candidates[:10]:
        order = list(STRATEGIES)
        rng.shuffle(order)
        answers = []
        for label, strategy in zip("ABC", order):
            result = runtime[case["id"], strategy].get("result") or {}
            answers.append(
                {
                    "label": label,
                    "answer": result.get("answer"),
                    "verdict": None,
                    "notes": "",
                }
            )
            keys.append({"case_id": case["id"], "label": label, "strategy": strategy})
        cases.append(
            {
                "case_id": case["id"],
                "messages": case["messages"],
                "rubric": case["rubric"],
                "reviewer": "",
                "answers": answers,
            }
        )
    return {"job_id": experiment["job_id"], "cases": cases}, keys


def percent(value):
    return "n/a" if value is None else f"{100 * value:.1f}%"


def markdown_report(experiment, report):
    lines = [
        "# Arbiter benchmark",
        "",
        report["conclusion"],
        "",
        f"Job: `{experiment['job_id']}`. Mode: **{experiment['mode']}**.",
        f"Dataset hash: `{experiment['dataset_hash']}`.",
        "",
        f"Frozen cases: {report['dataset_case_count']}; "
        f"matched cases: {len(report['matched_case_ids'])}; "
        f"manually reviewed triplets: {report['manual_review_count']}.",
        "",
        "| Strategy | Attempted | Passes | Errors | Runtime USD | Scoring USD | "
        "Median / p95 ms | Escalation | Unknown cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for strategy, data in report["strategies"].items():
        n = data["attempted_count"]
        lines.append(
            f"| {strategy} | {n} | {data['pass_count']}/{n} "
            f"({percent(data['pass_rate'])}) | {data['error_count']}/{n} "
            f"({percent(data['error_rate'])}) "
            f"| {data['total_runtime_cost_usd'] or 'unknown'} "
            f"| {data['total_scoring_cost_usd'] or 'unknown'} "
            f"| {data['median_latency_ms']} / {data['p95_latency_ms']} "
            f"| {percent(data['escalation_rate'])} | {data['unknown_cost_count']} |"
        )
    lines += [
        "",
        "Pass rates use independent grading, with all attempted runtime "
        "cases in pass/error denominators; unknown grades are nonpasses. "
        "p95 uses nearest rank. Missing latencies are counted separately; "
        "known failed-request latencies are included.",
        "",
        f"Matched quality difference: {report['quality_difference_pp']} pp. "
        f"Runtime cost savings: {percent(report['runtime_cost_savings'])} "
        f"({report['runtime_cost_conclusion']}). Median latency savings: "
        f"{percent(report['median_latency_savings'])}.",
        "",
        "The frozen target is quality no more than 5 percentage points below "
        "fixed-strong, plus at least 20% lower runtime cost or 15% lower median "
        "latency. Scoring is separate research overhead. Unknown cost is not zero.",
        "",
        f"Known combined cost: USD {report['known_combined_cost_usd']}. "
        f"Job budget used/held: USD {experiment.get('budget_used_usd', 'unknown')} "
        f"/ {experiment.get('budget_usd', 'unknown')}.",
        "",
        "## Accounting and failures",
        "",
    ]
    for strategy, data in report["strategies"].items():
        lines += [
            f"- **{strategy}**: known runtime USD "
            f"{data['known_runtime_cost_usd']}; mean runtime USD "
            f"{data['mean_runtime_cost_usd'] or 'unknown'}; known scoring USD "
            f"{data['known_scoring_cost_usd']}; unknown scoring costs "
            f"{data['unknown_scoring_cost_count']}; unknown grades "
            f"{data['unknown_grade_count']}; missing latencies "
            f"{data['unknown_latency_count']}.",
            "  First model distribution: "
            f"`{json.dumps(data['first_model_distribution'])}`. "
            "Final model distribution: "
            f"`{json.dumps(data['final_model_distribution'])}`.",
            "  Failed request latencies: "
            f"`{json.dumps(data['failed_case_latencies'])}`.",
        ]
    config = experiment["config_snapshot"]
    registry = config.get("registry", {})
    models = {model["key"]: model for model in registry.get("models", [])}
    scorer = models.get(config.get("scorer_key"), {})
    strong = models.get(registry.get("strong_baseline_key"), {})
    scorer_id = (scorer.get("provider"), scorer.get("model_id"))
    overlaps = [
        key
        for key, model in models.items()
        if scorer and (model["provider"], model["model_id"]) == scorer_id
    ]
    lines += [
        "",
        "## Frozen setup and limitations",
        "",
        f"Seed: `{config.get('seed')}`; scorer: `{config.get('scorer_key')}`; "
        f"scoring version: `{config.get('scoring_version')}`. Full model IDs, "
        "prices, settings, dataset, history, and per-case results: benchmark.json.",
        "",
        f"Source revision: `{config.get('source_revision')}`. "
        f"Runtime fingerprint: `{config.get('runtime_fingerprint')}`. "
        f"History snapshot: `{experiment.get('history_snapshot_id')}`.",
        "",
        f"Fixed scorer: `{scorer.get('provider')}/{scorer.get('model_id')}`. "
        f"Strong baseline: `{strong.get('provider')}/{strong.get('model_id')}`. "
        f"Exact scorer overlap with candidates: {', '.join(overlaps) or 'none'}. "
        "This overlap can bias grading toward a candidate's own outputs.",
        "",
        f"Manual reviewers: {', '.join(report['manual_reviewers']) or 'pending'}. "
        "The preserved verdicts and notes are in manual-review.json.",
        "",
        "This synthetic 30-case held-out student benchmark is small and "
        "does not establish statistical equivalence or general model superiority. "
        "Judge grading is a biased proxy; scorer overlap is listed above, "
        "and model-family preferences remain despite hiding strategy/model labels. "
        "Manual review records the reviewer's identity separately and does not "
        "replace frozen automated grades. Provider variability and sequential "
        "timing affect results; seeded interleaving reduces order bias without "
        "removing it. Costs use frozen prices and reported usage, not invoices. "
        "Held-out results never tune routing or history. Generated code is "
        "inspected, never executed. Mock rehearsals are not research evidence.",
    ]
    return "\n".join(lines) + "\n"


def write_report(experiment, output_dir, manual_reviews=None):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    review_path = output / "manual-review.json"
    if manual_reviews is None and review_path.exists():
        manual_reviews = json.loads(review_path.read_text())
    report = build_report(experiment, manual_reviews)
    (output / "benchmark.json").write_text(
        json.dumps(
            experiment | {"metrics": report, "manual_review": manual_reviews},
            indent=2,
            default=str,
        )
        + "\n"
    )
    (output / "benchmark.md").write_text(markdown_report(experiment, report))
    template, key = manual_template(experiment)
    if not (output / "manual-review.json").exists():
        (output / "manual-review.json").write_text(
            json.dumps(template, indent=2) + "\n"
        )
    (output / "manual-key.json").write_text(json.dumps(key, indent=2) + "\n")
    return report
