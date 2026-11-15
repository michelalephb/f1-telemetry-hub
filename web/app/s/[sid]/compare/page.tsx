import Link from 'next/link'
import { notFound } from 'next/navigation'
import CompareView, { type Series } from '@/components/CompareView'
import { getCornerMetrics, getCorners, getDrivers, getEvent, getLaps, getSession, readCar, readDist, readPos, type Lap } from '@/lib/db'
import { lapTime, pairColors, SESSION_LABEL, teamColor } from '@/lib/format'
import { buildLapTrace, deltaTime } from '@/lib/telemetry'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type SP = { a?: string; b?: string; la?: string; lb?: string; c?: string }

export default async function ComparePage({ params, searchParams }: { params: Promise<{ sid: string }>; searchParams: Promise<SP> }) {
  const { sid } = await params
  const sp = await searchParams
  const session = await getSession(sid)
  if (!session || session.status !== 'ingested' || !session.car_path || !session.pos_path || !session.dist_path) notFound()
  const [event, drivers, laps, corners] = await Promise.all([getEvent(session.season, session.round), getDrivers(sid), getLaps(sid), getCorners(sid)])

  const clean = laps.filter((l) => l.is_accurate && l.lap_time_ms != null)
  const bestOf = (d: string) => clean.filter((l) => l.driver_number === d).sort((x, y) => (x.lap_time_ms ?? 0) - (y.lap_time_ms ?? 0))[0]
  const order = [...new Set(clean.sort((x, y) => (x.lap_time_ms ?? 0) - (y.lap_time_ms ?? 0)).map((l) => l.driver_number))]
  const a = sp.a && order.includes(sp.a) ? sp.a : order[0]
  const b = sp.b && order.includes(sp.b) && sp.b !== a ? sp.b : order.find((d) => d !== a)
  if (!a || !b) notFound()
  const pick = (d: string, n?: string): Lap => clean.find((l) => l.driver_number === d && String(l.lap_number) === n) ?? bestOf(d)
  const lapA = pick(a, sp.la), lapB = pick(b, sp.lb)

  const [car, pos, dist, metrics] = await Promise.all([
    readCar(session.car_path, [a, b]),
    readPos(session.pos_path, [a, b]),
    readDist(session.dist_path, [lapA, lapB]),
    getCornerMetrics(sid, [lapA, lapB]),
  ])
  const drv = new Map(drivers.map((d) => [d.driver_number, d]))
  const [colA, colB] = pairColors(teamColor(drv.get(a)?.team_color), teamColor(drv.get(b)?.team_color))

  const trace = (l: Lap) => {
    const lo = (l.lap_start_s ?? 0) - 15, hi = (l.lap_end_s ?? 0) + 15
    return buildLapTrace(
      dist.filter((r) => r.driver_number === l.driver_number && r.lap_number === l.lap_number),
      car.filter((r) => r.driver_number === l.driver_number && r.t >= lo && r.t <= hi),
      pos.filter((r) => r.driver_number === l.driver_number && r.t >= lo && r.t <= hi),
      l.lap_start_s ?? 0,
    )
  }
  const tA = trace(lapA), tB = trace(lapB)
  const mk = (d: string, l: Lap, color: string, tr: ReturnType<typeof trace>): Series => ({
    num: d, code: drv.get(d)?.abbreviation ?? d, team: drv.get(d)?.team_name ?? '', color,
    lap: l.lap_number, lapTime: lapTime(l.lap_time_ms), compound: l.compound, trace: tr,
    metrics: metrics.filter((m) => m.driver_number === d && m.lap_number === l.lap_number),
  })

  const options = order.map((d) => ({
    num: d, code: drv.get(d)?.abbreviation ?? d,
    laps: clean.filter((l) => l.driver_number === d).sort((x, y) => x.lap_number - y.lap_number).map((l) => ({ n: l.lap_number, t: lapTime(l.lap_time_ms) })),
  }))

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link href={`/s/${sid}`} className="text-xs text-mute hover:text-ink">← {event?.event_name} {SESSION_LABEL[session.session_code]}</Link>
        <h1 className="mt-2 font-head text-2xl font-bold sm:text-3xl">Telemetry compare</h1>
      </div>
      <CompareView
        sid={sid}
        a={mk(a, lapA, colA, tA)}
        b={mk(b, lapB, colB, tB)}
        delta={deltaTime(tA, tB)}
        corners={corners.map((c) => ({ corner: c.corner, apex_m: c.apex_m, x: c.x, y: c.y }))}
        options={options}
        initialCorner={sp.c ?? null}
        trackM={session.track_length_m ?? Math.max(...tA.dist, 0)}
      />
    </div>
  )
}
