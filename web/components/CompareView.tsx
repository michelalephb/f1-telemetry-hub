'use client'

import { useRouter } from 'next/navigation'
import { useMemo, useRef, useState } from 'react'
import type { CornerMetric } from '@/lib/api'
import { TYRE } from '@/lib/format'
import { bisect, interp, type LapTrace } from '@/lib/telemetry'

export type Series = {
  num: string; code: string; team: string; color: string; lap: number; lapTime: string; compound: string | null
  trace: LapTrace; metrics: CornerMetric[]
}
type CornerPt = { corner: string; apex_m: number; x: number | null; y: number | null }
type Opt = { num: string; code: string; laps: { n: number; t: string }[] }

const W = 960, PL = 52, PR = 12
const WIN_BEFORE = 250, WIN_AFTER = 150

export default function CompareView({ sid, a, b, delta, corners, options, initialCorner, trackM }: {
  sid: string; a: Series; b: Series; delta: number[]; corners: CornerPt[]; options: Opt[]; initialCorner: string | null; trackM: number
}) {
  const router = useRouter()
  const [corner, setCorner] = useState<string | null>(initialCorner && corners.some((c) => c.corner === initialCorner) ? initialCorner : null)
  const [hoverD, setHoverD] = useState<number | null>(null)
  const sel = corners.find((c) => c.corner === corner) ?? null
  const range: [number, number] = sel ? [sel.apex_m - WIN_BEFORE, sel.apex_m + WIN_AFTER] : [0, trackM]

  const go = (p: Record<string, string | number>) => {
    const q = new URLSearchParams({ id: sid, a: a.num, b: b.num, la: String(a.lap), lb: String(b.lap), ...(corner ? { c: corner } : {}) })
    for (const [k, v] of Object.entries(p)) q.set(k, String(v))
    if ('a' in p) q.delete('la')
    if ('b' in p) q.delete('lb')
    router.push(`/compare/?${q.toString()}`)
  }
  const pickCorner = (c: string | null) => {
    setCorner(c)
    const q = new URLSearchParams(window.location.search)
    if (c) q.set('c', c); else q.delete('c')
    window.history.replaceState(null, '', `?${q.toString()}`)
  }

  const final = delta.length ? delta[delta.length - 1] : 0
  const ahead = final > 0 ? a : b

  return (
    <div className="flex flex-col gap-4">
      {/* pickers */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {[a, b].map((s, i) => (
          <div key={i} className="rounded-xl border bg-card p-3" style={{ borderColor: s.color }}>
            <div className="text-xs uppercase tracking-widest" style={{ color: s.color }}>Driver {i ? 'B' : 'A'}</div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <label className="sr-only" htmlFor={`d${i}`}>Driver {i ? 'B' : 'A'}</label>
              <select id={`d${i}`} value={s.num} onChange={(e) => go(i ? { b: e.target.value } : { a: e.target.value })}
                className="min-h-11 rounded-lg border border-line bg-bg px-2 font-head text-xl font-bold">
                {options.filter((o) => o.num !== (i ? a.num : b.num)).map((o) => <option key={o.num} value={o.num}>{o.code}</option>)}
              </select>
              <label className="sr-only" htmlFor={`l${i}`}>Lap</label>
              <select id={`l${i}`} value={s.lap} onChange={(e) => go(i ? { lb: e.target.value } : { la: e.target.value })}
                className="num min-h-11 rounded-lg border border-line bg-bg px-2 text-sm">
                {(options.find((o) => o.num === s.num)?.laps ?? []).map((l) => <option key={l.n} value={l.n}>L{l.n} · {l.t}</option>)}
              </select>
              <span className="num text-sm text-mute">{s.team}</span>
              {s.compound && <span className="text-xs font-bold" style={{ color: TYRE[s.compound]?.color }}>{s.compound}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* verdict */}
      <div className="rounded-xl border border-line bg-card px-4 py-3 text-sm">
        <span className="font-semibold" style={{ color: ahead.color }}>{ahead.code}</span> is{' '}
        <span className="num font-semibold">{Math.abs(final).toFixed(3)} s</span> faster over the lap ({a.code} {a.lapTime} vs {b.code} {b.lapTime}).
        {sel && <CornerVerdict a={a} b={b} corner={sel.corner} />}
      </div>

      {/* corner chips */}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Zoom to corner">
        <Chip on={!sel} onClick={() => pickCorner(null)}>Full lap</Chip>
        {corners.map((c) => <Chip key={c.corner} on={c.corner === corner} onClick={() => pickCorner(c.corner)}>T{c.corner}</Chip>)}
      </div>

      <div className="flex flex-wrap gap-4">
        {/* map */}
        <section className="min-w-0 flex-[1_1_320px] rounded-xl border border-line bg-card p-3">
          <TrackMap a={a} b={b} corners={corners} range={range} hoverD={hoverD} selected={sel?.corner ?? null} />
          {sel && <CornerCards a={a} b={b} corner={sel.corner} />}
        </section>

        {/* traces */}
        <section className="min-w-0 flex-[999_1_560px] rounded-xl border border-line bg-card p-3">
          <Traces a={a} b={b} delta={delta} corners={corners} range={range} hoverD={hoverD} setHoverD={setHoverD} />
        </section>
      </div>
      <p className="text-xs text-mute">
        One point per raw car sample (about every 240 ms, so roughly 20 m apart at 300 km/h). Delta above zero means {b.code} is behind {a.code} at that point.
        Corner windows run from 250 m before to 150 m after the apex.
      </p>
    </div>
  )
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={`num min-h-11 min-w-11 rounded-lg border px-3 text-sm ${on ? 'border-ink bg-ink font-bold text-bg' : 'border-line text-ink/80 hover:border-mute'}`}>
      {children}
    </button>
  )
}

function CornerVerdict({ a, b, corner }: { a: Series; b: Series; corner: string }) {
  const ma = a.metrics.find((m) => m.corner === corner), mb = b.metrics.find((m) => m.corner === corner)
  if (!ma?.window_time_s || !mb?.window_time_s) return null
  const d = mb.window_time_s - ma.window_time_s
  const w = d > 0 ? a : b
  const dv = (ma.min_speed_kph ?? 0) - (mb.min_speed_kph ?? 0)
  return (
    <span>
      {' '}Through T{corner}: <span className="font-semibold" style={{ color: w.color }}>{w.code}</span> gains{' '}
      <span className="num font-semibold">{Math.abs(d).toFixed(3)} s</span>
      {Math.abs(dv) >= 1 && <>, with <span className="num">{Math.abs(dv).toFixed(0)} km/h</span> more minimum speed for {dv > 0 ? a.code : b.code}</>}.
    </span>
  )
}

function CornerCards({ a, b, corner }: { a: Series; b: Series; corner: string }) {
  const ma = a.metrics.find((m) => m.corner === corner), mb = b.metrics.find((m) => m.corner === corner)
  const f = (v: number | null | undefined, unit: string, dp = 0, sign = false) =>
    v == null ? '—' : `${sign && v > 0 ? '+' : ''}${v.toFixed(dp)}${unit}`
  const rows: [string, string, string][] = [
    ['Brake point', f(ma?.brake_point_m, ' m', 0, true), f(mb?.brake_point_m, ' m', 0, true)],
    ['Entry speed', f(ma?.entry_speed_kph, ''), f(mb?.entry_speed_kph, '')],
    ['Min speed', f(ma?.min_speed_kph, ''), f(mb?.min_speed_kph, '')],
    ['Min speed at', f(ma?.min_speed_at_m, ' m', 0, true), f(mb?.min_speed_at_m, ' m', 0, true)],
    ['Exit (+100 m)', f(ma?.exit_speed_kph, ''), f(mb?.exit_speed_kph, '')],
    ['Window time', f(ma?.window_time_s, ' s', 3), f(mb?.window_time_s, ' s', 3)],
  ]
  return (
    <table className="mt-3 w-full text-sm">
      <thead>
        <tr className="text-left text-xs uppercase tracking-wider text-mute">
          <th className="py-1 font-medium">T{corner}</th>
          <th className="py-1 font-medium" style={{ color: a.color }}>{a.code}</th>
          <th className="py-1 font-medium" style={{ color: b.color }}>{b.code}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([k, va, vb]) => (
          <tr key={k} className="border-t border-line/60">
            <td className="py-1.5 text-mute">{k}</td>
            <td className="num py-1.5">{va}</td>
            <td className="num py-1.5">{vb}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ---------------------------------------------------------------- track map

function TrackMap({ a, b, corners, range, hoverD, selected }: {
  a: Series; b: Series; corners: CornerPt[]; range: [number, number]; hoverD: number | null; selected: string | null
}) {
  const t = a.trace
  const box = useMemo(() => {
    const xs = t.x.filter(Number.isFinite), ys = t.y.filter(Number.isFinite)
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys)
    const pad = 0.06 * Math.max(x1 - x0, y1 - y0)
    return { x0: x0 - pad, y0: y0 - pad, w: x1 - x0 + 2 * pad, h: y1 - y0 + 2 * pad }
  }, [t])
  if (!t.x.length) return <p className="text-sm text-mute">No position data for this lap.</p>
  const P = (x: number, y: number) => `${(x - box.x0).toFixed(0)},${(box.h - (y - box.y0)).toFixed(0)}`
  const path = t.x.map((x, i) => P(x, t.y[i])).join(' ')
  const win = t.x.map((x, i) => [x, t.y[i], t.dist[i]] as const).filter(([, , d]) => d >= range[0] && d <= range[1]).map(([x, y]) => P(x, y)).join(' ')
  const sw = box.w / 70
  const dot = (s: Series) => {
    if (hoverD == null || !s.trace.dist.length) return null
    const x = interp(hoverD, s.trace.dist, s.trace.x), y = interp(hoverD, s.trace.dist, s.trace.y)
    return <circle cx={x - box.x0} cy={box.h - (y - box.y0)} r={sw * 0.9} fill={s.color} stroke="#0B0E14" strokeWidth={sw / 4} />
  }
  return (
    <svg viewBox={`0 0 ${box.w.toFixed(0)} ${box.h.toFixed(0)}`} className="h-auto w-full" role="img" aria-label="Track map">
      <polyline points={path} fill="none" stroke="#2A3445" strokeWidth={sw} strokeLinejoin="round" strokeLinecap="round" />
      {range[1] - range[0] < 2000 && <polyline points={win} fill="none" stroke="#00E5FF" strokeWidth={sw} strokeLinecap="round" strokeOpacity="0.8" />}
      {corners.filter((c) => c.x != null && c.y != null).map((c) => (
        <text key={c.corner} x={(c.x as number) - box.x0} y={box.h - ((c.y as number) - box.y0)} dy={-sw * 1.3}
          fill={c.corner === selected ? '#FFFFFF' : '#93A0B4'} fontSize={sw * (c.corner === selected ? 2.2 : 1.6)}
          fontWeight={c.corner === selected ? 700 : 400} textAnchor="middle" fontFamily="JetBrains Mono">{c.corner}</text>
      ))}
      {dot(b)}{dot(a)}
    </svg>
  )
}

// ---------------------------------------------------------------- stacked traces

type Panel = { key: string; label: string; h: number; lo: number; hi: number; step?: boolean; get: (s: Series) => number[]; ticks: number[] }

function Traces({ a, b, delta, corners, range, hoverD, setHoverD }: {
  a: Series; b: Series; delta: number[]; corners: CornerPt[]; range: [number, number]; hoverD: number | null; setHoverD: (d: number | null) => void
}) {
  const ref = useRef<SVGSVGElement>(null)
  const [x0, x1] = range
  const X = (d: number) => PL + ((d - x0) / (x1 - x0 || 1)) * (W - PL - PR)
  const inR = (d: number) => d >= x0 - 30 && d <= x1 + 30

  const dMax = Math.max(0.05, ...delta.filter((_, i) => inR(a.trace.dist[i])).map(Math.abs)) * 1.15
  const vis = (s: Series) => s.trace.speed.filter((_, i) => inR(s.trace.dist[i]))
  const sMin = Math.max(0, Math.min(...vis(a), ...vis(b)) - 15), sMax = Math.max(...vis(a), ...vis(b)) + 10
  const panels: Panel[] = [
    { key: 'delta', label: `Delta s`, h: 90, lo: -dMax, hi: dMax, get: () => [], ticks: [-dMax / 1.15, 0, dMax / 1.15] },
    { key: 'speed', label: 'Speed km/h', h: 210, lo: sMin, hi: sMax, get: (s) => s.trace.speed, ticks: niceTicks(sMin, sMax) },
    { key: 'throttle', label: 'Throttle %', h: 70, lo: 0, hi: 100, get: (s) => s.trace.throttle, ticks: [0, 100] },
    { key: 'brake', label: 'Brake', h: 44, lo: 0, hi: 1, step: true, get: (s) => s.trace.brake, ticks: [] },
    { key: 'gear', label: 'Gear', h: 70, lo: 1, hi: 8, step: true, get: (s) => s.trace.gear, ticks: [2, 4, 6, 8] },
  ]
  const GAP = 14
  const tops: number[] = []
  let acc = 0
  for (const p of panels) { tops.push(acc); acc += p.h + GAP }
  const H = acc + 20

  const line = (s: Series, p: Panel, top: number) => {
    const ys = p.get(s), ds = s.trace.dist
    const Y = (v: number) => top + 4 + (1 - (v - p.lo) / (p.hi - p.lo || 1)) * (p.h - 8)
    let d = ''
    for (let i = 0; i < ds.length; i++) {
      if (!inR(ds[i])) continue
      const x = X(ds[i]).toFixed(1), y = Y(ys[i]).toFixed(1)
      if (!d) d = `M${x} ${y}`
      else if (p.step) d += ` H${x} V${y}`
      else d += ` L${x} ${y}`
    }
    return <path d={d} fill="none" stroke={s.color} strokeWidth={p.key === 'speed' ? 2.2 : 1.8} strokeLinejoin="round" />
  }
  const deltaPath = (top: number, p: Panel) => {
    const Y = (v: number) => top + 4 + (1 - (v - p.lo) / (p.hi - p.lo)) * (p.h - 8)
    let d = ''
    a.trace.dist.forEach((dd, i) => {
      if (!inR(dd)) return
      d += `${d ? ' L' : 'M'}${X(dd).toFixed(1)} ${Y(delta[i]).toFixed(1)}`
    })
    return <path d={d} fill="none" stroke="#E8ECF2" strokeWidth="2" />
  }

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    const sx = ((e.clientX - r.left) / r.width) * W
    if (sx < PL || sx > W - PR) return setHoverD(null)
    setHoverD(x0 + ((sx - PL) / (W - PL - PR)) * (x1 - x0))
  }
  const read = (s: Series, arr: number[]) => (hoverD == null || !s.trace.dist.length ? null : arr[Math.max(0, bisect(s.trace.dist, hoverD))])
  const dAt = hoverD == null || !a.trace.dist.length ? null : interp(hoverD, a.trace.dist, delta)

  return (
    <div>
      <div className="num mb-2 flex min-h-6 flex-wrap gap-x-4 text-sm">
        {hoverD == null ? <span className="text-mute">Move across the charts to read values and see both cars on the map</span> : (
          <>
            <span className="text-mute">{hoverD.toFixed(0)} m</span>
            {[a, b].map((s) => (
              <span key={s.num} style={{ color: s.color }}>
                {s.code} {read(s, s.trace.speed)?.toFixed(0)} km/h · {read(s, s.trace.throttle)?.toFixed(0)}% · G{read(s, s.trace.gear)}{read(s, s.trace.brake) ? ' · BRAKE' : ''}
              </span>
            ))}
            {dAt != null && <span>Δ {dAt >= 0 ? '+' : ''}{dAt.toFixed(3)} s</span>}
          </>
        )}
      </div>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full touch-none select-none" onPointerMove={onMove} onPointerDown={onMove}
        onPointerLeave={() => setHoverD(null)} role="img" aria-label="Delta, speed, throttle, brake and gear against distance">
        {panels.map((p, k) => {
          const top = tops[k]
          const Y = (v: number) => top + 4 + (1 - (v - p.lo) / (p.hi - p.lo || 1)) * (p.h - 8)
          return (
            <g key={p.key}>
              <rect x={PL} y={top} width={W - PL - PR} height={p.h} fill="#0F131B" />
              <text x={PL + 6} y={top + 13} fill="#93A0B4" fontSize="11" fontFamily="Inter">{p.label}</text>
              {p.ticks.map((v) => (
                <g key={v}>
                  <line x1={PL} x2={W - PR} y1={Y(v)} y2={Y(v)} stroke="#232D3F" />
                  <text x={PL - 6} y={Y(v) + 4} fill="#93A0B4" fontSize="10" textAnchor="end" fontFamily="JetBrains Mono">
                    {p.key === 'delta' ? `${v > 0 ? '+' : ''}${v.toFixed(2)}` : v.toFixed(0)}
                  </text>
                </g>
              ))}
              {corners.filter((c) => c.apex_m >= x0 && c.apex_m <= x1).map((c) => (
                <line key={c.corner} x1={X(c.apex_m)} x2={X(c.apex_m)} y1={top} y2={top + p.h} stroke="#2A3445" strokeDasharray="3 4" />
              ))}
              {p.key === 'delta' ? deltaPath(top, p) : <>{line(b, p, top)}{line(a, p, top)}</>}
            </g>
          )
        })}
        {corners.filter((c) => c.apex_m >= x0 && c.apex_m <= x1).map((c) => (
          <text key={c.corner} x={X(c.apex_m)} y={H - 4} fill="#93A0B4" fontSize="11" textAnchor="middle" fontFamily="JetBrains Mono">T{c.corner}</text>
        ))}
        {hoverD != null && <line x1={X(hoverD)} x2={X(hoverD)} y1={0} y2={H - 18} stroke="#00E5FF" strokeWidth="1" />}
      </svg>
    </div>
  )
}

function niceTicks(lo: number, hi: number): number[] {
  const span = hi - lo, step = span > 200 ? 50 : span > 80 ? 25 : 10
  const out = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v)
  return out
}
