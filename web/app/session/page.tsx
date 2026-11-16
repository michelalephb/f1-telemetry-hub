'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'
import EventNav from '@/components/EventNav'
import Flag from '@/components/Flag'
import PaceChart from '@/components/PaceChart'
import { Failed, Loading, useAsync } from '@/components/useAsync'
import { getDrivers, getEvent, getLaps, getResults, getSession, type Driver, type Lap, type Result } from '@/lib/api'
import { gap, lapTime, secs, SESSION_LABEL, teamColor, TYRE } from '@/lib/format'
import { finalSegmentKeys, segLabel } from '@/lib/segments'

export default function Page() {
  return <Suspense fallback={<Loading what="session" />}><SessionView /></Suspense>
}

async function load(sid: string) {
  const session = await getSession(sid)
  if (!session || session.status !== 'ingested') throw new Error(`session ${sid} is not available`)
  const [event, drivers, laps, results] = await Promise.all([
    getEvent(session.season, session.round), getDrivers(sid), getLaps(sid), getResults(session.season, session.round, session.session_code),
  ])
  return { session, event, drivers, laps, results }
}

function DriverCell({ d, num, href }: { d: Driver | undefined; num: string; href: string }) {
  return (
    <Link href={href} className="flex min-h-11 items-center gap-2 font-semibold hover:text-cyan">
      <span className="h-4 w-1 rounded" style={{ background: teamColor(d?.team_color) }} />
      {d?.abbreviation ?? num}
    </Link>
  )
}

function SessionView() {
  const sid = useSearchParams().get('id') ?? ''
  const { data, error, loading } = useAsync(() => load(sid), [sid])
  if (error) return <Failed error={error} />
  if (loading || !data) return <Loading what="session" />
  const { session, event, drivers, laps, results } = data
  const code = session.session_code
  const isQ = code === 'Q' || code === 'SQ'
  const drv = new Map(drivers.map((d) => [d.driver_number, d]))
  const finalKeys = finalSegmentKeys(laps, code, results)

  // Qualifying: only the final segment (Q3 / SQ3) counts. Other sessions: every clean lap.
  const allClean = laps.filter((l) => l.is_accurate && l.lap_time_ms != null && (!finalKeys || finalKeys.has(`${l.driver_number}/${l.lap_number}`)))
  const pool = allClean
  const best = new Map<string, Lap>()
  for (const l of pool) {
    const b = best.get(l.driver_number)
    if (!b || l.lap_time_ms! < b.lap_time_ms!) best.set(l.driver_number, l)
  }
  const rows = [...best.values()].sort((a, b) => a.lap_time_ms! - b.lap_time_ms!)
  const top = rows[0]?.lap_time_ms ?? 0
  const sessionBest = allClean.reduce<Lap | null>((m, l) => (!m || l.lap_time_ms! < m.lap_time_ms! ? l : m), null)
  const bestSector = (k: 'sector1_ms' | 'sector2_ms' | 'sector3_ms') => Math.min(...pool.filter((l) => l[k] != null).map((l) => l[k] as number))
  const sb = { s1: bestSector('sector1_ms'), s2: bestSector('sector2_ms'), s3: bestSector('sector3_ms') }
  const theoretical = sb.s1 + sb.s2 + sb.s3

  // The official classification drives the order and the default comparison
  const classified = results.filter((r) => r.position != null).sort((a, b) => a.position! - b.position!)
  const cmp = (a: string, b: string) => {
    const la = best.get(a), lb = best.get(b)
    return `/compare/?id=${sid}&a=${a}&b=${b}${la ? `&la=${la.lap_number}` : ''}${lb ? `&lb=${lb.lap_number}` : ''}`
  }
  const leadA = classified[0]?.driver_number ?? rows[0]?.driver_number
  const leadB = classified[1]?.driver_number ?? rows[1]?.driver_number
  const compareHref = leadA && leadB ? cmp(leadA, leadB) : null

  const q3 = segLabel(code, 2)
  const pole = isQ && classified[0] ? (classified[0].q3_ms ?? classified[0].q2_ms ?? classified[0].q1_ms) : null
  const cards: [string, string, string][] = isQ
    ? [
        ['Pole', lapTime(pole), classified[0] ? `${classified[0].driver_code ?? ''} · official` : 'classification pending'],
        [`Fastest ${q3} lap`, lapTime(sessionBest?.lap_time_ms), sessionBest ? `${drv.get(sessionBest.driver_number)?.abbreviation ?? ''} · L${sessionBest.lap_number}` : ''],
        [`Theoretical best ${q3}`, lapTime(theoretical), 'sum of best sectors'],
        [`${q3} laps`, `${allClean.length}`, `clean laps by ${rows.length} drivers`],
      ]
    : [
        ['Winner', classified[0]?.driver_code ?? '—', classified[0] ? `${classified[0].constructor ?? ''} · official` : 'classification pending'],
        ['Fastest lap', lapTime(sessionBest?.lap_time_ms), sessionBest ? `${drv.get(sessionBest.driver_number)?.abbreviation ?? ''} · L${sessionBest.lap_number}` : ''],
        ['Theoretical best', lapTime(theoretical), 'sum of best sectors'],
        ['Laps analysed', `${allClean.length}`, `of ${laps.length} timed`],
      ]

  const paceDrivers = (classified.length ? classified.map((r) => r.driver_number) : rows.map((r) => r.driver_number))
    .filter((n) => allClean.some((l) => l.driver_number === n))
    .map((n) => ({ num: n, code: drv.get(n)?.abbreviation ?? n, color: teamColor(drv.get(n)?.team_color) }))
  const fastestAny = sessionBest?.lap_time_ms ?? 0
  const paceLaps = allClean.filter((l) => l.lap_time_ms! < fastestAny * 1.07).map((l) => ({ d: l.driver_number, n: l.lap_number, ms: l.lap_time_ms!, c: l.compound }))
  const sectorCell = (v: number | null, bestV: number) => `px-2 py-2 num ${v != null && v === bestV ? 'text-purple font-bold' : 'text-ink/80'}`

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link href="/" className="text-xs text-mute hover:text-ink">← Season</Link>
          <p className="mt-2 text-xs uppercase tracking-widest text-mute">
            R{String(session.round).padStart(2, '0')} · {event?.location ?? ''}{session.track_length_m ? ` · ${(session.track_length_m / 1000).toFixed(3)} km measured line` : ''}
          </p>
          <h1 className="mt-1 flex items-center gap-3 font-head text-3xl font-bold"><Flag country={event?.country} className="h-7" />{event?.event_name ?? sid}</h1>
          <p className="mt-1 text-lg text-mute">{SESSION_LABEL[code] ?? session.session_name}</p>
        </div>
        {compareHref && (
          <Link href={compareHref} className="flex min-h-11 items-center rounded-lg bg-cyan px-4 font-semibold text-bg hover:bg-cyan/90">
            {isQ ? 'Compare pole lap →' : 'Compare telemetry →'}
          </Link>
        )}
      </div>

      <EventNav season={session.season} round={session.round} sid={sid} tab="overview" />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {cards.map(([k, v, s]) => (
          <div key={k} className="rounded-xl border border-line bg-card p-4">
            <div className="text-xs uppercase tracking-widest text-mute">{k}</div>
            <div className="num mt-1 text-2xl">{v}</div>
            <div className="text-xs text-mute">{s}</div>
          </div>
        ))}
      </div>

      {classified.length > 0 ? (
        <section className="rounded-xl border border-line bg-card p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-head text-lg font-bold">Official classification</h2>
            <p className="text-xs text-mute">{isQ ? `Final order with ${q3} times. Tap a driver to compare ${q3} laps with pole.` : 'Tap a driver to compare with the winner.'}</p>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-mute">
                  {(isQ ? ['Pos', 'Driver', 'Team', q3, 'Gap to pole'] : ['Pos', 'Driver', 'Team', 'Grid', 'Laps', 'Status', 'Pts']).map((h) => <th key={h} className="px-2 py-2 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {classified.map((r: Result, i) => {
                  const d = drv.get(r.driver_number)
                  const vs = i === 0 ? classified[1]?.driver_number : classified[0].driver_number
                  const out = r.q3_ms == null ? (r.q2_ms != null ? `out in ${segLabel(code, 1)}` : r.q1_ms != null ? `out in ${segLabel(code, 0)}` : 'no time') : null
                  return (
                    <tr key={r.driver_number} className="border-t border-line/70">
                      <td className="num px-2 py-2 text-mute">{r.position_text ?? r.position}</td>
                      <td className="px-2 py-2">{isQ && r.q3_ms == null ? <span className="flex min-h-11 items-center gap-2 font-semibold text-ink/70"><span className="h-4 w-1 rounded" style={{ background: teamColor(d?.team_color) }} />{d?.abbreviation ?? r.driver_code}</span> : <DriverCell d={d} num={r.driver_code ?? r.driver_number} href={vs ? cmp(r.driver_number, vs) : '#'} />}</td>
                      <td className="px-2 py-2 text-mute">{d?.team_name ?? r.constructor ?? ''}</td>
                      {isQ ? (
                        <>
                          <td className={`num px-2 py-2 ${i === 0 ? 'text-purple font-bold' : ''}`}>{out ? <span className="font-body text-mute">{out}</span> : lapTime(r.q3_ms)}</td>
                          <td className="num px-2 py-2 text-mute">{i === 0 || r.q3_ms == null || pole == null ? '' : gap(r.q3_ms, pole)}</td>
                        </>
                      ) : (
                        <>
                          <td className="num px-2 py-2 text-mute">{r.grid ?? '—'}</td>
                          <td className="num px-2 py-2 text-mute">{r.laps ?? '—'}</td>
                          <td className="px-2 py-2 text-mute">{r.status ?? ''}</td>
                          <td className="num px-2 py-2">{r.points ?? ''}</td>
                        </>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        (code === 'R' || code === 'Q' || code === 'S') && (
          <p className="rounded-lg border border-line px-4 py-3 text-sm text-mute">The official classification is not in yet; it usually follows within a day.</p>
        )
      )}

      <section className="rounded-xl border border-line bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-head text-lg font-bold">{isQ ? `Best ${q3} lap per driver` : 'Fastest clean lap per driver'}</h2>
            <p className="text-xs text-mute">
              Ranked by lap time. <span className="text-purple">Purple</span> = best sector.
              {isQ && ` ${q3} starts after the last lap of the drivers knocked out in ${segLabel(code, 1)}.`}
            </p>
          </div>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-mute">
                {['#', 'Driver', 'Team', 'Lap time', 'Gap', 'Lap', 'Tyre', 'S1', 'S2', 'S3'].map((h) => <th key={h} className="px-2 py-2 font-medium">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const d = drv.get(r.driver_number)
                const t = TYRE[r.compound ?? ''] ?? null
                const vs = i === 0 ? rows[1]?.driver_number : rows[0].driver_number
                return (
                  <tr key={r.driver_number} className="border-t border-line/70">
                    <td className="num px-2 py-2 text-mute">{i + 1}</td>
                    <td className="px-2 py-2"><DriverCell d={d} num={r.driver_number} href={`/compare/?id=${sid}&a=${r.driver_number}&b=${vs ?? ''}&la=${r.lap_number}&lb=${best.get(vs ?? '')?.lap_number ?? ''}`} /></td>
                    <td className="px-2 py-2 text-mute">{d?.team_name ?? ''}</td>
                    <td className="num px-2 py-2">{lapTime(r.lap_time_ms)}</td>
                    <td className="num px-2 py-2 text-mute">{gap(r.lap_time_ms, top)}</td>
                    <td className="num px-2 py-2 text-mute">L{r.lap_number}</td>
                    <td className="px-2 py-2">
                      {t ? <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border-2 text-[11px] font-bold" style={{ borderColor: t.color, color: t.color }} title={r.compound ?? ''}>{t.label}</span> : <span className="text-mute">—</span>}
                    </td>
                    <td className={sectorCell(r.sector1_ms, sb.s1)}>{secs(r.sector1_ms)}</td>
                    <td className={sectorCell(r.sector2_ms, sb.s2)}>{secs(r.sector2_ms)}</td>
                    <td className={sectorCell(r.sector3_ms, sb.s3)}>{secs(r.sector3_ms)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {!isQ && <PaceChart drivers={paceDrivers} laps={paceLaps} />}
    </div>
  )
}
