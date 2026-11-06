export type ChatResult = {
  run_id: string
  answer: string
  mode: 'mock' | 'live'
  final_model: string
  total_latency_ms: number
  total_cost_usd: string | null
  known_cost_usd: string
  reserved_cost_usd: string
  cost_complete: boolean
  status: 'passed' | 'quality_failed' | 'unverified'
  analysis: { task: string; difficulty: string; reasoning: string; confidence: number | null; source: string } | null
  attempts: { model_key: string; model_id: string; latency_ms: number; error_category: string | null; finish_reason: string }[]
  escalation_reason: string | null
  route_decisions: { selected_key: string | null; reason: string }[]
  warnings: string[]
}

export type Run = {
  id: string
  created_at: string
  mode: string
  status: string
  final_model: string | null
  total_latency_ms: number | null
  total_cost_usd: string | number | null
  known_cost_usd: string | number
  cost_complete: boolean
}

export type RunDetail = Run & {
  messages: { role: string; content: string }[]
  final_answer: string | null
  analysis: ChatResult['analysis']
  route_decisions: ChatResult['route_decisions']
  escalation_reason: string | null
  reserved_cost_usd: string | number
  evaluations: { attempt: number; model_key: string; status: string; reason: string }[]
  calls: {
    sequence: number; stage: string; attempt: number; model_id: string; status: string
    latency_ms: number; input_tokens: number | null; output_tokens: number | null
    cost_usd: string | number | null; error: { code: string } | null
    output: { model_key?: string; text?: string; finish_reason?: string } | null
  }[]
  error: { code: string } | null
}

export type Benchmark = {
  job_id: string
  created_at: string
  status: string
  strategy: string
  mode: string
  case_count: number
  states: { pending: number; running: number; done: number; error: number; uncertain: number }
  online_pass_count: number
  known_cost_usd: string
  cost_complete: boolean
  budget_usd: string
  budget_used_usd: string
  quality_basis: string
  scoring_known_cost_usd?: string
  scoring_cost_complete?: boolean
  strategy_metrics?: Record<string, {
    attempted_count: number
    pass_count: number
    total_runtime_cost_usd: string | null
    median_latency_ms: number | null
  }>
}

export type BenchmarkDetail = Benchmark & {
  dataset_hash: string
  history_snapshot_id: string | null
  cases: { ordinal: number; case_id: string; strategy: string; stage: string; state: string; run_id: string | null; attempts: number }[]
}

export async function fetchRun(id: string): Promise<RunDetail> {
  const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { signal: AbortSignal.timeout(10000) })
  if (!response.ok) throw new Error()
  const run = await response.json()
  if (!run || run.id !== id || !Array.isArray(run.messages) || !Array.isArray(run.calls)
    || !run.messages.every((message: RunDetail['messages'][number]) => message && typeof message.role === 'string' && typeof message.content === 'string')
    || !Array.isArray(run.route_decisions) || !run.route_decisions.every((route: RunDetail['route_decisions'][number]) => route && typeof route.reason === 'string' && (route.selected_key === null || typeof route.selected_key === 'string'))
    || !Array.isArray(run.evaluations) || !run.evaluations.every((grade: RunDetail['evaluations'][number]) => grade && Number.isInteger(grade.attempt) && [grade.model_key, grade.status, grade.reason].every(value => typeof value === 'string'))
    || !run.calls.every((call: RunDetail['calls'][number]) => call
      && Number.isInteger(call.sequence) && Number.isInteger(call.attempt)
      && [call.stage, call.model_id, call.status].every(value => typeof value === 'string')
      && Number.isFinite(call.latency_ms) && call.latency_ms >= 0
      && [call.input_tokens, call.output_tokens].every(value => value === null || Number.isInteger(value) && value >= 0)
      && (call.cost_usd === null || isMoney(call.cost_usd))
      && (call.error === null || typeof call.error?.code === 'string')
      && (call.output === null || typeof call.output === 'object'
        && [call.output.model_key, call.output.text].every(value => value === undefined || typeof value === 'string')))
    || ![run.mode, run.status].every(value => typeof value === 'string')
    || ![run.final_model, run.final_answer, run.escalation_reason].every(value => value === null || typeof value === 'string')
    || !(run.total_latency_ms === null || Number.isFinite(run.total_latency_ms) && run.total_latency_ms >= 0)
    || typeof run.cost_complete !== 'boolean' || !isMoney(run.known_cost_usd) || !isMoney(run.reserved_cost_usd)
    || !(run.total_cost_usd === null || isMoney(run.total_cost_usd))
    || !(run.error === null || typeof run.error?.code === 'string')
    || !(run.analysis === null || run.analysis
      && [run.analysis.task, run.analysis.difficulty, run.analysis.reasoning, run.analysis.source].every(value => typeof value === 'string')
      && (run.analysis.confidence === null || Number.isFinite(run.analysis.confidence) && run.analysis.confidence >= 0 && run.analysis.confidence <= 1))) throw new Error()
  return run
}

export async function fetchBenchmark(id: string): Promise<BenchmarkDetail> {
  const response = await fetch(`/api/benchmarks/${encodeURIComponent(id)}`, { signal: AbortSignal.timeout(10000) })
  if (!response.ok) throw new Error()
  const job = await response.json()
  if (!job || job.job_id !== id || typeof job.dataset_hash !== 'string'
    || !(job.history_snapshot_id === null || typeof job.history_snapshot_id === 'string')
    || !Array.isArray(job.cases) || !job.cases.every((item: BenchmarkDetail['cases'][number]) => item
      && Number.isInteger(item.ordinal) && Number.isInteger(item.attempts)
      && [item.case_id, item.strategy, item.stage, item.state].every(value => typeof value === 'string')
      && (item.run_id === null || typeof item.run_id === 'string'))) throw new Error()
  return job
}

export function isMoney(value: unknown): value is string | number {
  return (typeof value === 'string' && /^\d+(\.\d+)?([eE][+-]?\d+)?$/.test(value)
    || typeof value === 'number') && Number.isFinite(Number(value)) && Number(value) >= 0
}

export function isChatResult(result: ChatResult): boolean {
  return result && typeof result.run_id === 'string' && typeof result.answer === 'string'
    && ['mock', 'live'].includes(result.mode) && typeof result.final_model === 'string'
    && ['passed', 'quality_failed', 'unverified'].includes(result.status)
    && Number.isFinite(result.total_latency_ms) && result.total_latency_ms >= 0
    && (result.escalation_reason === null || typeof result.escalation_reason === 'string')
    && typeof result.cost_complete === 'boolean'
    && (result.total_cost_usd === null || isMoney(result.total_cost_usd))
    && isMoney(result.known_cost_usd) && isMoney(result.reserved_cost_usd)
    && (result.analysis === null || result.analysis
      && [result.analysis.task, result.analysis.difficulty, result.analysis.reasoning, result.analysis.source].every(value => typeof value === 'string')
      && (result.analysis.confidence === null || Number.isFinite(result.analysis.confidence)
        && result.analysis.confidence >= 0 && result.analysis.confidence <= 1))
    && Array.isArray(result.attempts) && result.attempts.every(attempt => attempt
      && typeof attempt.model_key === 'string' && Number.isFinite(attempt.latency_ms) && attempt.latency_ms >= 0
      && typeof attempt.model_id === 'string'
      && typeof attempt.finish_reason === 'string'
      && (attempt.error_category === null || typeof attempt.error_category === 'string'))
    && Array.isArray(result.route_decisions) && result.route_decisions.every(route => route
      && typeof route.reason === 'string' && (route.selected_key === null || typeof route.selected_key === 'string'))
    && Array.isArray(result.warnings) && result.warnings.every(warning => typeof warning === 'string')
}

export function costLabel(total: string | number | null, known: string | number, complete: boolean) {
  if (complete && total !== null) return `Estimated $${total}`
  return `Incomplete · known $${known}`
}

export function qualityLabel(status: string) {
  if (status === 'passed') return 'Judge passed'
  if (status === 'quality_failed') return 'Quality check failed'
  if (status === 'unverified') return 'Unverified'
  return status.replaceAll('_', ' ')
}

export function latencyLabel(milliseconds: number | null) {
  return milliseconds === null ? 'Unknown' : `${(milliseconds / 1000).toFixed(2)} s`
}

export async function fetchRuns(offset = 0): Promise<Run[]> {
  const response = await fetch(`/api/runs?limit=20&offset=${offset}`, { signal: AbortSignal.timeout(10000) })
  if (!response.ok) throw new Error()
  const rows = await response.json()
  if (!Array.isArray(rows) || !rows.every((run: Run) => run
    && [run.id, run.created_at, run.mode, run.status].every(value => typeof value === 'string')
    && (run.final_model === null || typeof run.final_model === 'string')
    && (run.total_latency_ms === null || Number.isFinite(run.total_latency_ms) && run.total_latency_ms >= 0)
    && typeof run.cost_complete === 'boolean' && isMoney(run.known_cost_usd)
    && (run.total_cost_usd === null || isMoney(run.total_cost_usd)))) throw new Error()
  return rows
}

export async function fetchBenchmarks(): Promise<Benchmark[]> {
  const response = await fetch('/api/benchmarks?limit=20', { signal: AbortSignal.timeout(10000) })
  if (!response.ok) throw new Error()
  const rows = await response.json()
  if (!Array.isArray(rows) || !rows.every((job: Benchmark) => job
    && [job.job_id, job.created_at, job.status, job.strategy, job.mode, job.quality_basis].every(value => typeof value === 'string')
    && Number.isInteger(job.case_count) && job.case_count >= 0
    && Number.isInteger(job.online_pass_count) && job.online_pass_count >= 0
    && job.states && [job.states.pending, job.states.running, job.states.done, job.states.error, job.states.uncertain].every(value => Number.isInteger(value) && value >= 0)
    && typeof job.cost_complete === 'boolean' && isMoney(job.known_cost_usd)
    && (job.scoring_known_cost_usd === undefined || isMoney(job.scoring_known_cost_usd))
    && (job.scoring_cost_complete === undefined || typeof job.scoring_cost_complete === 'boolean')
    && (job.strategy_metrics === undefined || job.strategy_metrics
      && Object.entries(job.strategy_metrics).every(([strategy, metrics]) =>
        ['fixed-cheap', 'fixed-strong', 'routed'].includes(strategy) && metrics
        && Number.isInteger(metrics.attempted_count) && metrics.attempted_count >= 0
        && Number.isInteger(metrics.pass_count) && metrics.pass_count >= 0 && metrics.pass_count <= metrics.attempted_count
        && (metrics.total_runtime_cost_usd === null || isMoney(metrics.total_runtime_cost_usd))
        && (metrics.median_latency_ms === null || Number.isFinite(metrics.median_latency_ms) && metrics.median_latency_ms >= 0)))
    && isMoney(job.budget_usd) && isMoney(job.budget_used_usd))) throw new Error()
  return rows
}
