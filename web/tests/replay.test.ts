import { test } from 'node:test'
import assert from 'node:assert/strict'
import { decode, leaderLap, metresAt, runningOrder, stateAt, timeAt } from '../lib/replay.ts'

// Two cars on a 1000 m track, 1 s steps from t = 100. Car 1: 50 m/s. Car 44: 40 m/s, starts 2 s later, retires at t = 130.
const n = 60
const t = [100, ...Array(n - 1).fill(1)]
const c1 = [0, ...Array(n - 1).fill(50)]
const c44 = [null, null, 0, ...Array(28).fill(40), ...Array(n - 31).fill(null)]
const r = decode({ _t: t, '1': c1, '44': c44 })

test('decode and lookups', () => {
  assert.equal(r.t0, 100)
  assert.equal(r.cars.length, 2)
  const a = r.cars.find((c) => c.num === '1')!, b = r.cars.find((c) => c.num === '44')!
  assert.equal(metresAt(r, a, 110.5), 525)
  assert.ok(Number.isNaN(metresAt(r, b, 101)))       // not started yet
  assert.equal(b.last, 30)
  assert.equal(timeAt(r, a, 525), 110.5)
})

test('state, order and gaps', () => {
  const grid = new Map<string, number | null>([['1', 1], ['44', 2]])
  const s = stateAt(r, 101, grid, new Set(['1']))
  const car44 = s.find((x) => x.num === '44')!
  assert.ok(car44.metres < 0 && car44.onTrack)             // waiting on the grid behind the line
  const o = runningOrder(r, stateAt(r, 120, grid, new Set(['1'])), 120, 1000)
  assert.deepEqual(o.map((x) => x.num), ['1', '44'])
  assert.equal(o[0].gap, 'Leader')
  assert.equal(o[1].gap, '')                                 // same lap: no seconds gap (not official)
  const later = stateAt(r, 170, grid, new Set(['1']))
  assert.ok(later.find((x) => x.num === '44')!.out)          // retired, gone after 30 s
  assert.equal(leaderLap(later, 1000, 3), 3)
})
