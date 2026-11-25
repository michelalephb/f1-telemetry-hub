'use client'

import { useEffect, useState } from 'react'

const pad = (n: number) => String(n).padStart(2, '0')

/** Live countdown to `to` (ISO time). Renders nothing once that moment has passed. */
export default function Countdown({ to, label, onDone }: { to: string; label: string; onDone?: () => void }) {
  const target = Date.parse(to)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const left = Math.floor((target - now) / 1000)
  useEffect(() => {
    if (left <= 0) onDone?.()
  }, [left <= 0]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!Number.isFinite(target) || left <= 0) return null
  const d = Math.floor(left / 86400), h = Math.floor((left % 86400) / 3600), m = Math.floor((left % 3600) / 60), s = left % 60
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 text-xs text-mute" aria-live="off">
      <span>{label}</span>
      <span className="font-mono text-base font-bold tabular-nums text-cyan">
        {d > 0 && `${d}d `}{pad(h)}h {pad(m)}m {pad(s)}s
      </span>
    </p>
  )
}
