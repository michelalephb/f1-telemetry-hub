'use client'

import { useRouter } from 'next/navigation'
import { useId, useMemo, useRef, useState } from 'react'
import type { CornerMetric } from '@/lib/api'
import { TYRE } from '@/lib/format'
import { bisect, interp, windowTime, type LapTrace } from '@/lib/telemetry'
import { rotator } from '@/lib/track'

export type Series = {
  num: string; code: string; team: string; color: string; lap: number; lapTime: string; lapMs?: number | null; compound: string | null
  trace: LapTrace; metrics: CornerMetric[]
}
type CornerPt = { corner: string; apex_m: number; x: number | null; y: number | null }
type Opt = { num: string; code: string; laps: { n: number; t: string }[] }

const W = 960, PL = 58, PR = 14
const WIN_BEFORE = 250, WIN_AFTER = 150

export default function CompareView({ sid, a, b, delta, corners, options, initialCorner, trackM, rot = 0 }: {
  sid: string; a: Series; b: Series; delta: number[]; corners: CornerPt[]; options: Opt[]; initialCorner: string | null; trackM: number; rot?: number
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

  // Verdict from the official lap times (the traces are aligned to them at the line)
  const final = a.lapMs != null && b.lapMs != null ? (b.lapMs - a.lapMs) / 1000 : delta.length ? delta[delta.length - 1] : 0
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
        <span className="num font-semibold">{Math.abs(final).toFixed(3)} s</span> faster over the lap ({a.code} {a.lapTime} vs {b.code} {b.lapTime}, official lap times).
        {(a.lap === 1 || b.lap === 1) && <span className="text-mute"> Lap 1 is timed from the start; the charts run from the timing line.</span>}
        {sel && <CornerVerdict a={a} b={b} corner={sel.corner} apex={sel.apex_m} />}
      </div>

      {/* corner chips */}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Zoom to corner">
        <Chip on={!sel} onClick={() => pickCorner(null)}>Full lap</Chip>
        {corners.map((c) => <Chip key={c.corner} on={c.corner === corner} onClick={() => pickCorner(c.corner)}>T{c.corner}</Chip>)}
      </div>

      <div className="flex flex-wrap gap-4">
        {/* map */}
        <section className="min-w-0 flex-[1_1_320px] rounded-xl border border-line bg-card p-3">
          <TrackMap a={a} b={b} corners={corners} range={range} hoverD={hoverD} selected={sel?.corner ?? null} rot={rot} />
          {sel && <CornerCards a={a} b={b} corner={sel.corner} apex={sel.apex_m} />}
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

// Window time from the plotted traces (not the pipeline's raw car clock), so the gain quoted here is
// exactly how much the delta curve moves across the zoomed window.
const winT = (s: Series, apex: number) => windowTime(s.trace, apex - WIN_BEFORE, apex + WIN_AFTER)

function CornerVerdict({ a, b, corner, apex }: { a: Series; b: Series; corner: string; apex: number }) {
  const ma = a.metrics.find((m) => m.corner === corner), mb = b.metrics.find((m) => m.corner === corner)
  const ta = winT(a, apex), tb = winT(b, apex)
  if (ta == null || tb == null) return null
  const d = tb - ta
  const w = d > 0 ? a : b
  const dv = ma?.min_speed_kph != null && mb?.min_speed_kph != null ? ma.min_speed_kph - mb.min_speed_kph : 0
  return (
    <span>
      {' '}Through T{corner}: <span className="font-semibold" style={{ color: w.color }}>{w.code}</span> gains{' '}
      <span className="num font-semibold">{Math.abs(d).toFixed(3)} s</span>
      {Math.abs(dv) >= 1 && <>, with <span className="num">{Math.abs(dv).toFixed(0)} km/h</span> more minimum speed for {dv > 0 ? a.code : b.code}</>}.
    </span>
  )
}

function CornerCards({ a, b, corner, apex }: { a: Series; b: Series; corner: string; apex: number }) {
  const ma = a.metrics.find((m) => m.corner === corner), mb = b.metrics.find((m) => m.corner === corner)
  const f = (v: number | null | undefined, unit: string, dp = 0, sign = false) =>
    v == null ? '—' : `${sign && v > 0 ? '+' : ''}${v.toFixed(dp)}${unit}`
  const rows: [string, string, string][] = [
    ['Brake point', f(ma?.brake_point_m, ' m', 0, true), f(mb?.brake_point_m, ' m', 0, true)],
    ['Entry speed', f(ma?.entry_speed_kph, ''), f(mb?.entry_speed_kph, '')],
    ['Min speed', f(ma?.min_speed_kph, ''), f(mb?.min_speed_kph, '')],
    ['Min speed at', f(ma?.min_speed_at_m, ' m', 0, true), f(mb?.min_speed_at_m, ' m', 0, true)],
    ['Exit (+100 m)', f(ma?.exit_speed_kph, ''), f(mb?.exit_speed_kph, '')],
    ['Window time', f(winT(a, apex), ' s', 3), f(winT(b, apex), ' s', 3)],
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

function TrackMap({ a, b, corners, range, hoverD, selected, rot }: {
  a: Series; b: Series; corners: CornerPt[]; range: [number, number]; hoverD: number | null; selected: string | null; rot: number
}) {
  // Rotated the way F1 graphics show the circuit (MultiViewer rotation, same as the thumbnails)
  const R = useMemo(() => rotator(rot), [rot])
  const t = useMemo(() => {
    const xs: number[] = [], ys: number[] = []
    a.trace.x.forEach((x, i) => { const [u, v] = R(x, a.trace.y[i]); xs.push(u); ys.push(v) })
    return { x: xs, y: ys, dist: a.trace.dist }
  }, [a.trace, R])
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
    const [x, y] = R(interp(hoverD, s.trace.dist, s.trace.x), interp(hoverD, s.trace.dist, s.trace.y))
    return <circle cx={x - box.x0} cy={box.h - (y - box.y0)} r={sw * 0.9} fill={s.color} stroke="#0B0E14" strokeWidth={sw / 4} />
  }
  return (
    <svg viewBox={`0 0 ${box.w.toFixed(0)} ${box.h.toFixed(0)}`} className="h-auto w-full" role="img" aria-label="Track map">
      <polyline points={path} fill="none" stroke="#2A3445" strokeWidth={sw} strokeLinejoin="round" strokeLinecap="round" />
      {range[1] - range[0] < 2000 && <polyline points={win} fill="none" stroke="#00E5FF" strokeWidth={sw} strokeLinecap="round" strokeOpacity="0.8" />}
      {corners.filter((c) => c.x != null && c.y != null).map((c) => [c, R(c.x as number, c.y as number)] as const).map(([c, [cx, cy]]) => (
        <text key={c.corner} x={cx - box.x0} y={box.h - (cy - box.y0)} dy={-sw * 1.3}
          fill={c.corner === selected ? '#FFFFFF' : '#93A0B4'} fontSize={sw * (c.corner === selected ? 2.2 : 1.6)}
          fontWeight={c.corner === selected ? 700 : 400} textAnchor="middle" fontFamily="JetBrains Mono">{c.corner}</text>
      ))}
      {dot(b)}{dot(a)}
    </svg>
  )
}

// ---------------------------------------------------------------- stacked traces

type Panel = {
  key: string; title: string; unit: string; h: number; lo: number; hi: number; ticks: number[]
  fmt?: (v: number) => string
}

const TITLE_H = 18     // strip above each panel for its title
const GAP = 10         // space between panels
const CORNER_H = 34    // corner label strip at the top (two staggered rows)

/** A tick step from the 1-2-5 series giving about `n` ticks. */
function niceStep(span: number, n = 4): number {
  const raw = span / Math.max(1, n)
  const p = 10 ** Math.floor(Math.log10(raw || 1))
  const m = raw / p
  return (m >= 5 ? 5 : m >= 2 ? 2 : 1) * p * (m > 5 ? 2 : 1)
}
function niceTicks(lo: number, hi: number, n = 4): number[] {
  const st = niceStep(hi - lo, n), out: number[] = []
  for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) out.push(Math.round(v / st) * st)
  return out
}

function Traces({ a, b, delta, corners, range, hoverD, setHoverD }: {
  a: Series; b: Series; delta: number[]; corners: CornerPt[]; range: [number, number]; hoverD: number | null; setHoverD: (d: number | null) => void
}) {
  const ref = useRef<SVGSVGElement>(null)
  const uid = useId().replace(/:/g, '')
  const [x0, x1] = range
  const X = (d: number) => PL + ((d - x0) / (x1 - x0 || 1)) * (W - PL - PR)
  const inR = (d: number) => d >= x0 - 20 && d <= x1 + 20
  const zoomed = x1 - x0 < 2000

  // ---- scales from what is visible
  const dv = delta.filter((_, i) => inR(a.trace.dist[i]))
  const dLo = Math.min(0, ...dv), dHi = Math.max(0, ...dv)
  const dPad = Math.max(0.02, (dHi - dLo) * 0.12)
  const vis = (s: Series) => s.trace.speed.filter((_, i) => inR(s.trace.dist[i]))
  const sAll = [...vis(a), ...vis(b)]
  const sLo = Math.max(0, Math.min(...sAll) - 10), sHi = Math.max(...sAll) + 10
  const panels: Panel[] = [
    { key: 'delta', title: `Gap  ·  above 0: ${a.code} ahead, below 0: ${b.code} ahead`, unit: 's', h: 96, lo: dLo - dPad, hi: dHi + dPad,
      ticks: niceTicks(dLo - dPad, dHi + dPad, 3), fmt: (v) => `${v > 0 ? '+' : ''}${Math.abs(v) < 1 ? v.toFixed(2) : v.toFixed(1)}` },
    { key: 'speed', title: 'Speed', unit: 'km/h', h: 220, lo: sLo, hi: sHi, ticks: niceTicks(sLo, sHi, 5) },
    { key: 'throttle', title: 'Throttle', unit: '%', h: 72, lo: -4, hi: 104, ticks: [0, 50, 100] },
    { key: 'brake', title: 'Brake', unit: '', h: 40, lo: 0, hi: 1, ticks: [] },
    { key: 'gear', title: 'Gear', unit: '', h: 80, lo: 0.5, hi: 8.5, ticks: [2, 4, 6, 8] },
  ]
  const tops: number[] = []
  let acc = CORNER_H
  for (const p of panels) { tops.push(acc + TITLE_H); acc += TITLE_H + p.h + GAP }
  const H = acc + 22 // distance axis
  const Yf = (p: Panel, top: number) => (v: number) => top + (1 - (v - p.lo) / (p.hi - p.lo || 1)) * p.h

  const path = (s: Series, ys: number[], p: Panel, top: number, step = false) => {
    const Y = Yf(p, top), ds = s.trace.dist
    let d = ''
    for (let i = 0; i < ds.length; i++) {
      if (!inR(ds[i])) continue
      const x = X(ds[i]).toFixed(1), y = Y(ys[i]).toFixed(1)
      d += !d ? `M${x} ${y}` : step ? ` H${x} V${y}` : ` L${x} ${y}`
    }
    return d
  }

  // Corner labels: one strip at the top, staggered onto a second row when two would overlap.
  const shown = corners.filter((c) => c.apex_m >= x0 && c.apex_m <= x1)
  const labelRow: number[] = []
  const lastX = [-1e9, -1e9]
  for (const c of shown) {
    const x = X(c.apex_m)
    const row = x - lastX[0] >= 34 ? 0 : x - lastX[1] >= 34 ? 1 : 0
    lastX[row] = x
    labelRow.push(row)
  }

  // Delta panel geometry
  const pD = panels[0], topD = tops[0], YD = Yf(pD, topD)
  let deltaLine = ''
  const inPts: [number, number][] = []
  a.trace.dist.forEach((dd, i) => {
    if (!inR(dd)) return
    inPts.push([X(dd), YD(delta[i])])
  })
  deltaLine = inPts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  const zeroY = YD(0)
  const area = inPts.length ? `${deltaLine} L${inPts[inPts.length - 1][0].toFixed(1)} ${zeroY.toFixed(1)} L${inPts[0][0].toFixed(1)} ${zeroY.toFixed(1)} Z` : ''

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    const sx = ((e.clientX - r.left) / r.width) * W
    if (sx < PL || sx > W - PR) return setHoverD(null)
    setHoverD(x0 + ((sx - PL) / (W - PL - PR)) * (x1 - x0))
  }
  const read = (s: Series, arr: number[]) => (hoverD == null || !s.trace.dist.length ? null : arr[Math.max(0, bisect(s.trace.dist, hoverD))])
  const dAt = hoverD == null || !a.trace.dist.length ? null : interp(hoverD, a.trace.dist, delta)
  // Distance axis: metres from the line, or metres to the apex when zoomed on a corner
  const apex = x0 + WIN_BEFORE
  const xTicks = zoomed ? niceTicks(x0 - apex, x1 - apex, 8).map((v) => ({ at: apex + v, label: v > 0 ? `+${v}` : `${v}` }))
    : niceTicks(Math.max(0, x0), x1, 8).map((v) => ({ at: v, label: v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${v}` }))

  return (
    <div>
      {/* legend and live readout */}
      <div className="mb-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
        {[a, b].map((s) => (
          <span key={s.num} className="flex items-center gap-2">
            <span className="inline-block h-[3px] w-5 rounded" style={{ background: s.color }} />
            <span className="font-semibold">{s.code}</span>
            <span className="num text-mute">L{s.lap} · {s.lapTime}</span>
          </span>
        ))}
      </div>
      <div className="num mb-1 flex min-h-6 flex-wrap gap-x-4 text-sm">
        {hoverD == null ? <span className="text-mute">Move across the charts to read values and see both cars on the map</span> : (
          <>
            <span className="text-mute">{hoverD.toFixed(0)} m</span>
            {[a, b].map((s) => (
              <span key={s.num} style={{ color: s.color }}>
                {s.code} {read(s, s.trace.speed)?.toFixed(0)} km/h · {read(s, s.trace.throttle)?.toFixed(0)}% · G{read(s, s.trace.gear)}{read(s, s.trace.brake) ? ' · brake' : ''}
              </span>
            ))}
            {dAt != null && <span>gap {dAt >= 0 ? `${a.code} +` : `${b.code} +`}{Math.abs(dAt).toFixed(3)} s</span>}
          </>
        )}
      </div>

      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full touch-none select-none" onPointerMove={onMove} onPointerDown={onMove}
        onPointerLeave={() => setHoverD(null)} role="img" aria-label="Gap, speed, throttle, brake and gear against distance">

        {/* corner labels and faint apex guides */}
        {shown.map((c, i) => (
          <g key={c.corner}>
            <line x1={X(c.apex_m)} x2={X(c.apex_m)} y1={CORNER_H - 4} y2={H - 22} stroke="#FFFFFF" strokeOpacity="0.06" />
            <text x={X(c.apex_m)} y={labelRow[i] ? 26 : 12} fill="#93A0B4" fontSize="11" textAnchor="middle" fontFamily="JetBrains Mono">T{c.corner}</text>
          </g>
        ))}

        {panels.map((p, k) => {
          const top = tops[k], Y = Yf(p, top)
          return (
            <g key={p.key}>
              <text x={PL} y={top - 5} fill="#C8D0DC" fontSize="11.5" fontWeight="600" fontFamily="Inter">
                {p.title}{p.unit && <tspan fill="#93A0B4" fontWeight="400">{`  ${p.unit}`}</tspan>}
              </text>
              <rect x={PL} y={top} width={W - PL - PR} height={p.h} fill="#0F131B" rx="3" />
              {p.ticks.map((v) => (
                <g key={v}>
                  <line x1={PL} x2={W - PR} y1={Y(v)} y2={Y(v)} stroke={p.key === 'delta' && v === 0 ? '#3A4558' : '#1C2533'} />
                  <text x={PL - 8} y={Y(v) + 3.5} fill="#93A0B4" fontSize="10" textAnchor="end" fontFamily="JetBrains Mono">{p.fmt ? p.fmt(v) : v}</text>
                </g>
              ))}

              {p.key === 'delta' && (
                <>
                  <clipPath id={`above${uid}`}><rect x={PL} y={top} width={W - PL - PR} height={Math.max(0, zeroY - top)} /></clipPath>
                  <clipPath id={`below${uid}`}><rect x={PL} y={zeroY} width={W - PL - PR} height={Math.max(0, top + p.h - zeroY)} /></clipPath>
                  <path d={area} fill={a.color} fillOpacity="0.22" clipPath={`url(#above${uid})`} />
                  <path d={area} fill={b.color} fillOpacity="0.22" clipPath={`url(#below${uid})`} />
                  <line x1={PL} x2={W - PR} y1={zeroY} y2={zeroY} stroke="#3A4558" />
                  <path d={deltaLine} fill="none" stroke="#E8ECF2" strokeWidth="1.8" strokeLinejoin="round" />
                </>
              )}
              {p.key === 'speed' && [b, a].map((s) => (
                <path key={s.num} d={path(s, s.trace.speed, p, top)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
              ))}
              {p.key === 'throttle' && [b, a].map((s) => (
                <path key={s.num} d={path(s, s.trace.throttle, p, top)} fill="none" stroke={s.color} strokeWidth="1.6" strokeLinejoin="round" />
              ))}
              {p.key === 'gear' && [b, a].map((s) => (
                <path key={s.num} d={path(s, s.trace.gear, p, top, true)} fill="none" stroke={s.color} strokeWidth="1.6" strokeLinejoin="round"
                  strokeOpacity={s === b ? 0.85 : 1} />
              ))}
              {p.key === 'brake' && [a, b].map((s, lane) => {
                // two lanes of solid bars: A on top, B below
                const laneH = p.h / 2 - 4, y = top + 3 + lane * (p.h / 2)
                const ds = s.trace.dist, br = s.trace.brake
                const bars: [number, number][] = []
                let start: number | null = null
                for (let i = 0; i < ds.length; i++) {
                  if (!inR(ds[i])) continue
                  if (br[i] && start == null) start = ds[i]
                  if (!br[i] && start != null) { bars.push([start, ds[i]]); start = null }
                }
                if (start != null) bars.push([start, ds[ds.length - 1]])
                return (
                  <g key={s.num}>
                    <text x={PL - 8} y={y + laneH / 2 + 3.5} fill={s.color} fontSize="10" textAnchor="end" fontFamily="JetBrains Mono">{s.code}</text>
                    {bars.map(([u, v], j) => (
                      <rect key={j} x={X(u)} y={y} width={Math.max(1.5, X(v) - X(u))} height={laneH} rx="1.5" fill={s.color} fillOpacity="0.9" />
                    ))}
                  </g>
                )
              })}
            </g>
          )
        })}

        {/* distance axis */}
        {xTicks.map((t) => (
          <text key={t.at} x={X(t.at)} y={H - 6} fill="#93A0B4" fontSize="10" textAnchor="middle" fontFamily="JetBrains Mono">{t.label}</text>
        ))}
        <text x={W - PR} y={H - 6} fill="#93A0B4" fontSize="10" textAnchor="end" fontFamily="Inter">{zoomed ? 'm to apex' : 'm'}</text>

        {hoverD != null && <line x1={X(hoverD)} x2={X(hoverD)} y1={CORNER_H} y2={H - 20} stroke="#00E5FF" strokeWidth="1" />}
      </svg>
    </div>
  )
}
