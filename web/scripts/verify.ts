// Real data check: reads Supabase exactly as the app does and asserts known facts.
// node --experimental-strip-types --conditions=react-server scripts/verify.ts 2026_20_R
import assert from 'node:assert/strict'
import { getCornerMetrics, getCorners, getDrivers, getLaps, getSession, readCar, readDist, readPos } from '../lib/db.ts'
import { buildLapTrace, deltaAt, extrap } from '../lib/telemetry.ts'

const sid = process.argv[2] ?? '2026_20_R'
const t0 = Date.now()
const s = await getSession(sid)
assert.ok(s && s.status === 'ingested', `${sid} not ingested`)
const [drivers, laps, corners] = await Promise.all([getDrivers(sid), getLaps(sid), getCorners(sid)])
assert.equal(laps.length, s.n_laps, 'lap paging returns every lap')
const clean = laps.filter((l) => l.is_accurate && l.lap_time_ms != null).sort((a, b) => a.lap_time_ms! - b.lap_time_ms!)
const A = clean[0], B = clean.find((l) => l.driver_number !== A.driver_number)!
const code = (n: string) => drivers.find((d) => d.driver_number === n)?.abbreviation ?? n
console.log(`${sid}: ${drivers.length} drivers, ${laps.length} laps, ${corners.length} corners; A ${code(A.driver_number)} L${A.lap_number} ${A.lap_time_ms} ms, B ${code(B.driver_number)} L${B.lap_number} ${B.lap_time_ms} ms`)

let t = Date.now()
const [car, pos, dist, metrics] = await Promise.all([
  readCar(s.car_path!, [A.driver_number, B.driver_number]),
  readPos(s.pos_path!, [A.driver_number, B.driver_number]),
  readDist(s.dist_path!, [A, B]),
  getCornerMetrics(sid, [A, B]),
])
console.log(`parquet + metrics: ${Date.now() - t} ms (cold); car ${car.length}, pos ${pos.length}, dist ${dist.length}, metrics ${metrics.length}`)
t = Date.now()
await Promise.all([readCar(s.car_path!, [A.driver_number, B.driver_number]), readPos(s.pos_path!, [A.driver_number]), readDist(s.dist_path!, [A, B])])
console.log(`same request again (cached): ${Date.now() - t} ms`)

const tr = (l: typeof A) => buildLapTrace(
  dist.filter((r) => r.driver_number === l.driver_number && r.lap_number === l.lap_number),
  car.filter((r) => r.driver_number === l.driver_number),
  pos.filter((r) => r.driver_number === l.driver_number), l.lap_start_s!, s.track_length_m!)
const ta = tr(A), tb = tr(B)
for (const [n, x] of [['A', ta], ['B', tb]] as const) {
  const span = x.dist[x.dist.length - 1] - x.dist[0]
  console.log(`trace ${n}: ${x.dist.length} samples, ${x.dist[0].toFixed(0)}..${x.dist[x.dist.length - 1].toFixed(0)} m, lap time ${x.time[x.time.length - 1].toFixed(3)} s, max ${Math.max(...x.speed)} km/h, xy finite ${x.x.every(Number.isFinite)}`)
  assert.ok(x.dist.length > 200, 'enough samples')
  assert.ok(span > 0.95 * s.track_length_m!, 'trace covers the lap')
  assert.ok(x.x.every(Number.isFinite) && x.y.every(Number.isFinite), 'map positions')
}
const atLine = deltaAt(ta, tb, s.track_length_m!)
const expected = (B.lap_time_ms! - A.lap_time_ms!) / 1000
console.log(`delta at line ${atLine.toFixed(3)} s, official lap time difference ${expected.toFixed(3)} s, error ${((atLine - expected) * 1000).toFixed(0)} ms`)
for (const [n, x, l] of [['A', ta, A], ['B', tb, B]] as const) {
  const t = extrap(s.track_length_m!, x.dist, x.time)
  console.log(`trace ${n} time at line ${t.toFixed(3)} s vs official ${(l.lap_time_ms! / 1000).toFixed(3)} s`)
}
assert.ok(Math.abs(atLine - expected) < 0.1, 'delta at the line within 0.1 s of the official gap')
assert.equal(metrics.length, 2 * corners.length, 'one metric row per corner per lap')
console.log(`OK in ${Date.now() - t0} ms`)
