import { useState } from 'react'
import { Button } from '@/components/ui/button'

function App() {
  const [status, setStatus] = useState('Ready to check the API connection.')
  const [checking, setChecking] = useState(false)

  async function checkHealth() {
    setChecking(true)
    setStatus('Checking connection…')
    try {
      const response = await fetch('/api/health', { signal: AbortSignal.timeout(5000) })
      if (!response.ok) throw new Error('Health check failed')
      const result = await response.json()
      if (result.status !== 'ok') throw new Error('Unexpected health response')
      setStatus('API connected. The foundation is ready.')
    } catch {
      setStatus('Could not reach the API. Check that the backend is running and try again.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="mx-auto flex max-w-4xl items-center justify-between px-6 py-8">
        <span className="text-lg font-semibold tracking-tight">arbiter</span>
        <span className="text-xs tracking-wide text-stone-500">A MODEL ROUTING EXPERIMENT</span>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-12 sm:py-24">
        <p className="mb-5 text-xs font-medium tracking-[0.2em] text-stone-500">PHASE 00 / FOUNDATION</p>
        <h1 className="max-w-xl text-4xl leading-tight font-semibold tracking-tight sm:text-6xl">
          The right model.<br />A measured choice.
        </h1>
        <p className="mt-6 max-w-lg text-lg leading-relaxed text-stone-600">
          Exploring the balance between response quality, cost, and speed across cloud AI models.
        </p>
        <section aria-labelledby="connection-title" className="mt-12 max-w-xl rounded-xl border bg-white p-6">
          <h2 id="connection-title" className="font-semibold">Start with a connection</h2>
          <p role="status" className="mt-2 min-h-12 text-sm leading-6 text-stone-600">{status}</p>
          <Button className="mt-4" size="lg" disabled={checking} onClick={checkHealth}>
            {checking ? 'Checking…' : 'Check connection'}
          </Button>
        </section>
        <p className="mt-6 text-xs text-stone-500">This check contacts only the local API. No model requests are sent.</p>
      </main>
    </div>
  )
}

export default App
