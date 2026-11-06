import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { RunDetails } from '@/components/RunDetails'
import { fetchBenchmark, type BenchmarkDetail } from '@/api'

export function BenchmarkDetails({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<BenchmarkDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      setJob(await fetchBenchmark(jobId))
    } catch {
      setError('Could not load benchmark details.')
    } finally {
      setLoading(false)
    }
  }

  return <details className="text-sm [overflow-wrap:anywhere]" onToggle={event => {
    if (event.target === event.currentTarget && event.currentTarget.open && !job && !loading && !error) void load()
  }}>
    <summary className="w-fit cursor-pointer rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-700">Benchmark details</summary>
    <p className="mt-2 break-all text-xs text-stone-500">Job: {jobId}</p>
    {loading && <p role="status" className="mt-3">Loading benchmark details…</p>}
    {error && <div role="alert" className="mt-3 text-red-700">{error} <Button variant="outline" onClick={() => void load()}>Retry benchmark details</Button></div>}
    {job && <div className="mt-4 space-y-3">
      <p className="break-all text-xs">Dataset: {job.dataset_hash}</p>
      <p className="break-all text-xs">History snapshot: {job.history_snapshot_id ?? 'None'}</p>
      <h3 className="font-medium">Cases</h3>
      {job.cases.length === 0 && <p>No cases recorded.</p>}
      <ul className="space-y-3">{job.cases.map(item => <li key={item.ordinal} className="rounded-md border p-3">
        <p className="mb-2 text-xs leading-5">{item.case_id} · {item.strategy} · {item.stage} · {item.state} · {item.attempts} attempts</p>
        {item.run_id ? <RunDetails runId={item.run_id} /> : <p className="text-xs text-stone-500">No run recorded.</p>}
      </li>)}</ul>
    </div>}
  </details>
}
