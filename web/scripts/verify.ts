// Real data check: loads a session exactly as the website does (publishable key + public trace
// files) and asserts known facts. node --experimental-strip-types scripts/verify.ts 2026_20_R
import assert from 'node:assert/strict'
import { getCornerMetrics, getCorners, getDrivers, getLaps, getResults, getSession, getTrace, SUPABASE_URL } from '../lib/api.ts'
import { cornerAt, lapClock, movesOf, ordersByLap, passPoint } from '../lib/race.ts'
import { loadReplay, runningOrder, stateAt } from '../lib/replay.ts'
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
// Same lap number, two drivers (the compare page in a race): the gap at the line must be the official gap.
if (s.session_code === 'R' || s.session_code === 'S') {
  const res = (await getResults(s.season, s.round, s.session_code)).filter((r) => r.position != null).sort((x, y) => x.position! - y.position!)
  const [p1, p2] = [res[0].driver_number, res[1].driver_number]
  const common = laps.filter((l) => l.driver_number === p1 && l.lap_time_ms != null && l.lap_number > 1 && !l.pit_in && !l.pit_out)
    .map((l) => [l, laps.find((m) => m.driver_number === p2 && m.lap_number === l.lap_number && m.lap_time_ms != null && !m.pit_in && !m.pit_out)] as const)
    .filter(([, m]) => m)
  const [la, lb] = common[Math.floor(common.length * 0.7)]
  const [r1, r2] = await Promise.all([getTrace(s.trace_prefix, p1), getTrace(s.trace_prefix, p2)])
  const t1 = lapTrace(r1, la.lap_number, L, la.lap_time_ms! / 1000), t2 = lapTrace(r2, lb!.lap_number, L, lb!.lap_time_ms! / 1000)
  const g = deltaAt(t1, t2, L), off = (lb!.lap_time_ms! - la.lap_time_ms!) / 1000
  console.log(`L${la.lap_number} ${code(p1)} vs ${code(p2)}: gap at the line ${g.toFixed(3)} s, official ${off.toFixed(3)} s`)
  assert.ok(Math.abs(g - off) < 0.005, 'race lap compare ends on the official gap')
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
  let found = 0, seeable = 0
  // data covers the lap: 90 % of the distance, and samples until the car crossed the line (no 40 s hole at the end)
  const spans = (c: { dist: number[]; t: number[] }, d: string, k: number) => {
    const end = laps.find((l) => l.driver_number === d && l.lap_number === k)?.lap_end_s
    return c.dist.length > 0 && c.dist[c.dist.length - 1] - c.dist[0] > 0.9 * L && (end == null || c.t[c.t.length - 1] >= end - 3)
  }
  for (const m of moves) {
    const cm = lapClock(mine, m.lap), co = lapClock(await getTrace(s.trace_prefix, m.other), m.lap)
    const p = passPoint(cm, co, m.kind)
    const ok = spans(cm, me, m.lap) && spans(co, m.other, m.lap)
    if (ok) seeable++
    if (p && ok) found++
    else {
      const ends = (c: typeof cm) => c.dist.length ? `${c.dist[0].toFixed(0)}..${c.dist[c.dist.length - 1].toFixed(0)} m, t ${c.t[0].toFixed(1)}..${c.t[c.t.length - 1].toFixed(1)}` : 'no samples'
      const lap = (d: string) => laps.find((l) => l.driver_number === d && l.lap_number === m.lap)
      console.log(`    not seen: me ${ends(cm)} (lap end ${lap(me)?.lap_end_s?.toFixed(1)}), other ${ends(co)} (lap end ${lap(m.other)?.lap_end_s?.toFixed(1)})`)
    }
    console.log(`  ${code(me)} L${m.lap} ${m.kind === 'gain' ? 'passed' : 'lost to'} ${code(m.other)}: ${p ? `T${cornerAt(p.d, corners, L)} at ${p.d.toFixed(0)} m${p.early ? ' (already ahead where the data starts)' : ''}` : 'not seen'}`)
  }
  console.log(`race story for ${code(me)}: ${moves.length} on track moves, ${seeable} with both cars' data covering the lap, ${found} of those located`)
  assert.ok(seeable === 0 || found / seeable >= 0.8, 'at least 80 % of on track moves with full data located')
}
// Replay: at the moment the winner takes the flag, the replay's top 3 must be the official podium.
if (s.session_code === 'R' || s.session_code === 'S') {
  const rp = await loadReplay(s.trace_prefix)
  if (!rp) console.log('replay: not built yet (track outlines and replays workflow)')
  else {
    const res = (await getResults(s.season, s.round, s.session_code)).filter((r) => r.position != null).sort((x, y) => x.position! - y.position!)
    const win = laps.filter((l) => l.driver_number === res[0].driver_number && l.lap_end_s != null).sort((x, y) => y.lap_number - x.lap_number)[0]
    const tFlag = win.lap_end_s! + 0.5
    const st = stateAt(rp, tFlag, new Map(res.map((r) => [r.driver_number, r.grid])), new Set(res.map((r) => r.driver_number)))
    const ord = runningOrder(rp, st, tFlag, L)
    console.log(`replay: ${rp.cars.length} cars, ${rp.n} s; order at the flag ${ord.slice(0, 5).map((o) => `${code(o.num)} ${o.gap}`).join(', ')}`)
    assert.deepEqual(ord.slice(0, 3).map((o) => o.num), res.slice(0, 3).map((r) => r.driver_number), 'replay podium at the flag matches the official result')
  }
}
const outline = await fetch(`${SUPABASE_URL}/storage/v1/object/public/web/tracks/${s.season}/${s.round}.json`)
console.log(`track outline: HTTP ${outline.status}${outline.ok ? '' : ' (built by the track outlines workflow)'}`)

console.log(`OK in ${Date.now() - t0} ms`)
