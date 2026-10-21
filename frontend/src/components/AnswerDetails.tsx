import { costLabel, latencyLabel, qualityLabel, type ChatResult } from '@/api'

export function AnswerDetails({ result }: { result: ChatResult }) {
  return <div className="mt-4 text-xs leading-5 text-stone-600">
    <p>{qualityLabel(result.status)} · {result.final_model} · {latencyLabel(result.total_latency_ms)} · {result.mode === 'mock'
      ? 'No API charge' : costLabel(result.total_cost_usd, result.known_cost_usd, result.cost_complete)}</p>
    <details className="mt-2">
      <summary className="w-fit cursor-pointer rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-700">Details</summary>
      <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 break-words">
        <dt>Task / difficulty</dt><dd>{result.analysis ? `${result.analysis.task} / ${result.analysis.difficulty}` : result.mode === 'mock' ? 'Not analyzed (mock)' : 'Not available'}</dd>
        {result.analysis && <><dt>Analysis</dt><dd>{result.analysis.source} · {result.analysis.reasoning} reasoning · confidence {result.analysis.confidence === null ? 'unknown' : `${Math.round(result.analysis.confidence * 100)}%`}</dd></>}
        <dt>First model</dt><dd>{result.attempts[0]?.model_key ?? 'None'}</dd>
        <dt>Final model</dt><dd>{result.final_model}</dd>
        <dt>Attempts</dt><dd>{result.attempts.length}</dd>
        <dt>Total latency</dt><dd>{latencyLabel(result.total_latency_ms)}</dd>
        <dt>Total cost</dt><dd>{costLabel(result.total_cost_usd, result.known_cost_usd, result.cost_complete)}{result.mode === 'mock' && ' (mock)'}</dd>
        {!result.cost_complete && <><dt>Reserved ceiling</dt><dd>${result.reserved_cost_usd}</dd></>}
        <dt>Escalation</dt><dd>{result.escalation_reason ?? 'None'}</dd>
      </dl>
      <ul className="mt-3 space-y-1">
        {result.route_decisions.map((route, index) => <li key={index}>Selected {route.selected_key ?? 'none'}: {route.reason}</li>)}
        {result.attempts.map((attempt, index) => <li key={`attempt-${index}`}>Attempt {index + 1}: {attempt.model_key} · {latencyLabel(attempt.latency_ms)} · {attempt.error_category ?? attempt.finish_reason}</li>)}
      </ul>
      <p className="mt-3">Judge approval is a quality signal, not a guarantee of correctness. Costs include classification, generation, and evaluation when called.</p>
      <p className="mt-1 break-all">Run: {result.run_id}</p>
    </details>
    {result.warnings.map((warning, index) => <p className="mt-2" key={index}>{warning}</p>)}
  </div>
}
