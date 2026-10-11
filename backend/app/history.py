import hashlib
import json

from psycopg.types.json import Jsonb

POLICY_VERSION = "history-v1"
RUBRIC_VERSION = "rubric-v1"


def judge_identity(registry):
    judge = next((m for m in registry.models if m.key == registry.judge_key), None)
    return {"provider": judge.provider, "model_id": judge.model_id} if judge else None


def load_history(pool, registry):
    judge = judge_identity(registry)
    configured = [
        {"key": m.key, "provider": m.provider, "model_id": m.model_id}
        for m in registry.models
    ]
    with pool.connection() as connection:
        entries = connection.execute(
            """
            WITH attempts AS (
                SELECT (r.analysis->>'task') || ':' ||
                       (r.analysis->>'difficulty') AS bucket,
                       m.key AS model_key, c.provider, c.model_id,
                       c.latency_ms, c.output_tokens,
                       CASE
                         WHEN c.output->>'error_category' IS NOT NULL THEN 'fail'
                         WHEN grade->>'status' = 'fail'
                           AND grade->>'error_category' = 'incomplete_answer'
                           AND (c.output->>'finish_reason' = 'length'
                                OR btrim(c.output->>'text') = '') THEN 'fail'
                         WHEN grade->>'status' IN ('pass', 'fail')
                           AND EXISTS (
                               SELECT 1 FROM calls j WHERE j.run_id = c.run_id
                               AND j.stage = 'evaluate' AND j.attempt = c.attempt
                           ) THEN grade->>'status'
                         ELSE 'unknown'
                       END AS label
                FROM calls c JOIN runs r ON r.id = c.run_id
                JOIN jsonb_to_recordset(%s::jsonb)
                     AS m(key TEXT, provider TEXT, model_id TEXT)
                  ON m.key = c.output->>'model_key'
                 AND m.provider = c.provider AND m.model_id = c.model_id
                LEFT JOIN LATERAL (
                    SELECT value AS grade FROM jsonb_array_elements(r.evaluations)
                    WHERE value->>'attempt' = c.attempt::text
                      AND value->>'model_key' = m.key LIMIT 1
                ) e ON true
                WHERE c.stage = 'generate' AND r.mode IN ('live', 'dev')
                  AND r.status != 'running'
                  AND r.policy_version = %s AND r.rubric_version = %s
                  AND r.analysis->>'task' IS NOT NULL
                  AND r.analysis->>'difficulty' IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM calls j WHERE j.run_id = c.run_id
                      AND j.stage = 'evaluate' AND j.attempt = c.attempt
                      AND (j.provider IS DISTINCT FROM %s
                           OR j.model_id IS DISTINCT FROM %s)
                  )
            )
            SELECT bucket, model_key, provider, model_id,
                   count(*) FILTER (WHERE label != 'unknown') AS n,
                   count(*) FILTER (WHERE label = 'pass') AS passes,
                   count(*) FILTER (WHERE label = 'fail') AS failures,
                   count(*) FILTER (WHERE label = 'unknown') AS unknown_count,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms)
                     FILTER (WHERE label != 'unknown' AND latency_ms >= 0)
                     AS latency_ms,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY output_tokens)
                     FILTER (WHERE label != 'unknown' AND output_tokens >= 0)
                     AS output_tokens
            FROM attempts GROUP BY bucket, model_key, provider, model_id
            ORDER BY bucket, model_key, provider, model_id
            """,
            (
                Jsonb(configured),
                POLICY_VERSION,
                RUBRIC_VERSION,
                judge["provider"] if judge else None,
                judge["model_id"] if judge else None,
            ),
        ).fetchall()
    snapshot = {
        "policy_version": POLICY_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "judge": judge,
        "entries": entries,
    }
    snapshot["id"] = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True).encode()
    ).hexdigest()
    return snapshot
