import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cornerAt, lapClock, movesOf, ordersByLap, passPoint, positions, type RaceLap } from '../lib/race.ts'

const lap = (d: string, n: number, end: number, extra: Partial<RaceLap> = {}): RaceLap =>
  ({ driver_number: d, lap_number: n, lap_start_s: end - 90, lap_end_s: end, pit_in: false, pit_out: false, ...extra })

test('order, positions and moves: on track pass, pit stop, retirement', () => {
  const grid = new Map<string, number | null>([['1', 1], ['4', 2], ['16', 3], ['44', 0]])
  const laps = [
    // lap 1: 4 passes 1; 44 (pit lane start) stays last
    lap('4', 1, 100), lap('1', 1, 101), lap('16', 1, 102), lap('44', 1, 110),
    // lap 2: 4 pits (in lap), 1 and 16 go by; 44 retires after lap 1
    lap('1', 2, 191), lap('16', 2, 192), lap('4', 2, 215, { pit_in: true }),
  ]
  const o = ordersByLap(laps, grid)
  assert.deepEqual(o[0], ['1', '4', '16', '44'])
  assert.deepEqual(o[1], ['4', '1', '16', '44'])
  assert.deepEqual(o[2], ['1', '16', '4'])
  assert.deepEqual(positions('4', o), [2, 1, 3])
  const m = movesOf('4', o, laps)
  assert.deepEqual(m.map((x) => [x.lap, x.other, x.kind, x.pit]), [[1, '1', 'gain', false], [2, '1', 'loss', true], [2, '16', 'loss', true]])
  // 16 gains nothing from 44 retiring
  assert.equal(movesOf('16', o, laps).filter((x) => x.kind === 'gain' && x.other === '44').length, 0)
})

test('passPoint finds where the time gap changes sign', () => {
  // me: 60 m/s then 70 m/s after 500 m; other: 65 m/s throughout, 0.1 s ahead at the line
  const rows = (v: (d: number) => number, t0: number, who: number) => {
    const out = []
    let t = t0
    for (let d = 0; d <= 2000; d += 10) { out.push({ lap_number: 3, t, lap_dist_m: d, x: d, y: who }); t += 10 / v(d) }
    return out
  }
  const me = lapClock(rows((d) => (d < 500 ? 60 : 70), 100.1, 0), 3)
  const other = lapClock(rows(() => 65, 100, 1), 3)
  const p = passPoint(me, other, 'gain')
  assert.ok(p && p.d > 500 && p.d < 2000, `pass at ${p?.d}`)
  assert.equal(passPoint(me, other, 'loss'), null)
})

test('cornerAt picks the corner the move belongs to', () => {
  const cs = [{ corner: '1', apex_m: 300 }, { corner: '4', apex_m: 1200 }, { corner: '12', apex_m: 3900 }]
  assert.equal(cornerAt(250, cs, 4300), '1')
  assert.equal(cornerAt(1250, cs, 4300), '4')   // just past the apex
  assert.equal(cornerAt(4200, cs, 4300), '1')   // after the last corner: next lap's first
})
