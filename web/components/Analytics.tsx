'use client'

import { useEffect, useState } from 'react'
import { consent, setConsent, start, track } from '@/lib/analytics'

/** Consent banner plus Analytics start. Nothing is loaded from Google until the visitor accepts. */
export default function Analytics() {
  const [ask, setAsk] = useState(false)
  useEffect(() => {
    const c = consent()
    if (c === 'yes') start()
    else if (c === null) setAsk(true)
    // outbound Instagram clicks, wherever the link is
    const onClick = (e: MouseEvent) => {
      const a = (e.target as HTMLElement | null)?.closest?.('a[href*="instagram.com"]')
      if (a) track('instagram_click', { page: window.location.pathname })
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])
  if (!ask) return null
  const answer = (v: 'yes' | 'no') => { setConsent(v); setAsk(false) }
  return (
    <div role="dialog" aria-label="Analytics consent"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-line bg-card/95 px-4 py-3 backdrop-blur sm:px-6">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 text-sm text-ink">
        <p className="min-w-0 flex-1 basis-64">
          We use Google Analytics cookies to count visits and see which features get used. No ads, nothing sold.
        </p>
        <div className="flex gap-2">
          <button type="button" onClick={() => answer('no')} className="min-h-11 rounded-lg border border-line px-4 text-ink hover:border-ink/60">Decline</button>
          <button type="button" onClick={() => answer('yes')} className="min-h-11 rounded-lg bg-ink px-4 font-semibold text-bg">Accept</button>
        </div>
      </div>
    </div>
  )
}
