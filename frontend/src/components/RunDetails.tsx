import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { costLabel, fetchRun, latencyLabel, qualityLabel, type RunDetail } from '@/api'

export function RunDetails({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      setRun(await fetchRun(runId))
    } catch {
      setError('Could not load run details.')
    } finally {
      setLoading(false)
    }
  }

  const generations = run?.calls.filter(call => call.stage === 'generate') ?? []
  const modelLabel = (key: string | null) => generations.find(call => call.output?.model_key === key)?.model_id ?? key ?? 'None'

  return <details className="text-sm [overflow-wrap:anywhere]" onToggle={event => {
    if (event.target === event.currentTarget && event.currentTarget.open && !run && !loading && !error) void load()
  }}>
    <summary className="w-fit cursor-pointer rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-700">Run details</summary>
    <p className="mt-2 break-all text-xs text-stone-500">Run: {runId}</p>
    {loading && <p role="status" className="mt-3">Loading run details…</p>}
    {error && <div role="alert" className="mt-3 text-red-700">{error} <Button variant="outline" onClick={() => void load()}>Retry run details</Button></div>}
    {run && <div className="mt-4 space-y-4">
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-xs leading-5">
        <dt>Mode / quality</dt><dd>{run.mode} · {qualityLabel(run.status)}</dd>
        <dt>Task / difficulty</dt><dd>{run.analysis ? `${run.analysis.task} / ${run.analysis.difficulty}` : run.mode === 'mock' ? 'Not analyzed (mock)' : 'Not available'}</dd>
        {run.analysis && <><dt>Analysis</dt><dd>{run.analysis.source} · {run.analysis.reasoning} reasoning · confidence {run.analysis.confidence === null ? 'unknown' : `${Math.round(run.analysis.confidence * 100)}%`}</dd></>}
        <dt>First model</dt><dd>{generations[0]?.model_id ?? 'None'}</dd>
        <dt>Final model</dt><dd>{modelLabel(run.final_model)}</dd>
        <dt>Attempts</dt><dd>{generations.length}</dd>
        <dt>Total latency</dt><dd>{latencyLabel(run.total_latency_ms)}</dd>
        <dt>Total cost</dt><dd>{costLabel(run.total_cost_usd, run.known_cost_usd, run.cost_complete)}{run.mode === 'mock' && ' (mock · No API charge)'}</dd>
        {!run.cost_complete && <><dt>Reserved ceiling</dt><dd>${run.reserved_cost_usd}</dd></>}
        <dt>Escalation</dt><dd>{run.escalation_reason ?? 'None'}</dd>
        {run.error && <><dt>Error</dt><dd>{run.error.code}</dd></>}
      </dl>
      <div><h3 className="font-medium">Conversation</h3>
        {run.messages.map((message, index) => <div key={index} className="mt-2">
          <p className="text-xs font-medium text-stone-500">{message.role === 'user' ? 'You' : 'Arbiter'}</p>
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>)}
      </div>
      <div><h3 className="font-medium">Answer</h3><p className="mt-2 whitespace-pre-wrap">{run.final_answer ?? 'No answer was saved.'}</p></div>
      {run.route_decisions.length > 0 && <div><h3 className="font-medium">Routing</h3><ul className="mt-2 space-y-1 text-xs leading-5">
        {run.route_decisions.map((route, index) => <li key={index}>Selected {modelLabel(route.selected_key)}: {route.reason}</li>)}
      </ul></div>}
      {run.evaluations.length > 0 && <div><h3 className="font-medium">Evaluations</h3><ul className="mt-2 space-y-1 text-xs leading-5">
        {run.evaluations.map((grade, index) => <li key={index}>Attempt {grade.attempt} · {modelLabel(grade.model_key)} · {grade.status}: {grade.reason}</li>)}
      </ul><p className="mt-2 text-xs text-stone-500">Online judge signals are not a guarantee of correctness.</p></div>}
      <div><h3 className="font-medium">Calls</h3>
        {run.calls.length === 0 && <p className="mt-2 text-xs">No calls recorded.</p>}
        <ul className="mt-2 space-y-2 text-xs leading-5">{run.calls.map(call => <li key={call.sequence}>
          <p>{call.stage} · attempt {call.attempt} · {call.model_id} · {call.error?.code ?? call.status}</p>
          <p className="text-stone-600">{latencyLabel(call.latency_ms)} · {call.cost_usd === null ? 'Cost unknown' : `Estimated $${call.cost_usd}`} · tokens {call.input_tokens ?? 'unknown'} in / {call.output_tokens ?? 'unknown'} out</p>
          {call.stage === 'generate' && call.output?.text && <details className="mt-1"><summary className="cursor-pointer">Attempt answer</summary><p className="mt-1 whitespace-pre-wrap">{call.output.text}</p></details>}
        </li>)}</ul>
      </div>
    </div>}
  </details>
}
