import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { costLabel, fetchBenchmarks, fetchRuns, latencyLabel, qualityLabel, type Benchmark, type Run } from '@/api'

export function ResultsView() {
  const [selected, setSelected] = useState<string[]>([])
  const [summarizing, setSummarizing] = useState(false)
  const [summaryError, setSummaryError] = useState('')
  async function downloadSummary() {
    setSummarizing(true)
    setSummaryError('')
    try {
      const response = await fetch('/api/run-summaries', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_ids: selected }), signal: AbortSignal.timeout(70000),
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.message ?? 'Could not create summary.')
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = 'arbiter-run-summary.md'
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      setSummaryError('Summary failed. Check the server budget and model access, or select fewer runs. Retrying may incur another charge.')
    } finally { setSummarizing(false) }
  }
  const [runs, setRuns] = useState<Run[]>([])
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([])
  const [runsLoading, setRunsLoading] = useState(true)
  const [benchmarksLoading, setBenchmarksLoading] = useState(true)
  const [runsError, setRunsError] = useState('')
  const [benchmarksError, setBenchmarksError] = useState('')

  function refreshRuns() {
    return fetchRuns().then(rows => { setRuns(rows); setSelected([]) })
      .catch(() => setRunsError('Could not load recent runs. Refresh to try again.'))
      .finally(() => setRunsLoading(false))
  }

  function refreshBenchmarks() {
    return fetchBenchmarks().then(setBenchmarks)
      .catch(() => setBenchmarksError('Could not load benchmark jobs. Refresh to try again.'))
      .finally(() => setBenchmarksLoading(false))
  }

  useEffect(() => {
    void refreshRuns()
    void refreshBenchmarks()
  }, [])

  return <div className="space-y-10">
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Runs & benchmarks</h1>
      <p className="mt-2 text-sm text-stone-600">Browse saved runs and the latest 20 benchmark jobs. Select up to 100 runs per report.</p>
    </div>
    <section aria-label="Chat summary" className="space-y-3 rounded-lg border p-4">
      <h2 className="font-semibold">Summarize completed chats</h2>
      <p className="text-sm text-stone-600">Select runs below. Sonnet 5.5 analyzes their saved conversations and results with Arbiter project context and downloads one Markdown report. This is a paid API request within the server budget.</p>
      <Button variant="outline" disabled={summarizing || !runs.length} onClick={() => setSelected(runs.filter(run => ['passed', 'quality_failed', 'unverified', 'error'].includes(run.status)).map(run => run.id))}>Select all completed</Button>{' '}
      <Button variant="outline" disabled={summarizing || !selected.length} onClick={() => setSelected([])}>Clear selection</Button>{' '}
      <Button disabled={summarizing || !selected.length || selected.length > 100} onClick={() => void downloadSummary()}>{summarizing ? 'Analyzing…' : `Download summary (${selected.length})`}</Button>
      {summaryError && <p role="alert" className="text-sm text-red-700">{summaryError}</p>}
    </section>
    <section aria-labelledby="runs-heading" aria-busy={runsLoading}>
      <div className="flex items-center justify-between gap-3">
        <h2 id="runs-heading" className="text-lg font-semibold">Recent runs</h2>
        <Button variant="outline" onClick={() => { setRunsLoading(true); setRunsError(''); void refreshRuns() }} disabled={runsLoading}>Refresh runs</Button>
      </div>
      {runsLoading && <p role="status" className="mt-3 text-sm text-stone-600">Loading runs…</p>}
      {runsError && <p role="alert" className="mt-3 text-sm text-red-700">{runsError} {runs.length > 0 && 'Previously loaded records are shown below.'}</p>}
      {!runsLoading && !runsError && runs.length === 0 && <p className="mt-4 text-sm text-stone-600">No runs yet. Send a message to create one.</p>}
      {runs.length > 0 && <div role="region" aria-label="Recent runs table" tabIndex={0} className="mt-4 overflow-x-auto rounded-lg border bg-white focus-visible:outline-2 focus-visible:outline-stone-700">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Recent request runs, including mock and failed requests</caption>
          <thead className="bg-stone-100 text-xs text-stone-600"><tr>
            {['Select', 'Run / mode', 'Quality / model', 'Latency', 'Runtime cost'].map(label => <th scope="col" key={label} className="px-4 py-3 font-medium">{label}</th>)}
          </tr></thead>
          <tbody>{runs.map(run => <tr key={run.id} className="border-t align-top">
            <td className="px-4 py-3"><input type="checkbox" aria-label={`Select run ${run.id}`} disabled={summarizing || !['passed', 'quality_failed', 'unverified', 'error'].includes(run.status)} checked={selected.includes(run.id)} onChange={event => setSelected(event.target.checked ? [...selected, run.id] : selected.filter(id => id !== run.id))} /></td>
            <td className="px-4 py-3"><time className="whitespace-nowrap" dateTime={run.created_at}>{new Date(run.created_at).toLocaleString()}</time><p className="text-xs text-stone-600">{run.mode}</p><details><summary className="cursor-pointer text-xs">Run ID</summary><p className="max-w-48 break-all text-xs">{run.id}</p></details></td>
            <td className="px-4 py-3"><p>{qualityLabel(run.status)}</p><p className="text-xs text-stone-600">{run.final_model ?? 'No model'}</p></td>
            <td className="whitespace-nowrap px-4 py-3">{latencyLabel(run.total_latency_ms)}</td>
            <td className="px-4 py-3">{costLabel(run.total_cost_usd, run.known_cost_usd, run.cost_complete)}{run.mode === 'mock' && <p className="text-xs text-stone-600">No API charge</p>}</td>
          </tr><tr><td colSpan={5} className="px-4 pb-4"><div className="sticky left-4 w-[calc(100vw-4.5rem)] max-w-[43.25rem]"><RunDetails runId={run.id} /></div></td></tr></Fragment>)}</tbody>
        </table>
      </div>}
      <Button className="mt-3" variant="outline" disabled={runsLoading || summarizing} onClick={async () => {
        setRunsLoading(true)
        setRunsError('')
        try {
          const more = await fetchRuns(runs.length)
          setRuns(current => [...current, ...more.filter(row => !current.some(run => run.id === row.id))])
          if (!more.length) setRunsError('No more runs.')
        } catch { setRunsError('Could not load more runs.') }
        finally { setRunsLoading(false) }
      }}>Load older runs</Button>
    </section>
    <section aria-labelledby="benchmarks-heading" aria-busy={benchmarksLoading}>
      <div className="flex items-center justify-between gap-3">
        <h2 id="benchmarks-heading" className="text-lg font-semibold">Benchmark jobs</h2>
        <Button variant="outline" onClick={() => { setBenchmarksLoading(true); setBenchmarksError(''); void refreshBenchmarks() }} disabled={benchmarksLoading}>Refresh benchmarks</Button>
      </div>
      <p className="mt-3 text-sm text-stone-600">Comparison jobs use independent grading. Development jobs show online judge signals only; mock jobs are not live research evidence.</p>
      {benchmarksLoading && <p role="status" className="mt-3 text-sm text-stone-600">Loading benchmark jobs…</p>}
      {benchmarksError && <p role="alert" className="mt-3 text-sm text-red-700">{benchmarksError} {benchmarks.length > 0 && 'Previously loaded records are shown below.'}</p>}
      {!benchmarksLoading && !benchmarksError && benchmarks.length === 0 && <p className="mt-4 text-sm text-stone-600">No benchmark jobs yet. Completed CLI jobs will appear here.</p>}
      {benchmarks.length > 0 && <div role="region" aria-label="Benchmark jobs table" tabIndex={0} className="mt-4 overflow-x-auto rounded-lg border bg-white focus-visible:outline-2 focus-visible:outline-stone-700">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Persisted benchmark summaries</caption>
          <thead className="bg-stone-100 text-xs text-stone-600"><tr>
            {['Job / strategy', 'Progress', 'Quality / comparison', 'Cost / budget'].map(label => <th scope="col" key={label} className="px-4 py-3 font-medium">{label}</th>)}
          </tr></thead>
          <tbody>{benchmarks.map(job => <tr key={job.job_id} className="border-t align-top">
            <td className="px-4 py-3"><time className="whitespace-nowrap" dateTime={job.created_at}>{new Date(job.created_at).toLocaleString()}</time><p className="text-xs text-stone-600">{job.strategy} · {job.mode}</p><details><summary className="cursor-pointer text-xs">Job ID</summary><p className="max-w-48 break-all text-xs">{job.job_id}</p></details></td>
            <td className="px-4 py-3"><p>{job.status.replaceAll('_', ' ')}</p><p className="text-xs text-stone-600">{job.states.done} done / {job.case_count} cases · {job.states.error} errors</p><p className="text-xs text-stone-600">{job.states.pending} pending · {job.states.running} running · {job.states.uncertain} uncertain</p></td>
            <td className="px-4 py-3">{job.strategy_metrics
              ? <ul className="min-w-52 space-y-2 text-xs">{Object.entries(job.strategy_metrics).map(([strategy, metrics]) => <li key={strategy}>
                <p className="font-medium">{strategy}: {metrics.pass_count} / {metrics.attempted_count} independent passes</p>
                <p className="text-stone-600">Runtime {metrics.total_runtime_cost_usd === null ? 'cost incomplete' : `$${metrics.total_runtime_cost_usd}`} · median {latencyLabel(metrics.median_latency_ms)}</p>
              </li>)}</ul>
              : <p>{job.online_pass_count} / {job.case_count} online passes</p>}
              <p className="mt-2 min-w-36 text-xs text-stone-600">{job.quality_basis}</p></td>
            <td className="px-4 py-3"><p>Runtime {costLabel(job.known_cost_usd, job.known_cost_usd, job.cost_complete)}</p>
              {job.scoring_known_cost_usd !== undefined && <p className="mt-1 text-xs text-stone-600">Scoring {costLabel(job.scoring_known_cost_usd, job.scoring_known_cost_usd, job.scoring_cost_complete === true)}</p>}
              <p className="mt-1 text-xs text-stone-600">Budget used / held: ${job.budget_used_usd} / ${job.budget_usd}</p></td>
          </tr><tr><td colSpan={4} className="px-4 pb-4"><div className="sticky left-4 w-[calc(100vw-4.5rem)] max-w-[43.25rem]"><BenchmarkDetails jobId={job.job_id} /></div></td></tr></Fragment>)}</tbody>
        </table>
      </div>}
    </section>
  </div>
}
