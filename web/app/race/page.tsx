'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useMemo, useState } from 'react'
import DriverBadge from '@/components/DriverBadge'
import EventNav from '@/components/EventNav'
import RaceReplay from '@/components/RaceReplay'
import ShareButton from '@/components/ShareButton'
import Flag from '@/components/Flag'
import { Failed, Loading, useAsync } from '@/components/useAsync'
import { getCorners, getDrivers, getEvent, getLaps, getResults, getSession, getTrace, type Corner, type Driver } from '@/lib/api'
import { SESSION_LABEL, teamColor } from '@/lib/format'
import { cornerAt, lapClock, movesOf, ordersByLap, passPoint, positions, type Move } from '@/lib/race'
import { getOutline, outlineFrom, project, type Outline } from '@/lib/track'

export default function Page() {
  return <Suspense fallback={<Loading what="race" />}><RaceView /></Suspense>
}

async function load(sid: string) {
  const session = await getSession(sid)
  if (!session || session.status !== 'ingested') throw new Error(`session ${sid} is not available`)
  if (!['R', 'S'].includes(session.session_code)) throw new Error('the race story covers races and sprint races')
  const [event, drivers, laps, results, corners, outline] = await Promise.all([
    getEvent(session.season, session.round), getDrivers(sid), getLaps(sid),
    getResults(session.season, session.round, session.session_code), getCorners(sid), getOutline(session.season, session.round),
  ])
  return { session, event, drivers, laps, results, corners, outline }
}

const GAIN = '#10B981', LOSS = '#EF4444', LINE = '#00E5FF'

function RaceView() {
  const q = useSearchParams()
  const router = useRouter()
  const sid = q.get('id') ?? ''
  const { data, error, loading } = useAsync(() => load(sid), [sid])
  if (error) return <Failed error={error} />
  if (loading || !data) return <Loading what="race" />
  const { session, event, drivers, laps, results, corners, outline } = data
  const drv = new Map(drivers.map((d) => [d.driver_number, d]))
  const classified = results.filter((r) => r.position != null).sort((a, b) => a.position! - b.position!)
  const grid = new Map(results.map((r) => [r.driver_number, r.grid]))
  const nCars = Math.max(results.length, drivers.length)
  // Default: the biggest climber of the day (pit lane start counts as last on the grid)
  const climb = (r: (typeof results)[number]) => (r.grid && r.grid > 0 ? r.grid : nCars) - (r.position ?? nCars)
  const fallback = [...classified].sort((a, b) => climb(b) - climb(a) || a.position! - b.position!)[0]?.driver_number ?? drivers[0]?.driver_number
  const qd = q.get('d')
  const me = qd && laps.some((l) => l.driver_number === qd) ? qd : fallback
  const follow = (d: string) => router.replace(`/race/?id=${sid}&d=${d}`, { scroll: false })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link href="/" className="text-xs text-mute hover:text-ink">← Season</Link>
        <p className="mt-2 text-xs uppercase tracking-widest text-mute">R{String(session.round).padStart(2, '0')} · {event?.location ?? ''}</p>
        <h1 className="mt-1 flex items-center gap-3 font-head text-3xl font-bold"><Flag country={event?.country} className="h-7" />{event?.event_name ?? sid}</h1>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
          <p className="text-lg text-mute">{SESSION_LABEL[session.session_code]} story</p>
          <ShareButton title={`${event?.event_name ?? ''} ${SESSION_LABEL[session.session_code]} story`} />
        </div>
      </div>
      <EventNav season={session.season} round={session.round} sid={sid} tab="race" />
      {me ? (
        <Story key={`${sid}/${me}`} sid={sid} prefix={session.trace_prefix} trackM={session.track_length_m ?? 5000} me={me} follow={follow}
          drv={drv} order={[...classified.map((r) => r.driver_number), ...drivers.map((d) => d.driver_number).filter((d) => !classified.some((r) => r.driver_number === d))]}
          laps={laps} grid={grid} result={results.find((r) => r.driver_number === me)} corners={corners} outline={outline}
          title={`${event?.event_name ?? sid} · ${SESSION_LABEL[session.session_code]}`}
          classified={new Set(results.filter((r) => r.laps != null && results[0]?.laps != null && r.laps >= 0.9 * (results.find((x) => x.position === 1)?.laps ?? 0)).map((r) => r.driver_number))}
          initialT={q.get('rt') ? Number(q.get('rt')) : null} />
      ) : <p className="text-sm text-mute">No lap data for this session.</p>}
    </div>
  )
}

type Loc = { d: number; u: number; v: number; corner: string | null; start: boolean } | null

function Story({ sid, prefix, trackM, me, follow, drv, order, laps, grid, result, corners, outline, title, classified, initialT }: {
  sid: string; prefix: string | null; trackM: number; me: string; follow: (d: string) => void; drv: Map<string, Driver>; order: string[]
  laps: Awaited<ReturnType<typeof load>>['laps']; grid: Map<string, number | null>; result: Awaited<ReturnType<typeof load>>['results'][number] | undefined
  corners: Corner[]; outline: Outline | null; title: string; classified: Set<string>; initialT: number | null
}) {
  const orders = useMemo(() => ordersByLap(laps, grid, order), [laps, grid, order])
  const pos = useMemo(() => positions(me, orders), [me, orders])
  const moves = useMemo(() => movesOf(me, orders, laps), [me, orders, laps])
  const onTrack = moves.filter((m) => !m.pit)
  const myLaps = laps.filter((l) => l.driver_number === me)
  const stops = myLaps.filter((l) => l.pit_in).map((l) => l.lap_number)
  const code = (d: string) => drv.get(d)?.abbreviation ?? d
  const [hi, setHi] = useState<string | null>(null)

  // Where each on track move happened: needs the traces of this driver and of every car involved.
  const located = useAsync(async () => {
    const out = new Map<string, Loc>()
    if (!prefix || !onTrack.length) return { out, map: null as Outline | null }
    const mine = await getTrace(prefix, me)
    let map = outline
    if (!map) {
      const l2 = mine.filter((r) => r.lap_number === 2)
      map = outlineFrom(l2.map((r) => r.x), l2.map((r) => r.y))
    }
    const others = [...new Set(onTrack.map((m) => m.other))]
    const rows = new Map(await Promise.all(others.map(async (d) => [d, await getTrace(prefix, d).catch(() => [])] as const)))
    for (const m of onTrack) {
      const p = passPoint(lapClock(mine, m.lap), lapClock(rows.get(m.other) ?? [], m.lap), m.kind)
      const [u, v] = p && map ? project(map, p.x, p.y) : [NaN, NaN]
      out.set(`${m.lap}/${m.other}`, p ? { d: p.d, u, v, corner: p.early && m.lap === 1 ? null : cornerAt(p.d, corners, trackM), start: Boolean(p.early && m.lap === 1) } : null)
    }
    return { out, map }
  }, [sid, me])
  const loc = located.data?.out
  const map = outline ?? located.data?.map ?? null

  const gridPos = pos[0]
  const finish = result?.position ?? pos[pos.length - 1]
  const gains = onTrack.filter((m) => m.kind === 'gain').length
  const losses = onTrack.filter((m) => m.kind === 'loss').length

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <label htmlFor="follow" className="text-xs uppercase tracking-widest text-mute">Follow driver</label>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <DriverBadge num={me} color={teamColor(drv.get(me)?.team_color)} size={40} />
            <select id="follow" value={me} onChange={(e) => follow(e.target.value)}
              className="min-h-11 rounded-lg border border-line bg-card px-3 font-head text-2xl font-bold">
              {order.map((d) => <option key={d} value={d}>{code(d)}</option>)}
            </select>
            <span className="num text-sm text-ink/80">
              P{gridPos ?? '?'} grid → {result?.position ? `P${finish} finish` : (result?.status ?? 'did not finish')} · {gains} passes made · {losses} lost on track · {stops.length} {stops.length === 1 ? 'stop' : 'stops'}
            </span>
          </div>
        </div>
      </div>

      {prefix && (
        <RaceReplay sid={sid} prefix={prefix} trackM={trackM} raceLaps={Math.max(1, ...laps.map((l) => l.lap_number))} title={title}
          drivers={drv} grid={grid} classified={classified} finish={order} outline={outline} corners={corners} me={me} initialT={initialT} />
      )}

      <div className="flex flex-wrap gap-4">
        <section className="min-w-0 flex-[999_1_560px] rounded-xl border border-line bg-card p-4">
          <h2 className="font-head text-lg font-bold">Where the passes happened</h2>
          <p className="mt-1 text-xs text-mute">
            <span style={{ color: GAIN }}>●</span> places won · <span style={{ color: LOSS }}>●</span> places lost, on track only.
            Logged where the order changed, which can be after the move was set up.
          </p>
          {located.loading && onTrack.length > 0 && <p className="mt-2 animate-pulse text-xs text-mute">Locating {onTrack.length} moves on track…</p>}
          {map ? <PassMap map={map} corners={corners} moves={onTrack} loc={loc} hi={hi} /> : !located.loading && <p className="mt-4 text-sm text-mute">Track map not available yet.</p>}
        </section>
        <aside className="min-w-0 flex-[1_1_320px] rounded-xl border border-line bg-card p-4">
          <h2 className="font-head text-lg font-bold">Move log</h2>
          {moves.length === 0 ? <p className="mt-3 text-sm text-mute">No position changes.</p> : (
            <div className="mt-2 max-h-[560px] overflow-auto">
              <table className="w-full border-collapse text-sm">
                <thead><tr className="text-left text-xs uppercase tracking-wider text-mute">
                  {['Lap', 'Where', 'Move', 'Pos'].map((h) => <th key={h} className="sticky top-0 bg-card px-2 py-2 font-medium">{h}</th>)}
                </tr></thead>
                <tbody>
                  {moves.map((m: Move) => {
                    const k = `${m.lap}/${m.other}`
                    const l = loc?.get(k)
                    const where = m.pit ? 'pit stop' : l?.start ? 'start' : l?.corner ? `T${l.corner}` : located.loading ? '…' : 'not seen'
                    return (
                      <tr key={k + m.kind} onMouseEnter={() => setHi(k)} onMouseLeave={() => setHi(null)}
                        className={`border-t border-line font-mono ${hi === k ? 'bg-line/50' : ''} ${m.pit ? 'text-mute' : ''}`}>
                        <td className="px-2 py-2 text-mute">L{m.lap}</td>
                        <td className="px-2 py-2">{where}</td>
                        <td className="px-2 py-2"><span style={{ color: m.pit ? undefined : m.kind === 'gain' ? GAIN : LOSS }}>{m.kind === 'gain' ? 'passed' : 'lost to'}</span>{' '}
                          <span className="inline-flex items-center gap-1 align-middle"><DriverBadge num={m.other} color={teamColor(drv.get(m.other)?.team_color)} size={18} /><b>{code(m.other)}</b></span></td>
                        <td className="px-2 py-2 text-ink/80">P{m.posAfter}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </aside>
      </div>

      <PositionChart pos={pos} moves={moves} stops={stops} n={orders[0]?.length ?? 20} color={teamColor(drv.get(me)?.team_color)} />
    </>
  )
}

function PassMap({ map, corners, moves, loc, hi }: { map: Outline; corners: Corner[]; moves: Move[]; loc: Map<string, Loc> | undefined; hi: string | null }) {
  const s = Math.max(map.w, map.h) / 100
  const pts = corners.filter((c) => c.x != null && c.y != null).map((c) => ({ c: c.corner, p: project(map, c.x as number, c.y as number) }))
  const count = (kind: 'gain' | 'loss') => {
    const m = new Map<string, number>()
    for (const mv of moves) {
      const l = loc?.get(`${mv.lap}/${mv.other}`)
      if (mv.kind === kind && l?.corner) m.set(l.corner, (m.get(l.corner) ?? 0) + 1)
    }
    return m
  }
  const g = count('gain'), l = count('loss')
  const at = (c: string) => pts.find((p) => p.c === c)?.p
  const h = hi ? loc?.get(hi) : null
  const r = (n: number) => s * (2.4 + 0.9 * Math.sqrt(n))
  return (
    <svg viewBox={`${-8 * s} ${-8 * s} ${map.w + 16 * s} ${map.h + 16 * s}`} className="mt-3 h-auto max-h-[560px] w-full" role="img" aria-label="Track map with passes by corner">
      <polygon points={map.pts} fill="none" stroke="#2A3445" strokeWidth={3.2 * s} strokeLinejoin="round" />
      {pts.map(({ c, p }) => (
        <text key={c} x={p[0]} y={p[1] - 4.2 * s} fill="#93A0B4" fontSize={2.6 * s} textAnchor="middle" fontFamily="JetBrains Mono">{c}</text>
      ))}
      {[...g].map(([c, n]) => { const p = at(c); return p && (
        <g key={`g${c}`}><circle cx={p[0]} cy={p[1]} r={r(n)} fill={GAIN} fillOpacity={0.9} />
          <text x={p[0]} y={p[1] + 1 * s} fill="#0B0E14" fontSize={2.6 * s} fontWeight={700} textAnchor="middle" fontFamily="JetBrains Mono">{n}</text></g>
      ) })}
      {[...l].map(([c, n]) => { const p = at(c); const dx = g.has(c) ? r(g.get(c)!) + r(n) : 0; return p && (
        <g key={`l${c}`}><circle cx={p[0] + dx} cy={p[1]} r={r(n)} fill={LOSS} fillOpacity={0.9} />
          <text x={p[0] + dx} y={p[1] + 1 * s} fill="#0B0E14" fontSize={2.6 * s} fontWeight={700} textAnchor="middle" fontFamily="JetBrains Mono">{n}</text></g>
      ) })}
      {h && Number.isFinite(h.u) && <circle cx={h.u} cy={h.v} r={2.2 * s} fill="none" stroke={LINE} strokeWidth={0.9 * s} />}
    </svg>
  )
}

function PositionChart({ pos, moves, stops, n, color }: { pos: (number | null)[]; moves: Move[]; stops: number[]; n: number; color: string }) {
  const W = 1300, H = 260, PL = 48, PR = 12, PT = 12, PB = 28
  const N = Math.max(1, pos.length - 1)
  const X = (lap: number) => PL + (lap / N) * (W - PL - PR)
  const Y = (p: number) => PT + ((p - 1) / Math.max(1, n - 1)) * (H - PT - PB)
  let d = ''
  pos.forEach((p, i) => {
    if (p == null) return
    d += d ? ` H${X(i).toFixed(1)} V${Y(p).toFixed(1)}` : `M${X(i).toFixed(1)} ${Y(p).toFixed(1)}`
  })
  const gridLines = [1, 5, 10, 15, 20].filter((p) => p <= n)
  const xt = [1, ...Array.from({ length: 6 }, (_, i) => Math.round(((i + 1) * N) / 6))].filter((v, i, a) => a.indexOf(v) === i)
  return (
    <section className="rounded-xl border border-line bg-card p-4">
      <h2 className="font-head text-lg font-bold">Position by lap</h2>
      <p className="mt-1 text-xs text-mute">From the grid (lap 0) to the flag · <span style={{ color: GAIN }}>●</span> place won · <span style={{ color: LOSS }}>●</span> place lost · grey: in the pits · PIT marks a stop</p>
      <div className="mt-3 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full min-w-[640px]" role="img" aria-label="Position by lap">
          {gridLines.map((p) => (
            <g key={p}><line x1={PL} x2={W - PR} y1={Y(p)} y2={Y(p)} stroke="#232D3F" />
              <text x={PL - 10} y={Y(p) + 4} fill="#93A0B4" fontSize={12} textAnchor="end" fontFamily="JetBrains Mono">P{p}</text></g>
          ))}
          {xt.map((l) => <text key={l} x={X(l)} y={H - 6} fill="#93A0B4" fontSize={12} textAnchor="middle" fontFamily="JetBrains Mono">L{l}</text>)}
          {stops.map((l) => (
            <g key={`p${l}`}><line x1={X(l)} x2={X(l)} y1={PT} y2={H - PB} stroke="#93A0B4" strokeDasharray="3 4" strokeOpacity={0.5} />
              <text x={X(l)} y={PT + 10} fill="#93A0B4" fontSize={11} textAnchor="middle" fontFamily="JetBrains Mono">PIT</text></g>
          ))}
          <path d={d} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" />
          {moves.map((m, i) => (
            <circle key={i} cx={X(m.lap)} cy={Y(m.posAfter)} r={4} fill={m.pit ? '#93A0B4' : m.kind === 'gain' ? GAIN : LOSS}>
              <title>{`L${m.lap} ${m.kind === 'gain' ? 'won' : 'lost'} a place${m.pit ? ' (pit stop)' : ''}`}</title>
            </circle>
          ))}
        </svg>
      </div>
    </section>
  )
}
