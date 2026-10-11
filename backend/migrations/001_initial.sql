CREATE TABLE runs (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    messages JSONB NOT NULL,
    analysis JSONB,
    route_decisions JSONB NOT NULL DEFAULT '[]',
    final_answer TEXT,
    final_model TEXT,
    total_latency_ms INTEGER NOT NULL DEFAULT 0,
    total_cost_usd NUMERIC,
    known_cost_usd NUMERIC NOT NULL DEFAULT 0,
    cost_complete BOOLEAN NOT NULL DEFAULT false,
    config_version TEXT NOT NULL,
    rubric_version TEXT,
    policy_version TEXT,
    error JSONB
);
CREATE INDEX runs_created_at_idx ON runs (created_at DESC);

CREATE TABLE calls (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id),
    sequence INTEGER NOT NULL,
    stage TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    raw_usage JSONB,
    price_snapshot JSONB,
    cost_usd NUMERIC,
    cost_source TEXT NOT NULL,
    output JSONB,
    error JSONB,
    UNIQUE (run_id, sequence)
);
