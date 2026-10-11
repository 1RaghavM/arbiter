from decimal import Decimal

from app.config import reserve_cost
from app.history import POLICY_VERSION, RUBRIC_VERSION, judge_identity


def choose_route(
    analysis,
    registry,
    messages,
    available_keys,
    budget,
    remaining_seconds,
    history=None,
):
    bucket = f"{analysis.task}:{analysis.difficulty}"
    candidates = []
    ranks = {}
    compatible = (
        history is not None
        and history.get("policy_version") == POLICY_VERSION
        and history.get("rubric_version") == RUBRIC_VERSION
        and history.get("judge") == judge_identity(registry)
    )
    entries = history["entries"] if compatible else []
    input_tokens = sum(
        len(message.content.encode("utf-8")) + 256 for message in messages
    )
    for model in sorted(registry.models, key=lambda model: model.key):
        quality = model.prior_quality.get(
            bucket, model.prior_quality.get(analysis.difficulty)
        )
        latency = model.prior_latency_ms
        output_tokens = min(256, model.max_output_tokens)
        sample = next(
            (
                entry
                for entry in entries
                if entry["bucket"] == bucket
                and entry["model_key"] == model.key
                and entry["provider"] == model.provider
                and entry["model_id"] == model.model_id
            ),
            None,
        )
        source = "priors"
        if sample and sample["n"] >= 5 and quality is not None:
            quality = (sample["passes"] + 5 * quality) / (sample["n"] + 5)
            if sample["latency_ms"] is not None:
                latency = max(1, sample["latency_ms"])
            if sample["output_tokens"] is not None:
                output_tokens = min(sample["output_tokens"], model.max_output_tokens)
            source = "history"
        cost = reservation = None
        exclusion = None
        if (
            model.input_usd_per_million is not None
            and model.output_usd_per_million is not None
        ):
            cost = (
                input_tokens * model.input_usd_per_million
                + Decimal(str(output_tokens)) * model.output_usd_per_million
            ) / 1_000_000
        if not model.enabled:
            exclusion = "disabled"
        elif model.key not in available_keys:
            exclusion = "unavailable"
        elif (
            quality is None
            or model.prior_latency_ms is None
            or model.capability_rank is None
        ):
            exclusion = "missing_priors"
        else:
            try:
                reservation = reserve_cost(model, messages)
            except ValueError:
                exclusion = "context_limit"
            if exclusion is None:
                if reservation > budget:
                    exclusion = "budget"
                elif latency / 1000 > remaining_seconds:
                    exclusion = "deadline"
        candidates.append(
            {
                "key": model.key,
                "eligible": exclusion is None,
                "exclusion_reason": exclusion,
                "quality": quality,
                "estimated_cost_usd": str(cost) if cost is not None else None,
                "reserved_cost_usd": str(reservation)
                if reservation is not None
                else None,
                "latency_ms": latency,
                "expected_output_tokens": output_tokens,
                "estimate_source": source,
                "history_n": sample["n"] if sample else 0,
                "unknown_count": sample["unknown_count"] if sample else 0,
                "score": None,
            }
        )
        ranks[model.key] = model.capability_rank

    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    selected = None
    reason = "No candidate fits the configured hard limits."
    if eligible:
        fallback = (
            analysis.source == "fallback"
            or analysis.confidence is None
            or analysis.confidence < 0.60
        )
        if fallback:
            selected = next(
                (c for c in eligible if c["key"] == registry.strong_baseline_key), None
            )
            if selected is None:
                selected = min(eligible, key=lambda c: (-ranks[c["key"]], c["key"]))
            reason = "Classifier fallback; strong model or highest available rank."
        else:
            above_floor = [
                c for c in eligible if c["quality"] >= registry.quality_floor
            ]
            if above_floor:
                max_cost = max(
                    max(Decimal(c["estimated_cost_usd"]) for c in above_floor),
                    Decimal("1e-12"),
                )
                max_latency = max(c["latency_ms"] for c in above_floor)
                for candidate in above_floor:
                    candidate["score"] = float(
                        Decimal(str(registry.cost_weight))
                        * Decimal(candidate["estimated_cost_usd"])
                        / max_cost
                        + Decimal(str(registry.latency_weight))
                        * Decimal(candidate["latency_ms"])
                        / max_latency
                    )
                selected = min(above_floor, key=lambda c: (c["score"], c["key"]))
                reason = "Eligible quality estimate; lowest weighted cost/latency."
            else:
                selected = min(
                    eligible,
                    key=lambda c: (
                        -c["quality"],
                        Decimal(c["estimated_cost_usd"]),
                        c["key"],
                    ),
                )
                reason = "below_target: selected highest available quality estimate."
    return {
        "selected_key": selected["key"] if selected else None,
        "bucket": bucket,
        "policy_version": POLICY_VERSION,
        "candidates": candidates,
        "reason": reason,
        "source": "history"
        if any(c["estimate_source"] == "history" for c in candidates)
        else "priors",
        "history_snapshot_id": history["id"] if compatible else None,
    }
