'use client'

import { useState } from 'react'

/** Share the current view: the phone's share sheet where there is one, else copy the link. */
export default function ShareButton({ title, url, className = '' }: { title: string; url?: () => string; className?: string }) {
  const [msg, setMsg] = useState<string | null>(null)
  const go = async () => {
    const link = url ? url() : window.location.href
    try {
      if (navigator.share) { await navigator.share({ title, url: link }); return }
      await navigator.clipboard.writeText(link)
      setMsg('Link copied')
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      setMsg(link)  // last resort: show it so it can be copied by hand
    }
    setTimeout(() => setMsg(null), 4000)
  }
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <button type="button" onClick={go}
        className="flex min-h-11 items-center gap-2 rounded-lg border border-line px-4 text-sm text-ink hover:border-cyan/60">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7" /><path d="M16 6l-4-4-4 4" /><path d="M12 2v14" />
        </svg>
        Share
      </button>
      {msg && <span role="status" className="max-w-[260px] truncate text-xs text-mute">{msg}</span>}
    </span>
  )
}
