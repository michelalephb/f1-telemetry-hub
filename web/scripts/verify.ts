// Real data check: loads a session exactly as the website does (publishable key + public trace
// files) and asserts known facts. node --experimental-strip-types scripts/verify.ts 2026_20_R
import assert from 'node:assert/strict'
import { getCornerMetrics, getCorners, getDrivers, getLaps, getSession, getTrace, SUPABASE_URL } from '../lib/api.ts'
import { deltaAt, extrap, lapTrace } from '../lib/telemetry.ts'

const sid = process.argv[2] ?? '2026_20_R'
const t0 = Date.now()
const s = await getSession(sid)
assert.ok(s && s.status === 'ingested', `${sid} not ingested`)
assert.ok(s.trace_prefix, `${sid} has no trace files yet`)
const [drivers, laps, corners] = await Promise.all([getDrivers(sid), getLaps(sid), getCorners(sid)])
assert.equal(laps.length, s.n_laps, 'lap paging returns every lap')
const clean = laps.filter((l) => l.is_accurate && l.lap_time_ms != null).sort((a, b) => a.lap_time_ms! - b.lap_time_ms!)
const A = clean[0], B = clean.find((l) => l.driver_number !== A.driver_number)!
const code = (n: string) => drivers.find((d) => d.driver_number === n)?.abbreviation ?? n
console.log(`${sid}: ${drivers.length} drivers, ${laps.length} laps, ${corners.length} corners; A ${code(A.driver_number)} L${A.lap_number} ${A.lap_time_ms} ms, B ${code(B.driver_number)} L${B.lap_number} ${B.lap_time_ms} ms`)

// The browser fetches trace files cross origin: the response must allow it.
const url = `${SUPABASE_URL}/storage/v1/object/public/web/${s.trace_prefix}trace_${A.driver_number}.parquet`
const head = await fetch(url, { headers: { Origin: 'https://michelalephb.github.io' } })
const acao = head.headers.get('access-control-allow-origin')
console.log(`trace file: HTTP ${head.status}, ${(Number(head.headers.get('content-length') ?? 0) / 1e3).toFixed(0)} kB, access-control-allow-origin: ${acao}`)
assert.equal(head.status, 200)
assert.ok(acao === '*' || acao === 'https://michelalephb.github.io', 'CORS allows the site')

let t = Date.now()
const [ra, rb, metrics] = await Promise.all([getTrace(s.trace_prefix, A.driver_number), getTrace(s.trace_prefix, B.driver_number), getCornerMetrics(sid, [A, B])])
console.log(`two trace files + metrics: ${Date.now() - t} ms; rows ${ra.length} + ${rb.length}, metrics ${metrics.length}`)

const L = s.track_length_m!
const ta = lapTrace(ra, A.lap_number, L), tb = lapTrace(rb, B.lap_number, L)
for (const [n, x, l] of [['A', ta, A], ['B', tb, B]] as const) {
  const atLine = extrap(L, x.dist, x.time)
  console.log(`trace ${n}: ${x.dist.length} samples, ${x.dist[0].toFixed(0)}..${x.dist[x.dist.length - 1].toFixed(0)} m, max ${Math.max(...x.speed)} km/h, time at line ${atLine.toFixed(3)} s vs official ${(l.lap_time_ms! / 1000).toFixed(3)} s`)
  assert.ok(x.dist.length > 200, 'enough samples')
  assert.ok(x.dist[0] <= 0 && x.dist[x.dist.length - 1] >= L, 'trace spans the lap')
  assert.ok(x.x.every(Number.isFinite) && x.y.every(Number.isFinite), 'map positions')
  assert.ok(Math.abs(atLine - l.lap_time_ms! / 1000) < 0.1, 'lap time from the trace within 0.1 s of official')
}
const d = deltaAt(ta, tb, L), expected = (B.lap_time_ms! - A.lap_time_ms!) / 1000
console.log(`delta at line ${d.toFixed(3)} s vs official gap ${expected.toFixed(3)} s`)
assert.ok(Math.abs(d - expected) < 0.05, 'delta at the line within 50 ms of the official gap')
assert.equal(metrics.length, 2 * corners.length, 'one metric row per corner per lap')
console.log(`OK in ${Date.now() - t0} ms`)
