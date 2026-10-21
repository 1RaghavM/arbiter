ALTER TABLE benchmark_jobs DROP CONSTRAINT benchmark_jobs_strategy_check;
ALTER TABLE benchmark_jobs ADD CHECK (strategy IN ('routed', 'comparison'));
ALTER TABLE benchmark_jobs ADD COLUMN scoring_known_cost_usd NUMERIC NOT NULL DEFAULT 0;
ALTER TABLE benchmark_jobs ADD COLUMN scoring_cost_complete BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE benchmark_cases DROP CONSTRAINT benchmark_cases_strategy_check;
ALTER TABLE benchmark_cases ADD CHECK (strategy IN ('routed', 'fixed-cheap', 'fixed-strong'));
ALTER TABLE benchmark_cases ADD COLUMN stage TEXT NOT NULL DEFAULT 'runtime'
    CHECK (stage IN ('runtime', 'grading'));
ALTER TABLE benchmark_cases DROP CONSTRAINT benchmark_cases_pkey;
ALTER TABLE benchmark_cases ADD PRIMARY KEY (job_id, case_id, strategy, stage);
