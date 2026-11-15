import { test } from 'node:test'
import assert from 'node:assert/strict'
import { bisect, buildLapTrace, deltaTime, interp } from '../lib/telemetry.ts'

test('bisect and interp', () => {
  const xs = [0, 10, 20, 30]
  assert.equal(bisect(xs, 15), 1)
  assert.equal(bisect(xs, -5), 0)
  assert.equal(bisect(xs, 99), 3)
  assert.equal(interp(15, xs, [0, 100, 200, 300]), 150)
})

test('buildLapTrace joins car, distance and position by time', () => {
  const car = [0, 0.24, 0.48, 0.72].map((t, i) => ({ driver_number: '1', t, speed: 100 + i, throttle: 100, brake: i === 2 ? 100 : 0, gear: 5, rpm: 10000, drs: 0 }))
  const dist = car.map((c, i) => ({ driver_number: '1', lap_number: 3, t: c.t, lap_dist_m: i * 7, in_lap: i > 0 }))
  const pos = [{ driver_number: '1', t: 0, x: 0, y: 0 }, { driver_number: '1', t: 1, x: 100, y: -100 }]
  const tr = buildLapTrace(dist, car, pos, 0.24)
  assert.deepEqual(tr.dist, [7, 14, 21])
  assert.deepEqual(tr.brake, [0, 1, 0])
  assert.ok(Math.abs(tr.time[0]) < 1e-9)
  assert.ok(Math.abs(tr.x[1] - 48) < 1e-6)
})

test('deltaTime is positive when B is slower', () => {
  const mk = (v: number) => {
    const dist = Array.from({ length: 50 }, (_, i) => i * 10)
    return { dist, time: dist.map((d) => d / v), speed: [], throttle: [], brake: [], gear: [], drs: [], x: [], y: [] }
  }
  const d = deltaTime(mk(50), mk(40))
  assert.ok(d[49] > 0)
  assert.ok(Math.abs(d[49] - (490 / 40 - 490 / 50)) < 1e-6)
})
