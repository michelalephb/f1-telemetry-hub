'use client'

import { useState } from 'react'
import { sendFeedback } from '@/lib/api'

/** Footer button that opens a short form; the message is stored for the site owner (never shown publicly). */
export default function BugReport() {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [contact, setContact] = useState('')
  const [trap, setTrap] = useState('')           // hidden field: bots fill it, people do not
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [err, setErr] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (trap) { setState('sent'); return }
    if (message.trim().length < 5) { setErr('Please describe the problem in a few words.'); setState('error'); return }
    setState('sending')
    try {
      await sendFeedback(message.trim().slice(0, 2000), contact.trim().slice(0, 200), window.location.href.slice(0, 500))
      setState('sent'); setMessage(''); setContact('')
    } catch (x) {
      setErr(x instanceof Error ? x.message : 'Could not send'); setState('error')
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => { setOpen(true); setState('idle') }}
        className="flex min-h-11 items-center gap-2 rounded-lg border border-line px-4 text-sm text-ink hover:border-ink/60">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
        </svg>
        Report a bug
      </button>
    )
  }
  return (
    <form onSubmit={submit} className="flex w-full max-w-xl flex-col gap-3 rounded-xl border border-line bg-card p-4 text-sm text-ink">
      <div className="flex items-center justify-between">
        <h2 className="font-head text-base font-bold">Report a bug</h2>
        <button type="button" onClick={() => setOpen(false)} className="flex min-h-11 items-center px-2 text-mute hover:text-ink">Close</button>
      </div>
      {state === 'sent' ? (
        <p role="status">Thank you. Your report was sent.</p>
      ) : (
        <>
          <label className="flex flex-col gap-1">
            <span className="text-mute">What went wrong? The page address is included automatically.</span>
            <textarea required minLength={5} maxLength={2000} rows={4} value={message} onChange={(e) => setMessage(e.target.value)}
              className="rounded-lg border border-line bg-bg p-3 text-base text-ink" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-mute">Your email (optional, only if you want a reply)</span>
            <input type="email" maxLength={200} value={contact} onChange={(e) => setContact(e.target.value)} autoComplete="email"
              className="min-h-11 rounded-lg border border-line bg-bg px-3 text-base text-ink" />
          </label>
          <input type="text" tabIndex={-1} autoComplete="off" value={trap} onChange={(e) => setTrap(e.target.value)} aria-hidden="true" className="hidden" />
          {state === 'error' && <p role="alert" className="text-loss">{err}</p>}
          <button type="submit" disabled={state === 'sending'}
            className="flex min-h-11 items-center justify-center rounded-lg bg-ink px-4 font-semibold text-bg disabled:opacity-60">
            {state === 'sending' ? 'Sending…' : 'Send report'}
          </button>
        </>
      )}
    </form>
  )
}
