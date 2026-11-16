// Real data check: loads a session exactly as the website does (publishable key + public trace
// files) and asserts known facts. node --experimental-strip-types scripts/verify.ts 2026_20_R
import assert from 'node:assert/strict'
import { getCornerMetrics, getCorners, getDrivers, getLaps, getResults, getSession, getTrace, SUPABASE_URL } from '../lib/api.ts'
import { cornerAt, lapClock, movesOf, ordersByLap, passPoint } from '../lib/race.ts'
import { finalSegmentKeys } from '../lib/segments.ts'
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

// Qualifying: our Q3 laps must reproduce the official Q3 times of the top of the order
if (s.session_code === 'Q') {
  const res = (await getResults(s.season, s.round, 'Q')).filter((r) => r.q3_ms != null).sort((x, y) => x.position! - y.position!)
  if (!res.length) {
    console.log('official classification not in yet; Q3 check skipped')
  } else {
    const all = await getResults(s.season, s.round, 'Q')
    const keys = finalSegmentKeys(laps, 'Q', all)!
    for (const r of res) {
      const mine = laps.filter((l) => l.driver_number === r.driver_number && l.lap_time_ms != null && keys.has(`${l.driver_number}/${l.lap_number}`))
      const ours = Math.min(...mine.map((l) => l.lap_time_ms!))
      console.log(`P${r.position} ${r.driver_code}: official Q3 ${r.q3_ms} ms, our best Q3 lap ${ours} ms`)
      assert.ok(Math.abs(ours - r.q3_ms!) <= 50, `Q3 time for ${r.driver_code} within 50 ms of official`)
    }
  }
}
// Race story: our running order at the flag must match the official classification, and most
// on track moves must be found on the map.
if (s.session_code === 'R' || s.session_code === 'S') {
  const res = (await getResults(s.season, s.round, s.session_code)).filter((r) => r.position != null).sort((x, y) => x.position! - y.position!)
  const orders = ordersByLap(laps, new Map(res.map((r) => [r.driver_number, r.grid])))
  const flag = orders[orders.length - 1]
  const leadLap = res.filter((r) => r.laps === res[0].laps).map((r) => r.driver_number)
  const ours = flag.filter((d) => leadLap.includes(d))
  const off = leadLap.filter((d, i) => ours[i] !== d)
  console.log(`order at the flag (lead lap): ours ${ours.map(code).join(' ')} | official ${leadLap.map(code).join(' ')}`)
  assert.deepEqual(ours.slice(0, 3), leadLap.slice(0, 3), 'podium order from lap times matches the official result')
  assert.ok(off.length <= 2, `at most 2 lead lap places differ (time penalties), got ${off.length}`)
  const climb = (r: (typeof res)[number]) => (r.grid && r.grid > 0 ? r.grid : res.length) - r.position!
  const me = [...res].sort((x, y) => climb(y) - climb(x))[0].driver_number
  const moves = movesOf(me, orders, laps).filter((m) => !m.pit)
  const mine = await getTrace(s.trace_prefix, me)
  let found = 0
  for (const m of moves) {
    const p = passPoint(lapClock(mine, m.lap), lapClock(await getTrace(s.trace_prefix, m.other), m.lap), m.kind)
    if (p) found++
    console.log(`  ${code(me)} L${m.lap} ${m.kind === 'gain' ? 'passed' : 'lost to'} ${code(m.other)}: ${p ? `T${cornerAt(p.d, corners, L)} at ${p.d.toFixed(0)} m` : 'not seen'}`)
  }
  console.log(`race story for ${code(me)}: ${moves.length} on track moves, ${found} located`)
  assert.ok(moves.length === 0 || found / moves.length >= 0.7, 'at least 70 % of on track moves located')
}
const outline = await fetch(`${SUPABASE_URL}/storage/v1/object/public/web/tracks/${s.season}/${s.round}.json`)
console.log(`track outline: HTTP ${outline.status}${outline.ok ? '' : ' (built by the track outlines workflow)'}`)

console.log(`OK in ${Date.now() - t0} ms`)
