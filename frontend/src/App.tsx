import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

type ChatResult = {
  answer: string
  mode: 'mock' | 'live'
  final_model: string
  total_cost_usd: string | null
  cost_complete: boolean
  status: 'unverified'
  warnings: string[]
}
type Message = { role: 'user' | 'assistant'; content: string; result?: ChatResult }
type Config = {
  mode: 'mock' | 'live'
  model_key: string | null
  providers: { key: string; provider: string; model_id: string | null; status: 'available' | 'disabled' | 'missing_credentials' }[]
}

async function fetchConfig(): Promise<Config> {
  const response = await fetch('/api/config', { signal: AbortSignal.timeout(10000) })
  if (!response.ok) throw new Error('Configuration unavailable')
  const result = await response.json()
  if (!['mock', 'live'].includes(result.mode)
    || !(result.model_key === null || typeof result.model_key === 'string')
    || !Array.isArray(result.providers)
    || !result.providers.every((provider: Config['providers'][number]) => provider
      && typeof provider.key === 'string' && typeof provider.provider === 'string'
      && (provider.model_id === null || typeof provider.model_id === 'string')
      && ['available', 'disabled', 'missing_credentials'].includes(provider.status))) {
    throw new Error('Unexpected configuration')
  }
  return result
}

function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const [configError, setConfigError] = useState('')
  const [configRetry, setConfigRetry] = useState(0)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)
  const composer = useRef<HTMLTextAreaElement>(null)
  const content = draft.trim()
  const characterCount = [...messages.map(message => message.content).join(''), ...content].length
  const limitReached = messages.length >= 10 || characterCount > 12000
  const canSend = config?.mode === 'mock' || config?.providers.some(provider =>
    provider.key === config.model_key && provider.status === 'available')

  useEffect(() => {
    let active = true
    void fetchConfig().then(result => {
      if (active) setConfig(result)
    }).catch(() => {
      if (active) setConfigError('Could not check the server configuration. Retry before sending a message.')
    })
    return () => { active = false }
  }, [configRetry])

  async function send() {
    if (!content || inFlight.current || limitReached || !canSend) return
    inFlight.current = true
    setSending(true)
    setError('')
    const history: Message[] = [...messages, { role: 'user', content }]
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history.map(({ role, content }) => ({ role, content })) }),
        signal: AbortSignal.timeout(95000),
      })
      if (!response.ok) {
        throw new Error('Could not complete this request. Check the API, database, and provider configuration, then select Send to retry. A retry may incur another charge.')
      }
      const result = await response.json()
      if (typeof result.answer !== 'string' || !['mock', 'live'].includes(result.mode)
        || typeof result.final_model !== 'string' || result.status !== 'unverified'
        || typeof result.cost_complete !== 'boolean'
        || !(result.total_cost_usd === null || (typeof result.total_cost_usd === 'string'
          && /^\d+(\.\d+)?([eE][+-]?\d+)?$/.test(result.total_cost_usd)))
        || !Array.isArray(result.warnings)
        || !result.warnings.every((warning: unknown) => typeof warning === 'string')) {
        throw new Error('The API returned an unexpected reply. Select Send to retry.')
      }
      setMessages([...history, { role: 'assistant', content: result.answer, result }])
      setDraft('')
    } catch (cause) {
      setError(cause instanceof Error && cause.name === 'Error' ? cause.message
        : 'Could not reach the API in time. Select Send to retry; the previous run may have been saved and charged.')
    } finally {
      inFlight.current = false
      setSending(false)
      composer.current?.focus()
    }
  }

  function newChat() {
    setMessages([])
    setDraft('')
    setError('')
    composer.current?.focus()
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-5 py-6">
        <span className="text-lg font-semibold tracking-tight">arbiter</span>
        <span className="rounded-full border bg-white px-3 py-1 text-xs text-stone-600">
          {config ? (config.mode === 'mock' ? 'Mock mode · No paid calls' : 'Live mode · Paid calls')
            : configError ? 'Configuration unavailable' : 'Checking configuration…'}</span>
      </header>
      <main className="mx-auto max-w-3xl px-5 pb-10 pt-6 sm:pt-12">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium tracking-widest text-stone-500">PHASE 02 / CHAT</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight">A conversation, with context.</h1>
          </div>
          <Button variant="outline" disabled={sending} onClick={newChat}>New chat</Button>
        </div>
        <p className="mt-4 text-sm leading-6 text-stone-600">
          {config?.mode === 'mock'
            ? 'Try a message, then a follow-up. Deterministic mock replies echo your context; no AI model is called.'
            : config?.mode === 'live'
              ? `Messages use the server’s fixed model: ${config.model_key ?? 'not configured'}. Replies have not been quality evaluated.`
              : 'Checking which mode and model the server is configured to use.'}
        </p>
        {configError && <div role="alert" className="mt-4 text-sm text-red-700">
          <p>{configError}</p>
          <Button className="mt-2" variant="outline" onClick={() => { setConfigError(''); setConfigRetry(configRetry + 1) }}>Retry configuration</Button>
        </div>}
        {config?.mode === 'live' && <p className="mt-3 text-xs leading-5 text-stone-500">
          {config.providers.map(provider => `${provider.provider}: ${provider.status.replace('_', ' ')}`).join(' · ')}
          {!canSend && ' · The fixed model is unavailable. Update the server configuration and refresh.'}
        </p>}
        <section aria-label="Conversation" aria-live="polite" aria-busy={sending}
          className="my-7 space-y-4">
          {messages.length === 0 && (
            <div className="rounded-xl border border-dashed p-6 text-sm leading-6 text-stone-500">
              Start with “My project is called Arbiter.” Then ask “What did I call my project?”
            </div>
          )}
          {messages.map((message, index) => (
            <article key={index} className={`rounded-xl border p-5 ${message.role === 'assistant' ? 'bg-white' : 'bg-stone-100'}`}>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">
                {message.role === 'user' ? 'You' : `Arbiter · ${message.result?.mode === 'mock' ? 'Mock' : 'Live'} reply`}
              </h2>
              <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.content}</p>
              {message.result && <div className="mt-3 text-xs leading-5 text-stone-500">
                <p>Unverified · {message.result.final_model} · {message.result.mode === 'mock'
                  ? 'No API charge'
                  : message.result.cost_complete && message.result.total_cost_usd !== null
                    ? `Estimated cost: $${message.result.total_cost_usd}`
                    : 'Cost unknown or incomplete'}</p>
                {message.result.warnings.map((warning, warningIndex) => <p key={warningIndex}>{warning}</p>)}
              </div>}
            </article>
          ))}
          {sending && <p role="status" className="break-words text-sm text-stone-600">Sending: {content}</p>}
        </section>
        <form onSubmit={event => { event.preventDefault(); void send() }} className="rounded-xl border bg-white p-4">
          <label htmlFor="message" className="text-sm font-medium">Your message</label>
          <textarea id="message" ref={composer} value={draft} readOnly={sending} rows={3}
            onChange={event => setDraft(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                void send()
              }
            }}
            aria-describedby="composer-help" placeholder="Write a message…"
            className="mt-2 block w-full resize-y rounded-md border p-3 text-sm leading-6 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-700" />
          <div className="mt-3 flex items-center justify-between gap-3">
            <p id="composer-help" className="text-xs leading-5 text-stone-500">Enter to send · Shift+Enter for a new line<br />{characterCount.toLocaleString()} / 12,000 characters</p>
            <Button type="submit" disabled={sending || !content || limitReached || !canSend}>{sending ? 'Sending…' : 'Send'}</Button>
          </div>
        </form>
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
        {limitReached && <p role="status" className="mt-4 text-sm text-stone-700">Conversation limit reached. Shorten your message or choose New chat.</p>}
        <p className="mt-5 text-xs leading-5 text-stone-500">Refresh or New chat clears this conversation. Saved runs remain in PostgreSQL. {config?.mode === 'live' && 'Each Send or retry creates a new request and may incur a charge.'}</p>
      </main>
    </div>
  )
}

export default App
