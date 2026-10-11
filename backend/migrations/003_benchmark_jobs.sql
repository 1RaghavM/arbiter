CREATE TABLE benchmark_jobs (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'blocked', 'uncertain', 'completed')),
    strategy TEXT NOT NULL DEFAULT 'routed' CHECK (strategy = 'routed'),
    dataset_hash TEXT NOT NULL,
    dataset JSONB NOT NULL,
    config_snapshot JSONB NOT NULL,
    history_snapshot JSONB NOT NULL,
    spend_ceiling_usd NUMERIC NOT NULL CHECK (spend_ceiling_usd > 0),
    budget_used_usd NUMERIC NOT NULL DEFAULT 0 CHECK (budget_used_usd >= 0),
    known_cost_usd NUMERIC NOT NULL DEFAULT 0 CHECK (known_cost_usd >= 0),
    cost_complete BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE benchmark_cases (
    job_id UUID NOT NULL REFERENCES benchmark_jobs(id),
    case_id TEXT NOT NULL,
    strategy TEXT NOT NULL DEFAULT 'routed' CHECK (strategy = 'routed'),
    ordinal INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'running', 'done', 'error', 'uncertain')),
    run_id UUID,
    attempts INTEGER NOT NULL DEFAULT 0,
    reserved_cost_usd NUMERIC NOT NULL DEFAULT 0,
    result JSONB,
    uncertain_attempts JSONB NOT NULL DEFAULT '[]',
    PRIMARY KEY (job_id, case_id, strategy),
    UNIQUE (job_id, ordinal)
);

ALTER TABLE runs ADD COLUMN benchmark_job_id UUID REFERENCES benchmark_jobs(id);
CREATE INDEX runs_benchmark_job_idx ON runs (benchmark_job_id);
