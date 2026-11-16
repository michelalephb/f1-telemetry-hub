'use client'

import { useMemo, useState } from 'react'
import { lapTime, TYRE } from '@/lib/format'

type D = { num: string; code: string; color: string }
type L = { d: string; n: number; ms: number; c: string | null }

const W = 900, H = 320, PL = 64, PR = 16, PT = 12, PB = 32

/** Every clean lap: lap time by lap number, coloured by driver (second teammate drawn hollow). */
export default function PaceChart({ drivers, laps }: { drivers: D[]; laps: L[] }) {
  const [on, setOn] = useState<Set<string>>(() => new Set(drivers.slice(0, 3).map((d) => d.num)))
  const [hover, setHover] = useState<L | null>(null)
  const color = useMemo(() => new Map(drivers.map((d) => [d.num, d.color])), [drivers])
  const code = useMemo(() => new Map(drivers.map((d) => [d.num, d.code])), [drivers])
  // Teammates share a team colour: the second one in the list is drawn hollow so both read apart.
  const hollow = useMemo(() => {
    const seen = new Set<string>(), out = new Set<string>()
    for (const d of drivers) { const c = d.color.toLowerCase(); if (seen.has(c)) out.add(d.num); else seen.add(c) }
    return out
  }, [drivers])
  const shown = laps.filter((l) => on.has(l.d))
  if (!laps.length) return null

  const nMax = Math.max(...laps.map((l) => l.n))
  const yMin = Math.min(...laps.map((l) => l.ms)), yMax = Math.max(...laps.map((l) => l.ms))
  const x = (n: number) => PL + ((n - 1) / Math.max(1, nMax - 1)) * (W - PL - PR)
  const y = (ms: number) => PT + (1 - (ms - yMin) / Math.max(1, yMax - yMin)) * (H - PT - PB)
  const step = (yMax - yMin) / 4
  const toggle = (num: string) => setOn((s) => {
    const n = new Set(s)
    if (n.has(num)) n.delete(num); else n.add(num)
    return n
  })

  // degradation trend per driver per stint: least squares slope over consecutive laps on one compound
  const trends = [...on].flatMap((num) => {
    const ls = shown.filter((l) => l.d === num).sort((a, b) => a.n - b.n)
    const stints: L[][] = []
    for (const l of ls) {
      const cur = stints[stints.length - 1]
      if (cur && cur[cur.length - 1].c === l.c && l.n - cur[cur.length - 1].n <= 2) cur.push(l)
      else stints.push([l])
    }
    return stints.filter((s) => s.length >= 5).map((s) => {
      const mx = s.reduce((a, l) => a + l.n, 0) / s.length, my = s.reduce((a, l) => a + l.ms, 0) / s.length
      const k = s.reduce((a, l) => a + (l.n - mx) * (l.ms - my), 0) / s.reduce((a, l) => a + (l.n - mx) ** 2, 0)
      const n0 = s[0].n, n1 = s[s.length - 1].n
      return { num, n0, n1, y0: my + k * (n0 - mx), y1: my + k * (n1 - mx), k }
    })
  })

  return (
    <section className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-head text-lg font-bold">Pace and tyre degradation</h2>
        <p className="text-xs text-mute">Clean laps within 107 % of the fastest, in each driver's colour (teammate hollow). Lines: trend per stint, in s per lap.</p>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {drivers.map((d) => (
          <button key={d.num} type="button" aria-pressed={on.has(d.num)} onClick={() => toggle(d.num)}
            className="min-h-11 rounded-full border px-3 text-sm"
            style={on.has(d.num) ? { borderColor: d.color, color: '#fff', background: `${d.color}33` } : { borderColor: '#232D3F', color: '#93A0B4' }}>
            {d.code}
          </button>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 h-auto w-full" role="img" aria-label="Lap time by lap">
        {[0, 1, 2, 3, 4].map((i) => {
          const v = yMin + i * step
          return (
            <g key={i}>
              <line x1={PL} x2={W - PR} y1={y(v)} y2={y(v)} stroke="#232D3F" />
              <text x={PL - 8} y={y(v) + 4} fill="#93A0B4" fontSize="11" textAnchor="end" fontFamily="JetBrains Mono">{lapTime(v)}</text>
            </g>
          )
        })}
        {Array.from({ length: 6 }, (_, i) => Math.max(1, Math.round(1 + (i * (nMax - 1)) / 5))).map((n) => (
          <text key={n} x={x(n)} y={H - 10} fill="#93A0B4" fontSize="11" textAnchor="middle" fontFamily="JetBrains Mono">L{n}</text>
        ))}
        {trends.map((t, i) => (
          <g key={i}>
            <line x1={x(t.n0)} x2={x(t.n1)} y1={y(t.y0)} y2={y(t.y1)} stroke={color.get(t.num)} strokeWidth="2" strokeDasharray="5 4" />
            <text x={x(t.n1) + 4} y={y(t.y1) - 4} fill={color.get(t.num)} fontSize="10" fontFamily="JetBrains Mono">{(t.k / 1000 >= 0 ? '+' : '') + (t.k / 1000).toFixed(3)}</text>
          </g>
        ))}
        {shown.map((l) => (
          <circle key={`${l.d}-${l.n}`} cx={x(l.n)} cy={y(l.ms)} r="4.5" fill={hollow.has(l.d) ? '#141923' : color.get(l.d)} fillOpacity="0.9"
            stroke={color.get(l.d)} strokeWidth="2" onMouseEnter={() => setHover(l)} onMouseLeave={() => setHover(null)} />
        ))}
      </svg>
      <div className="num h-5 text-sm text-mute">
        {hover ? `${code.get(hover.d)} · L${hover.n} · ${lapTime(hover.ms)} · ${TYRE[hover.c ?? '']?.label ? `${hover.c?.toLowerCase()} tyre` : 'tyre unknown'}` : 'Hover a dot for the lap and tyre'}
      </div>
    </section>
  )
}
