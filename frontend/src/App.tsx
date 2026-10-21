import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

import { isChatResult, type ChatResult } from '@/api'
import { AnswerDetails } from '@/components/AnswerDetails'
import { ResultsView } from '@/components/ResultsView'

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
  const [view, setView] = useState<'chat' | 'results'>('chat')
  const [resultsVisited, setResultsVisited] = useState(false)
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
    provider.status === 'available')

  useEffect(() => {
    let active = true
    void fetchConfig().then(result => {
      if (active) setConfig(result)
    }).catch(() => {
      if (active) setConfigError('Chat is unavailable. Try reconnecting.')
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
        throw new Error('Could not send your message. Try again; a retry may incur another charge.')
      }
      const result = await response.json()
      if (!isChatResult(result)) {
        throw new Error('Could not read the reply. Try again; a retry may incur another charge.')
      }
      setMessages([...history, { role: 'assistant', content: result.answer, result }])
      setDraft('')
    } catch (cause) {
      setError(cause instanceof Error && cause.name === 'Error' ? cause.message
        : 'The request timed out. You can retry, but the previous request may have been charged.')
    } finally {
      inFlight.current = false
      setSending(false)
      composer.current?.focus()
    }
  }

  function newChat() {
    setView('chat')
    setMessages([])
    setDraft('')
    setError('')
    requestAnimationFrame(() => composer.current?.focus())
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-5 py-6">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold tracking-tight">arbiter</span>
          {config?.mode === 'mock' && <span className="rounded-full border bg-white px-3 py-1 text-xs text-stone-600">Mock mode</span>}
        </div>
        <Button variant="outline" disabled={sending} onClick={newChat}>New chat</Button>
      </header>
      <nav aria-label="Main" className="mx-auto flex max-w-3xl gap-2 px-5">
        <Button variant={view === 'chat' ? 'default' : 'outline'} aria-pressed={view === 'chat'} onClick={() => setView('chat')}>Chat</Button>
        <Button variant={view === 'results' ? 'default' : 'outline'} aria-pressed={view === 'results'} onClick={() => { setView('results'); setResultsVisited(true) }}>Runs & benchmarks</Button>
      </nav>
      <main className="mx-auto max-w-3xl px-5 pb-10 pt-6 sm:pt-12">
        <div hidden={view !== 'chat'}>
        <h1 className={messages.length === 0 ? 'py-10 text-center text-3xl font-semibold tracking-tight' : 'sr-only'}>
          {messages.length === 0 ? 'What can I help with?' : 'Conversation'}
        </h1>
        {!config && !configError && <p role="status" className="text-sm text-stone-500">Connecting…</p>}
        {configError && <div role="alert" className="mt-4 text-sm text-red-700">
          <p>{configError}</p>
          <Button className="mt-2" variant="outline" onClick={() => { setConfigError(''); setConfigRetry(configRetry + 1) }}>Reconnect</Button>
        </div>}
        {config?.mode === 'live' && !canSend && <p role="alert" className="mt-3 text-sm text-red-700">
          No models are available. Check your server settings and refresh.
        </p>}
        <section aria-label="Conversation" aria-live="polite" aria-busy={sending}
          className="my-7 space-y-4">
          {messages.map((message, index) => (
            <article key={index} className={`rounded-xl border p-5 ${message.role === 'assistant' ? 'bg-white' : 'bg-stone-100'}`}>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">
                {message.role === 'user' ? 'You' : message.result?.mode === 'mock' ? 'Arbiter · Mock' : 'Arbiter'}
              </h2>
              <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.content}</p>
              {message.result && <AnswerDetails result={message.result} />}
            </article>
          ))}
          {sending && <p role="status" className="text-sm text-stone-600">Thinking…</p>}
        </section>
        <form onSubmit={event => { event.preventDefault(); void send() }} className="rounded-xl border bg-white p-4">
          <label htmlFor="message" className="sr-only">Your message</label>
          <textarea id="message" ref={composer} value={draft} readOnly={sending} rows={3}
            onChange={event => setDraft(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                void send()
              }
            }}
            aria-describedby="composer-help" placeholder="Message Arbiter…"
            className="block w-full resize-y rounded-md border p-3 text-sm leading-6 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-700" />
          <div className="mt-3 flex items-center justify-between gap-3">
            <p id="composer-help" className="text-xs leading-5 text-stone-500">Enter to send · Shift+Enter for a new line</p>
            <Button type="submit" disabled={sending || !content || limitReached || !canSend}>{sending ? 'Sending…' : 'Send'}</Button>
          </div>
        </form>
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
        {limitReached && <p role="status" className="mt-4 text-sm text-stone-700">Conversation limit reached. Shorten your message or choose New chat.</p>}
        <p className="mt-4 text-center text-xs text-stone-500">Chat clears on browser refresh. Run records are saved.</p>
        </div>
        {resultsVisited && <div hidden={view !== 'results'}><ResultsView /></div>}
      </main>
    </div>
  )
}

export default App
