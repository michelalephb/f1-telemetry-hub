'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'
import PaceChart from '@/components/PaceChart'
import { Failed, Loading, useAsync } from '@/components/useAsync'
import { getDrivers, getEvent, getLaps, getSession, type Lap } from '@/lib/api'
import { gap, lapTime, secs, SESSION_LABEL, teamColor, TYRE } from '@/lib/format'

export default function Page() {
  return <Suspense fallback={<Loading what="session" />}><SessionView /></Suspense>
}

async function load(sid: string) {
  const session = await getSession(sid)
  if (!session || session.status !== 'ingested') throw new Error(`session ${sid} is not available`)
  const [event, drivers, laps] = await Promise.all([getEvent(session.season, session.round), getDrivers(sid), getLaps(sid)])
  return { session, event, drivers, laps }
}

function SessionView() {
  const sid = useSearchParams().get('id') ?? ''
  const { data, error, loading } = useAsync(() => load(sid), [sid])
  if (error) return <Failed error={error} />
  if (loading || !data) return <Loading what="session" />
  const { session, event, drivers, laps } = data
  const drv = new Map(drivers.map((d) => [d.driver_number, d]))

  const best = new Map<string, Lap>()
  for (const l of laps) {
    if (!l.is_accurate || l.lap_time_ms == null) continue
    const b = best.get(l.driver_number)
    if (!b || l.lap_time_ms < (b.lap_time_ms ?? Infinity)) best.set(l.driver_number, l)
  }
  const rows = [...best.values()].sort((a, b) => (a.lap_time_ms ?? 0) - (b.lap_time_ms ?? 0))
  const top = rows[0]?.lap_time_ms ?? 0
  const bestSector = (k: 'sector1_ms' | 'sector2_ms' | 'sector3_ms') =>
    Math.min(...laps.filter((l) => l.is_accurate && l[k] != null).map((l) => l[k] as number))
  const sb = { s1: bestSector('sector1_ms'), s2: bestSector('sector2_ms'), s3: bestSector('sector3_ms') }
  const theoretical = sb.s1 + sb.s2 + sb.s3
  const compareHref = rows.length >= 2 ? `/compare/?id=${sid}&a=${rows[0].driver_number}&b=${rows[1].driver_number}` : null

  const paceDrivers = rows.map((r) => {
    const d = drv.get(r.driver_number)
    return { num: r.driver_number, code: d?.abbreviation ?? r.driver_number, color: teamColor(d?.team_color) }
  })
  const paceLaps = laps
    .filter((l) => l.is_accurate && l.lap_time_ms != null && l.lap_time_ms < top * 1.07)
    .map((l) => ({ d: l.driver_number, n: l.lap_number, ms: l.lap_time_ms as number, c: l.compound }))
  const sectorCell = (v: number | null, bestV: number) => `px-2 py-2 num ${v != null && v === bestV ? 'text-purple font-bold' : 'text-ink/80'}`

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link href="/" className="text-xs text-mute hover:text-ink">← Season</Link>
          <p className="mt-2 text-xs uppercase tracking-widest text-mute">
            R{String(session.round).padStart(2, '0')} · {event?.location ?? ''}{session.track_length_m ? ` · ${(session.track_length_m / 1000).toFixed(3)} km measured line` : ''}
          </p>
          <h1 className="mt-1 font-head text-3xl font-bold">{event?.event_name ?? sid}</h1>
          <p className="mt-1 text-lg text-mute">{SESSION_LABEL[session.session_code] ?? session.session_name}</p>
        </div>
        {compareHref && (
          <Link href={compareHref} className="flex min-h-11 items-center rounded-lg bg-cyan px-4 font-semibold text-bg hover:bg-cyan/90">
            Compare telemetry →
          </Link>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Fastest lap', lapTime(top), drv.get(rows[0]?.driver_number ?? '')?.abbreviation ?? ''],
          ['Theoretical best', lapTime(theoretical), 'sum of best sectors'],
          ['Left on the table', `${((top - theoretical) / 1000).toFixed(3)} s`, 'fastest vs theoretical'],
          ['Laps analysed', `${laps.filter((l) => l.is_accurate).length}`, `of ${laps.length} timed`],
        ].map(([k, v, s]) => (
          <div key={k} className="rounded-xl border border-line bg-card p-4">
            <div className="text-xs uppercase tracking-widest text-mute">{k}</div>
            <div className="num mt-1 text-2xl">{v}</div>
            <div className="text-xs text-mute">{s}</div>
          </div>
        ))}
      </div>

      <section className="rounded-xl border border-line bg-card p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-head text-lg font-bold">Fastest laps</h2>
          <p className="text-xs text-mute">Clean laps only. <span className="text-purple">Purple</span> = session best sector. Tap a driver to compare with the fastest.</p>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
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
                    <td className="px-2 py-2">
                      <Link href={`/compare/?id=${sid}&a=${r.driver_number}&b=${vs}`} className="flex min-h-11 items-center gap-2 font-semibold hover:text-cyan">
                        <span className="h-4 w-1 rounded" style={{ background: teamColor(d?.team_color) }} />
                        {d?.abbreviation ?? r.driver_number}
                      </Link>
                    </td>
                    <td className="px-2 py-2 text-mute">{d?.team_name ?? ''}</td>
                    <td className="num px-2 py-2">{lapTime(r.lap_time_ms)}</td>
                    <td className="num px-2 py-2 text-mute">{gap(r.lap_time_ms, top)}</td>
                    <td className="num px-2 py-2 text-mute">L{r.lap_number}</td>
                    <td className="px-2 py-2">
                      {t ? (
                        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border-2 text-[11px] font-bold" style={{ borderColor: t.color, color: t.color }} title={r.compound ?? ''}>{t.label}</span>
                      ) : <span className="text-mute">—</span>}
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

      <PaceChart drivers={paceDrivers} laps={paceLaps} />
    </div>
  )
}
