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
  attempts: { model_key: string; latency_ms: number; error_category: string | null; finish_reason: string }[]
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

export async function fetchRuns(): Promise<Run[]> {
  const response = await fetch('/api/runs?limit=20', { signal: AbortSignal.timeout(10000) })
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
    && isMoney(job.budget_usd) && isMoney(job.budget_used_usd))) throw new Error()
  return rows
}
