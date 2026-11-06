CREATE TABLE IF NOT EXISTS run_summaries (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_ids JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    reserved_cost_usd NUMERIC NOT NULL,
    result JSONB
);
