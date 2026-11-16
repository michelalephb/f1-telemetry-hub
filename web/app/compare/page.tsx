'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'
import CompareView, { type Series } from '@/components/CompareView'
import EventNav from '@/components/EventNav'
import ShareButton from '@/components/ShareButton'
import Flag from '@/components/Flag'
import { Failed, Loading, useAsync } from '@/components/useAsync'
import { getCornerMetrics, getCorners, getDrivers, getEvent, getLaps, getResults, getSession, getTrace, type Lap } from '@/lib/api'
import { finalSegmentKeys } from '@/lib/segments'
import { lapTime, pairColors, SESSION_LABEL, teamColor } from '@/lib/format'
import { deltaTime, lapTrace } from '@/lib/telemetry'
import { getOutline } from '@/lib/track'

export default function Page() {
  return <Suspense fallback={<Loading what="telemetry" />}><Compare /></Suspense>
}

async function load(sid: string, qa: string | null, qb: string | null, qla: string | null, qlb: string | null) {
  const session = await getSession(sid)
  if (!session || session.status !== 'ingested' || !session.trace_prefix) throw new Error(`telemetry for ${sid} is not available yet`)
  const [event, drivers, laps, corners, results] = await Promise.all([
    getEvent(session.season, session.round), getDrivers(sid), getLaps(sid), getCorners(sid), getResults(session.season, session.round, session.session_code),
  ])

  // Qualifying: only final segment (Q3) laps can be compared, ordered by the official result.
  const isQ = session.session_code === 'Q' || session.session_code === 'SQ'
  const finalKeys = finalSegmentKeys(laps, session.session_code, results)
  const clean = laps
    .filter((l) => l.is_accurate && l.lap_time_ms != null && (!finalKeys || finalKeys.has(`${l.driver_number}/${l.lap_number}`)))
    .sort((x, y) => (x.lap_time_ms ?? 0) - (y.lap_time_ms ?? 0))
  const withLaps = new Set(clean.map((l) => l.driver_number))
  const official = results.filter((r) => r.position != null).sort((x, y) => x.position! - y.position!).map((r) => r.driver_number).filter((d) => withLaps.has(d))
  const order = [...new Set([...official, ...clean.map((l) => l.driver_number)])]
  const a = qa && order.includes(qa) ? qa : order[0]
  const b = qb && order.includes(qb) && qb !== a ? qb : order.find((d) => d !== a)
  if (!a || !b) throw new Error('not enough clean laps to compare')
  // Qualifying: Q3 laps only, fastest first. Races and sprints: every timed lap, lap 1 by default.
  const pool = isQ ? clean : laps.filter((l) => l.lap_time_ms != null).sort((x, y) => x.lap_number - y.lap_number)
  const pick = (d: string, n: string | null): Lap =>
    pool.find((l) => l.driver_number === d && String(l.lap_number) === n) ?? pool.find((l) => l.driver_number === d)!
  const lapA = pick(a, qla), lapB = pick(b, qlb)
  const trackM = session.track_length_m ?? 5000

  const [rowsA, rowsB, metrics, outline] = await Promise.all([getTrace(session.trace_prefix, a), getTrace(session.trace_prefix, b), getCornerMetrics(sid, [lapA, lapB]), getOutline(session.season, session.round)])
  const officialS = (l: Lap) => (l.lap_time_ms != null ? l.lap_time_ms / 1000 : null)
  const tA = lapTrace(rowsA, lapA.lap_number, trackM, officialS(lapA)), tB = lapTrace(rowsB, lapB.lap_number, trackM, officialS(lapB))
  const drv = new Map(drivers.map((d) => [d.driver_number, d]))
  const [colA, colB] = pairColors(teamColor(drv.get(a)?.team_color), teamColor(drv.get(b)?.team_color))
  const mk = (d: string, l: Lap, color: string, tr: typeof tA): Series => ({
    num: d, code: drv.get(d)?.abbreviation ?? d, team: drv.get(d)?.team_name ?? '', color,
    lap: l.lap_number, lapTime: lapTime(l.lap_time_ms), lapMs: l.lap_time_ms, compound: l.compound, trace: tr,
    metrics: metrics.filter((m) => m.driver_number === d && m.lap_number === l.lap_number),
  })
  const options = order.map((d) => ({
    num: d, code: drv.get(d)?.abbreviation ?? d,
    laps: pool.filter((l) => l.driver_number === d).sort((x, y) => x.lap_number - y.lap_number).map((l) => ({
      n: l.lap_number, t: `${lapTime(l.lap_time_ms)}${!isQ && l.lap_number === 1 ? ' · start' : l.pit_in ? ' · in lap' : l.pit_out ? ' · out lap' : ''}`,
    })),
  }))
  return {
    session, event, trackM, options, isQ, rot: outline?.rot ?? 0,
    a: mk(a, lapA, colA, tA), b: mk(b, lapB, colB, tB), delta: deltaTime(tA, tB),
    corners: corners.map((c) => ({ corner: c.corner, apex_m: c.apex_m, x: c.x, y: c.y })),
  }
}

function Compare() {
  const q = useSearchParams()
  const sid = q.get('id') ?? ''
  const key = [sid, q.get('a'), q.get('b'), q.get('la'), q.get('lb')]
  const { data, error, loading } = useAsync(() => load(sid, q.get('a'), q.get('b'), q.get('la'), q.get('lb')), key)

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link href={`/session/?id=${sid}`} className="flex items-center gap-2 text-xs text-mute hover:text-ink">
          <span>←</span>
          {data && <Flag country={data.event?.country} className="h-3.5" />}
          <span>{data ? `${data.event?.event_name ?? ''} ${SESSION_LABEL[data.session.session_code] ?? ''}` : 'Session'}</span>
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <h1 className="font-head text-2xl font-bold sm:text-3xl">{data?.isQ ? `${data.session.session_code === 'SQ' ? 'SQ3' : 'Q3'} corner compare` : 'Corner compare'}</h1>
          {data && <ShareButton title={`${data.event?.event_name ?? ''}: ${data.a.code} vs ${data.b.code}`} />}
        </div>
      </div>
      {data && <EventNav season={data.session.season} round={data.session.round} sid={sid} tab="corners" />}
      {error && <Failed error={error} />}
      {loading && <Loading what="telemetry" />}
      {data && !loading && (
        <CompareView sid={sid} a={data.a} b={data.b} delta={data.delta} corners={data.corners} options={data.options}
          initialCorner={q.get('c')} trackM={data.trackM} rot={data.rot} />
      )}
    </div>
  )
}
