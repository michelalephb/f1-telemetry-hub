'use client'
import { useEffect, useState } from 'react'

/** Run an async loader when deps change; returns data, error and loading. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; error: string | null; loading: boolean } {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true })
  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn().then(
      (data) => live && setState({ data, error: null, loading: false }),
      (e) => live && setState({ data: null, error: e instanceof Error ? e.message : String(e), loading: false }),
    )
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}

export function Loading({ what }: { what: string }) {
  return <p className="animate-pulse py-10 text-sm text-mute">Loading {what}…</p>
}

export function Failed({ error }: { error: string }) {
  return <p className="rounded-lg border border-loss/60 bg-loss/10 p-4 text-sm">Could not load data: {error}</p>
}
