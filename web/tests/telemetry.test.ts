import { test } from 'node:test'
import assert from 'node:assert/strict'
import { bisect, deltaAt, deltaTime, extrap, interp, lapTrace, type Sample } from '../lib/telemetry.ts'

test('bisect and interp', () => {
  const xs = [0, 10, 20, 30]
  assert.equal(bisect(xs, 15), 1)
  assert.equal(bisect(xs, -5), 0)
  assert.equal(bisect(xs, 99), 3)
  assert.equal(interp(15, xs, [0, 100, 200, 300]), 150)
})

const lapAt = (v: number, lap: number, L: number, offset = 0): Sample[] =>
  Array.from({ length: Math.ceil((L + 80) / (v * 0.24)) }, (_, i) => {
    const d = -40 + offset + i * v * 0.24
    return { lap_number: lap, t: 100 + (d + 40) / v, lap_dist_m: d, in_lap: d >= 0 && d < L, speed: v * 3.6, throttle: 100, brake: 0, gear: 7, drs: 0, x: d, y: 0, rpm: 10000 + i }
  })

test('lapTrace: clock reads zero at the line, other laps excluded', () => {
  const rows = [...lapAt(50, 3, 1000, 7), ...lapAt(40, 4, 1000)]
  const tr = lapTrace(rows, 3, 1000)
  assert.ok(tr.dist[0] < 0 && tr.dist[tr.dist.length - 1] > 1000)
  const zero = tr.time[bisect(tr.dist, 0)] - (tr.dist[bisect(tr.dist, 0)]) / 50
  assert.ok(Math.abs(zero) < 1e-9, String(zero))
  assert.ok(tr.speed.every((s) => s === 180))
})

test('delta at the line equals the lap time gap', () => {
  const a = lapTrace(lapAt(50, 1, 1000, 3), 1, 1000), b = lapTrace(lapAt(40, 1, 1000, 11), 1, 1000)
  assert.ok(Math.abs(deltaAt(a, b, 1000) - (1000 / 40 - 1000 / 50)) < 1e-6)
  const d = deltaTime(a, b)
  assert.ok(d[d.length - 1] > 0)
})

test('lapTrace drops repeated (frozen) samples but keeps genuine constant speed at the end of a run', () => {
  const base = lapAt(50, 1, 1000)
  // samples 20 to 24 repeat sample 19 exactly (only time and distance move on)
  const rows = base.map((r, i) => (i >= 20 && i <= 24 ? { ...base[19], t: r.t, lap_dist_m: r.lap_dist_m } : r))
  const tr = lapTrace(rows, 1, 1000)
  assert.equal(tr.dist.length, rows.length - 5)
})

test('every 2026 host country has a flag file', async () => {
  const { flagIso } = await import('../lib/flags.ts')
  const fs = await import('node:fs')
  const hosts = ['Australia', 'China', 'Japan', 'USA', 'Canada', 'Monaco', 'Spain', 'Austria', 'UK', 'Belgium', 'Hungary',
    'Netherlands', 'Italy', 'Azerbaijan', 'Malaysia', 'Singapore', 'Mexico', 'Brazil', 'Qatar', 'UAE']
  for (const c of hosts) {
    const iso = flagIso(c)
    assert.ok(iso, `no ISO code for ${c}`)
    assert.ok(fs.existsSync(new URL(`../public/flags/${iso}.svg`, import.meta.url)), `no flag file for ${c}`)
  }
})

test('qualiSegments splits on the two longest breaks', async () => {
  const { qualiSegments } = await import('../lib/segments.ts')
  const lap = (d: string, n: number, s: number) => ({ driver_number: d, lap_number: n, lap_start_s: s, lap_end_s: s + 90 })
  // Q1 0..490 with a 150 s lull, 420 s break, Q2 910..1180, 480 s break, Q3 1660..1840
  const laps = [lap('1', 1, 0), lap('1', 2, 240), lap('1', 3, 400), lap('4', 1, 910), lap('4', 2, 1090), lap('4', 3, 1660), lap('1', 4, 1750)]
  const seg = qualiSegments(laps, 'Q')
  assert.deepEqual(['1/1', '1/2', '1/3', '4/1', '4/2', '4/3', '1/4'].map((k) => seg.get(k)), [0, 0, 0, 1, 1, 2, 2])
  assert.equal(qualiSegments(laps, 'R').size, 0)
})

test('finalSegmentKeys: Q3 starts after the last lap of drivers out in Q2', async () => {
  const { finalSegmentKeys } = await import('../lib/segments.ts')
  const lap = (d: string, n: number, s: number) => ({ driver_number: d, lap_number: n, lap_start_s: s, lap_end_s: s + 90 })
  // driver 1 reaches Q3; driver 9 is out in Q2 and last runs at 2000..2090. A long red flag sits inside Q3.
  const laps = [lap('1', 1, 100), lap('1', 2, 1990), lap('9', 1, 2000), lap('1', 3, 2600), lap('1', 4, 5000)]
  const keys = finalSegmentKeys(laps, 'Q', [{ driver_number: '1', q3_ms: 80000 }, { driver_number: '9', q3_ms: null }])!
  assert.deepEqual([...keys].sort(), ['1/3', '1/4'])
  assert.equal(finalSegmentKeys(laps, 'R'), null)
})

test('lapTrace stretched to the official lap time: the gap at the line is the official gap', () => {
  const L = 1000
  const a = lapTrace(lapAt(50, 3, L), 3, L, 20.12)   // car clock says 20.0 s, timing says 20.12 s
  const b = lapTrace(lapAt(40, 3, L), 3, L, 25.31)
  assert.ok(Math.abs(extrap(L, a.dist, a.time) - 20.12) < 1e-6)
  assert.ok(Math.abs(deltaAt(a, b, L) - (25.31 - 20.12)) < 1e-6)
  const c = lapTrace(lapAt(50, 1, L), 1, L, 26)       // lap 1 from the start: 30 % off, left alone
  assert.ok(Math.abs(extrap(L, c.dist, c.time) - 20) < 1e-6)
})
