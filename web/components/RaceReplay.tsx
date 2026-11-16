'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import DriverBadge, { badgeText } from '@/components/DriverBadge'
import ShareButton from '@/components/ShareButton'
import { useAsync } from '@/components/useAsync'
import type { Corner, Driver } from '@/lib/api'
import { teamColor } from '@/lib/format'
import { leaderLap, loadReplay, runningOrder, stateAt } from '@/lib/replay'
import { pointAt, project, trackPath, type Outline } from '@/lib/track'
import { recordReplay, videoFormat, type VideoFrame } from '@/lib/video'

const ACCENT = '#00E5FF'
const SPEEDS = [10, 30, 60, 120, 300, 600]
const LENGTHS = [15, 30, 60]
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? ''

const clock = (s: number) => {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = Math.floor(s % 60)
  return `${h ? `${h}:` : ''}${String(m).padStart(h ? 2 : 1, '0')}:${String(x).padStart(2, '0')}`
}

export default function RaceReplay({ sid, prefix, trackM, raceLaps, title, drivers, grid, classified, outline, corners, me, initialT }: {
  sid: string; prefix: string; trackM: number; raceLaps: number; title: string
  drivers: Map<string, Driver>; grid: Map<string, number | null>; classified: Set<string>
  outline: Outline | null; corners: Corner[]; me: string; initialT: number | null
}) {
  const { data: replay, loading } = useAsync(() => loadReplay(prefix), [prefix])
  const tp = useMemo(() => (outline ? trackPath(outline) : null), [outline])
  const start = replay ? replay.t0 + Math.min(...replay.cars.map((c) => c.first)) * replay.step : 0
  const end = replay ? replay.t0 + Math.max(...replay.cars.map((c) => c.last)) * replay.step : 0
  const [t, setT] = useState<number | null>(initialT)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(60)
  const [len, setLen] = useState(30)
  const [rec, setRec] = useState<{ p: number } | null>(null)
  const [file, setFile] = useState<{ url: string; name: string; blob: Blob } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const now = t ?? start
  const last = useRef<number | null>(null)

  useEffect(() => {
    if (!playing || !replay) return
    let raf = 0
    const step = (ts: number) => {
      const dt = last.current == null ? 0 : Math.min(0.1, (ts - last.current) / 1000)
      last.current = ts
      setT((v) => {
        const n = Math.min(end, (v ?? start) + dt * speed)
        if (n >= end) setPlaying(false)
        return n
      })
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => { cancelAnimationFrame(raf); last.current = null }
  }, [playing, speed, replay, start, end])

  useEffect(() => () => { if (file) URL.revokeObjectURL(file.url) }, [file])

  if (loading) return <p className="animate-pulse py-6 text-sm text-mute">Loading the replay…</p>
  if (!replay || !tp || !outline) return <p className="py-4 text-sm text-mute">The replay for this session is not built yet.</p>

  const frameAt = (time: number) => {
    const states = stateAt(replay, time, grid, classified)
    const order = runningOrder(replay, states, time, trackM)
    const pos = new Map(order.map((o) => [o.num, o.pos]))
    return { states, order, pos, lap: leaderLap(states, trackM, raceLaps) }
  }
  const f = frameAt(now)
  const col = (n: string) => teamColor(drivers.get(n)?.team_color)
  const code = (n: string) => drivers.get(n)?.abbreviation ?? n
  const cars = f.states.filter((s) => s.onTrack && !s.out).map((s) => {
    const [u, v] = pointAt(tp, s.metres / trackM)
    return { num: s.num, u, v, me: s.num === me, pos: f.pos.get(s.num) ?? 0 }
  }).sort((a, b) => Number(a.me) - Number(b.me))
  const s = Math.max(outline.w, outline.h) / 100
  const [l0, l1] = [pointAt(tp, 0), pointAt(tp, 0.004)]
  const nl = Math.hypot(l1[0] - l0[0], l1[1] - l0[1]) || 1
  const nx = -(l1[1] - l0[1]) / nl, ny = (l1[0] - l0[0]) / nl
  const meRow = f.order.find((o) => o.num === me)

  const video = async () => {
    setErr(null); setFile(null); setPlaying(false)
    const frameFor = (p: number): VideoFrame => {
      const time = start + p * (end - start)
      const g = frameAt(time)
      return {
        lap: `${g.lap}/${raceLaps}`,
        sub: `Following ${code(me)} · P${grid.get(me) ?? '?'} on the grid · now P${g.pos.get(me) ?? '?'}`,
        cars: g.states.filter((x) => x.onTrack && !x.out).map((x) => {
          const [u, v] = pointAt(tp, x.metres / trackM)
          return { num: x.num, code: code(x.num), color: col(x.num), fg: badgeText(col(x.num)), u, v, me: x.num === me, pos: g.pos.get(x.num) ?? 0 }
        }),
        rows: g.order.map((o) => ({ pos: o.pos, num: o.num, code: code(o.num), color: col(o.num), fg: badgeText(col(o.num)), gap: o.gap })),
      }
    }
    try {
      setRec({ p: 0 })
      const { blob, ext } = await recordReplay({
        title, outlinePts: tp.p, ow: outline.w, oh: outline.h, logoUrl: `${BASE}/logo.png`, accent: ACCENT,
        seconds: len, frameAt: frameFor, onProgress: (p) => setRec({ p }),
      })
      setFile({ url: URL.createObjectURL(blob), name: `f1telemetryhub_${sid}_${code(me).toLowerCase()}_replay.${ext}`, blob })
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setRec(null)
    }
  }
  const shareVideo = async () => {
    if (!file) return
    const f2 = new File([file.blob], file.name, { type: file.blob.type })
    try {
      if (navigator.canShare?.({ files: [f2] })) await navigator.share({ files: [f2], title })
      else setErr('This browser cannot share files: download the video and post it from your gallery.')
    } catch (e) { if (!(e instanceof Error && e.name === 'AbortError')) setErr('Sharing failed') }
  }
  const canRecord = typeof window !== 'undefined' && videoFormat() != null

  return (
    <section className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-head text-lg font-bold">Race replay</h2>
        <span className="num text-sm text-mute">Lap <b className="text-ink">{f.lap}</b>/{raceLaps} · {clock(Math.max(0, now - start))}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-4">
        <div className="min-w-0 flex-[999_1_520px]">
          <svg viewBox={`${-8 * s} ${-8 * s} ${outline.w + 16 * s} ${outline.h + 16 * s}`} className="h-auto max-h-[620px] w-full" role="img"
            aria-label={`Track map: every car at ${clock(Math.max(0, now - start))} into the race`}>
            <polygon points={outline.pts} fill="none" stroke="#232D3F" strokeWidth={4.4 * s} strokeLinejoin="round" />
            <line x1={l0[0] + nx * 3 * s} y1={l0[1] + ny * 3 * s} x2={l0[0] - nx * 3 * s} y2={l0[1] - ny * 3 * s} stroke="#E8ECF2" strokeWidth={0.7 * s} />
            {corners.filter((c) => c.x != null && c.y != null).map((c) => {
              const [u, v] = project(outline, c.x as number, c.y as number)
              return <text key={c.corner} x={u} y={v - 4.4 * s} fill="#5D6B82" fontSize={2.4 * s} textAnchor="middle" fontFamily="JetBrains Mono">{c.corner}</text>
            })}
            {cars.map((c) => (
              <g key={c.num}>
                {c.me && <>
                  <circle cx={c.u} cy={c.v} r={4 * s} fill="none" stroke={ACCENT} strokeWidth={0.7 * s} />
                  <rect x={c.u - 9 * s} y={c.v - 11 * s} width={18 * s} height={5 * s} rx={s} fill={ACCENT} />
                  <text x={c.u} y={c.v - 7.4 * s} fill="#0B0E14" fontSize={3 * s} fontWeight={700} textAnchor="middle" fontFamily="JetBrains Mono">{code(c.num)} P{c.pos}</text>
                </>}
                <circle cx={c.u} cy={c.v} r={(c.me ? 2.9 : 2.2) * s} fill={col(c.num)} stroke="#0B0E14" strokeWidth={0.4 * s} />
                <text x={c.u} y={c.v + 0.9 * s} fill={badgeText(col(c.num))} fontSize={(c.me ? 2.8 : 2.2) * s} fontWeight={700} textAnchor="middle" fontFamily="Space Grotesk">{c.num}</text>
              </g>
            ))}
          </svg>
        </div>
        <ol className="min-w-0 flex-[1_1_260px] space-y-0.5" aria-label="Running order">
          {f.order.map((o) => (
            <li key={o.num} className={`num flex items-center gap-2 rounded-md px-2 py-1 text-sm ${o.num === me ? 'bg-line/70' : ''}`}>
              <span className="w-6 text-right text-mute">{o.pos}</span>
              <DriverBadge num={o.num} color={col(o.num)} size={22} />
              <span className="w-11 font-bold">{code(o.num)}</span>
              <span className="flex-1 text-right text-ink/80">{o.gap}</span>
              {(() => { const g = grid.get(o.num); const d = g && g > 0 ? g - o.pos : 0; return <span className={`w-9 text-right ${d > 0 ? 'text-gain' : d < 0 ? 'text-loss' : 'text-mute'}`}>{d > 0 ? `+${d}` : d < 0 ? d : '='}</span> })()}
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => { if (now >= end) setT(start); setPlaying((p) => !p) }}
          className="min-h-11 min-w-24 rounded-lg bg-cyan px-5 font-semibold text-bg">{playing ? 'Pause' : 'Play'}</button>
        <span className="ml-1 text-xs text-mute">Speed</span>
        {SPEEDS.map((v) => (
          <button key={v} type="button" aria-pressed={v === speed} onClick={() => setSpeed(v)}
            className={`num min-h-11 rounded-full border px-3 text-sm ${v === speed ? 'border-ink bg-ink text-bg' : 'border-line text-ink/80'}`}>{v}×</button>
        ))}
        <span className="num ml-auto text-xs text-mute">full race in {clock((end - start) / speed)} at {speed}×</span>
      </div>
      <input type="range" min={Math.floor(start)} max={Math.ceil(end)} step={1} value={Math.round(now)} aria-label="Race time"
        onChange={(e) => setT(Number(e.target.value))} className="mt-2 h-11 w-full accent-cyan" />
      {meRow && <p className="num text-sm text-ink/80">{code(me)}: P{grid.get(me) ?? '?'} on the grid, P{meRow.pos} now{meRow.gap && meRow.pos > 1 ? `, ${meRow.gap} to the leader` : ''}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <ShareButton title={`${title}: ${code(me)} replay`} url={() => {
          const u = new URL(window.location.href); u.searchParams.set('d', me); u.searchParams.set('rt', String(Math.round(now))); return u.toString()
        }} />
        {canRecord ? (
          <>
            <label className="ml-2 text-xs text-mute" htmlFor="vlen">Video length</label>
            <select id="vlen" value={len} onChange={(e) => setLen(Number(e.target.value))} disabled={!!rec}
              className="min-h-11 rounded-lg border border-line bg-bg px-2 text-sm">
              {LENGTHS.map((v) => <option key={v} value={v}>{v} s</option>)}
            </select>
            <button type="button" onClick={video} disabled={!!rec}
              className="min-h-11 rounded-lg border border-line px-4 text-sm hover:border-cyan/60 disabled:opacity-50">
              {rec ? `Recording ${Math.round(rec.p * 100)} %` : 'Make video'}
            </button>
            {file && <>
              <a href={file.url} download={file.name} className="flex min-h-11 items-center rounded-lg bg-cyan px-4 text-sm font-semibold text-bg">Download video</a>
              <button type="button" onClick={shareVideo} className="min-h-11 rounded-lg border border-line px-4 text-sm">Share video</button>
            </>}
            {rec && <span className="text-xs text-mute">Keep this tab open while it records.</span>}
          </>
        ) : <span className="text-xs text-mute">This browser cannot record video.</span>}
        {err && <span role="alert" className="text-xs text-loss">{err}</span>}
      </div>
    </section>
  )
}
