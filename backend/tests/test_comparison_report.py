import copy
import json
from decimal import Decimal

import pytest

from app.comparison_report import (
    STRATEGIES,
    build_report,
    manual_template,
    write_report,
)


def experiment(n=3, mode="live"):
    data = {
        "job_id": "report-fixture",
        "mode": mode,
        "status": "completed",
        "dataset_hash": "fixture-hash",
        "budget_usd": "5",
        "budget_used_usd": "0.1",
        "history_snapshot_id": "frozen-history",
        "config_snapshot": {
            "seed": 20261021,
            "scorer_key": "strong",
            "source_revision": "frozen-source",
            "runtime_fingerprint": "frozen-code",
            "registry": {
                "strong_baseline_key": "strong",
                "models": [
                    {"key": "strong", "provider": "fixture", "model_id": "fixed-model"},
                ],
            },
        },
        "dataset": [
            {
                "id": f"case-{i}",
                "split": "heldout",
                "rubric": "Return blue.",
                "messages": [{"role": "user", "content": "Return blue."}],
            }
            for i in range(n)
        ],
        "cases": [],
    }
    for i in range(n):
        for strategy in STRATEGIES:
            cost = "0.02" if strategy == "fixed-strong" else "0.01"
            data["cases"].append(
                {
                    "case_id": f"case-{i}",
                    "strategy": strategy,
                    "stage": "runtime",
                    "state": "done",
                    "attempts": 1,
                    "uncertain_attempts": [],
                    "result": {
                        "status": "passed",
                        "answer": "blue",
                        "total_latency_ms": 100 + i,
                        "known_cost_usd": cost,
                        "total_cost_usd": cost,
                        "cost_complete": True,
                        "first_model": strategy,
                        "final_model": strategy,
                        "escalated": False,
                    },
                }
            )
            data["cases"].append(
                {
                    "case_id": f"case-{i}",
                    "strategy": strategy,
                    "stage": "grading",
                    "state": "done",
                    "attempts": 1,
                    "uncertain_attempts": [],
                    "result": {
                        "status": "pass",
                        "known_cost_usd": "0.001",
                        "total_cost_usd": "0.001",
                        "cost_complete": True,
                    },
                }
            )
    return data


def row(data, case_id, strategy="routed", stage="runtime"):
    return next(
        r
        for r in data["cases"]
        if r["case_id"] == case_id and r["strategy"] == strategy and r["stage"] == stage
    )


def completed_reviews(data):
    reviews, _ = manual_template(data)
    for case in reviews["cases"]:
        case["reviewer"] = "coding-agent (offline fixture)"
        for answer in case["answers"]:
            answer.update(verdict="pass", notes="Matches the required color.")
    return reviews


def test_errors_unknown_grades_and_failed_latencies_remain_in_denominators():
    data = experiment()
    row(data, "case-1", stage="grading")["result"]["status"] = "unknown"
    failed = row(data, "case-2")
    failed["state"] = "error"
    failed["result"].update(
        status="error", total_latency_ms=900, error_category="timeout"
    )
    report = build_report(data)
    routed = report["strategies"]["routed"]
    assert routed["attempted_count"] == 3 and routed["pass_count"] == 1
    assert routed["pass_rate"] == 1 / 3 and routed["error_rate"] == 1 / 3
    assert routed["unknown_grade_count"] == 1
    assert routed["median_latency_ms"] == 101 and routed["p95_latency_ms"] == 900
    assert routed["failed_case_latencies"] == [
        {
            "case_id": "case-1",
            "latency_ms": 101,
            "error_category": None,
            "grade": "unknown",
        },
        {
            "case_id": "case-2",
            "latency_ms": 900,
            "error_category": "timeout",
            "grade": "pass",
        },
    ]
    assert Decimal(routed["total_runtime_cost_usd"]) == Decimal(".03")
    assert Decimal(routed["total_scoring_cost_usd"]) == Decimal(".003")
    assert Decimal(report["known_combined_cost_usd"]) == Decimal(".129")


def test_unknown_cost_retains_subtotal_and_previous_attempt_even_pending_retry():
    data = experiment()
    retry = row(data, "case-1")
    retry.update(
        state="pending",
        result=None,
        uncertain_attempts=[{"known_cost_usd": "0.04", "run_id": "prior"}],
    )
    score = row(data, "case-2", stage="grading")
    score["result"].update(total_cost_usd=None, cost_complete=False)
    result = build_report(data)
    routed = result["strategies"]["routed"]
    assert routed["attempted_count"] == 3
    assert routed["unknown_cost_count"] == 1
    assert routed["total_runtime_cost_usd"] is None
    assert Decimal(routed["known_runtime_cost_usd"]) == Decimal(".06")
    assert routed["unknown_scoring_cost_count"] == 1
    assert routed["total_scoring_cost_usd"] is None
    assert result["runtime_cost_savings"] is None
    assert result["runtime_cost_conclusion"] == "inconclusive"
    assert not result["complete_comparison"] and result["target_met"] is None


def test_savings_use_only_matched_cases_and_partial_run_has_no_final_target():
    data = experiment()
    row(data, "case-2", "fixed-cheap").update(state="pending", attempts=0, result=None)
    row(data, "case-2")["result"]["known_cost_usd"] = "10"
    row(data, "case-2")["result"]["total_cost_usd"] = "10"
    result = build_report(data)
    assert result["matched_case_ids"] == ["case-0", "case-1"]
    assert result["strategies"]["routed"]["attempted_count"] == 3
    assert result["runtime_cost_savings"] == 0.5
    assert result["target_met"] is None
    assert not result["complete_comparison"]


def test_missing_latency_not_zero_and_unknown_cost_in_any_strategy_blocks_savings():
    data = experiment()
    row(data, "case-0")["result"]["total_latency_ms"] = None
    row(data, "case-0", "fixed-cheap")["result"]["cost_complete"] = False
    result = build_report(data)
    assert result["median_latency_savings"] is None
    assert result["strategies"]["routed"]["unknown_latency_count"] == 1
    assert result["runtime_cost_savings"] is None


def test_real_target_requires_full_heldout_and_ten_completed_blinded_reviews():
    data = experiment(30)
    assert build_report(data)["target_met"] is None
    reviews = completed_reviews(data)
    result = build_report(data, reviews)
    assert result["manual_review_count"] == 10
    assert result["target_met"] is True
    for record in data["cases"]:
        if record["strategy"] == "routed" and record["stage"] == "grading":
            record["result"]["status"] = "fail"
    result = build_report(data, reviews)
    assert result["target_met"] is False and "not met" in result["conclusion"]
    data["mode"] = "mock"
    result = build_report(data, reviews)
    assert result["target_met"] is None and not result["research_evidence"]
    assert "Mock rehearsal" in result["conclusion"]


def test_blinding_is_reproducible_and_review_cannot_be_silently_fabricated(tmp_path):
    data = experiment(30)
    template, key = manual_template(data)
    assert (template, key) == manual_template(data)
    assert len(template["cases"]) == 10 and len(key) == 30
    assert "strategy" not in json.dumps(template)
    assert all(a["verdict"] is None for c in template["cases"] for a in c["answers"])
    write_report(data, tmp_path)
    reviews = completed_reviews(data)
    (tmp_path / "manual-review.json").write_text(json.dumps(reviews))
    write_report(data, tmp_path)
    assert json.loads((tmp_path / "manual-review.json").read_text()) == reviews
    exported = json.loads((tmp_path / "benchmark.json").read_text())
    assert exported["metrics"]["manual_review_count"] == 10
    assert exported["manual_review"] == reviews
    text = (tmp_path / "benchmark.md").read_text()
    assert "30" in text and "The frozen target was met" in text
    assert "frozen-source" in text and "frozen-history" in text
    assert "frozen-code" in text and "fixture/fixed-model" in text
    assert "Exact scorer overlap with candidates: strong" in text
    assert "coding-agent (offline fixture)" in text
    for mutation in ("answer", "reviewer", "notes"):
        broken = copy.deepcopy(reviews)
        if mutation == "reviewer":
            broken["cases"][0]["reviewer"] = ""
        else:
            broken["cases"][0]["answers"][0][mutation] = ""
        with pytest.raises(ValueError):
            build_report(data, broken)
    reviews["job_id"] = "another-job"
    with pytest.raises(ValueError, match="another experiment"):
        build_report(data, reviews)


def test_duplicate_or_foreign_case_rows_are_rejected():
    data = experiment()
    data["cases"].append(data["cases"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        build_report(data)
    data = experiment()
    data["cases"][0]["case_id"] = "not-in-dataset"
    with pytest.raises(ValueError, match="frozen dataset"):
        build_report(data)
