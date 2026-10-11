from decimal import Decimal

from app.config import reserve_cost


def choose_route(
    analysis, registry, messages, available_keys, budget, remaining_seconds
):
    bucket = f"{analysis.task}:{analysis.difficulty}"
    candidates = []
    ranks = {}
    input_tokens = sum(
        len(message.content.encode("utf-8")) + 256 for message in messages
    )
    for model in sorted(registry.models, key=lambda model: model.key):
        quality = model.prior_quality.get(
            bucket, model.prior_quality.get(analysis.difficulty)
        )
        cost = reservation = None
        exclusion = None
        if (
            model.input_usd_per_million is not None
            and model.output_usd_per_million is not None
        ):
            # shortcut: fixed output prior; replace with compatible history in Phase 05.
            cost = (
                input_tokens * model.input_usd_per_million
                + min(256, model.max_output_tokens) * model.output_usd_per_million
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
                elif model.prior_latency_ms / 1000 > remaining_seconds:
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
                "latency_ms": model.prior_latency_ms,
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
                reason = "Eligible quality prior; lowest weighted cost/latency."
            else:
                selected = min(
                    eligible,
                    key=lambda c: (
                        -c["quality"],
                        Decimal(c["estimated_cost_usd"]),
                        c["key"],
                    ),
                )
                reason = "below_target: selected highest available quality prior."
    return {
        "selected_key": selected["key"] if selected else None,
        "bucket": bucket,
        "policy_version": "priors-v1",
        "candidates": candidates,
        "reason": reason,
        "source": "priors",
    }
