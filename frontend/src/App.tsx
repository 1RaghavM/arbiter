import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

type Message = { role: 'user' | 'assistant'; content: string; runId?: string }

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)
  const composer = useRef<HTMLTextAreaElement>(null)
  const content = draft.trim()
  const characterCount = [...messages.map(message => message.content).join(''), ...content].length
  const limitReached = messages.length >= 10 || characterCount > 12000

  async function send() {
    if (!content || inFlight.current || limitReached) return
    inFlight.current = true
    setSending(true)
    setError('')
    const history: Message[] = [...messages, { role: 'user', content }]
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history.map(({ role, content }) => ({ role, content })) }),
        signal: AbortSignal.timeout(15000),
      })
      if (!response.ok) {
        throw new Error('Could not complete this request. Check the API and database, then select Send to retry.')
      }
      const result = await response.json()
      if (typeof result.answer !== 'string' || result.mode !== 'mock') {
        throw new Error('The API returned an unexpected reply. Select Send to retry.')
      }
      setMessages([...history, { role: 'assistant', content: result.answer, runId: result.run_id }])
      setDraft('')
    } catch (cause) {
      setError(cause instanceof Error && cause.name === 'Error' ? cause.message
        : 'Could not reach the API in time. Select Send to retry; the previous run may have been saved.')
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
        <span className="rounded-full border bg-white px-3 py-1 text-xs text-stone-600">Mock mode · No paid calls</span>
      </header>
      <main className="mx-auto max-w-3xl px-5 pb-10 pt-6 sm:pt-12">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium tracking-widest text-stone-500">PHASE 01 / CHAT</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight">A conversation, with context.</h1>
          </div>
          <Button variant="outline" disabled={sending} onClick={newChat}>New chat</Button>
        </div>
        <p className="mt-4 text-sm leading-6 text-stone-600">
          Try a message, then a follow-up. These deterministic replies echo your context;
          no AI model or quality evaluator is connected.
        </p>
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
                {message.role === 'user' ? 'You' : 'Arbiter · Mock reply'}
              </h2>
              <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.content}</p>
              {message.runId && <p className="mt-3 text-xs text-stone-500">Unverified · Saved mock run · No API charge</p>}
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
            <Button type="submit" disabled={sending || !content || limitReached}>{sending ? 'Sending…' : 'Send'}</Button>
          </div>
        </form>
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
        {limitReached && <p role="status" className="mt-4 text-sm text-stone-700">Conversation limit reached. Shorten your message or choose New chat.</p>}
        <p className="mt-5 text-xs leading-5 text-stone-500">Refresh or New chat clears this conversation. Saved mock runs remain in PostgreSQL.</p>
      </main>
    </div>
  )
}

export default App
