// Race story: running order lap by lap, the moves of one driver, and where on track each pass happened.
// Pure functions, no I/O (unit tested in tests/race.test.ts).
import { bisect } from './telemetry.ts'

export type RaceLap = {
  driver_number: string; lap_number: number; lap_start_s: number | null; lap_end_s: number | null
  pit_in: boolean; pit_out: boolean
}

/** Running order at the end of every lap; index 0 is the starting grid. */
/** Line crossing times are only good to about 0.2 s (checked against the official finishing gaps). */
export const TIMING_RES_S = 0.25

/**
 * finish: the official classification order. On the last lap, cars that crossed within TIMING_RES_S
 * of each other are put in that order, since the timestamps cannot separate them (Baku 2026: Russell
 * won by 0.196 s, the timestamps had Verstappen 3 ms ahead).
 */
export function ordersByLap(laps: RaceLap[], grid: Map<string, number | null>, finish: string[] = []): string[][] {
  const byDriver = new Map<string, Map<number, RaceLap>>()
  for (const l of laps) {
    if (!byDriver.has(l.driver_number)) byDriver.set(l.driver_number, new Map())
    byDriver.get(l.driver_number)!.set(l.lap_number, l)
  }
  const crossed = (d: string, k: number): number | null => {
    const m = byDriver.get(d)!
    return m.get(k)?.lap_end_s ?? m.get(k + 1)?.lap_start_s ?? null
  }
  const drivers = [...byDriver.keys()]
  // Grid 0 or missing means pit lane start: behind everyone who started on the grid.
  const g = (d: string) => { const v = grid.get(d); return v && v > 0 ? v : 100 + Number(d) }
  const out: string[][] = [[...drivers].sort((a, b) => g(a) - g(b))]
  const nLaps = Math.max(0, ...laps.map((l) => l.lap_number))
  for (let k = 1; k <= nLaps; k++) {
    const at = drivers.map((d) => [d, crossed(d, k)] as const).filter((x): x is readonly [string, number] => x[1] != null)
    at.sort((a, b) => a[1] - b[1])
    if (k === nLaps && finish.length) {
      const idx = (d: string) => { const i = finish.indexOf(d); return i < 0 ? Infinity : i }
      for (let swapped = true; swapped;) {
        swapped = false
        for (let i = 0; i + 1 < at.length; i++) {
          if (at[i + 1][1] - at[i][1] < TIMING_RES_S && idx(at[i + 1][0]) < idx(at[i][0])) {
            [at[i], at[i + 1]] = [at[i + 1], at[i]]
            swapped = true
          }
        }
      }
    }
    out.push(at.map(([d]) => d))
  }
  return out
}

export type Move = { lap: number; other: string; kind: 'gain' | 'loss'; pit: boolean; posAfter: number }

/**
 * Places won and lost by one driver, lap by lap. Only drivers present at both ends of a lap count,
 * so a retirement ahead is not a pass. pit = either car stopped on that lap: the order changed in the pits.
 */
export function movesOf(driver: string, orders: string[][], laps: RaceLap[]): Move[] {
  const pitted = new Set(laps.filter((l) => l.pit_in || l.pit_out).map((l) => `${l.driver_number}/${l.lap_number}`))
  const out: Move[] = []
  for (let k = 1; k < orders.length; k++) {
    const prev = orders[k - 1], cur = orders[k]
    const ip = prev.indexOf(driver), ic = cur.indexOf(driver)
    if (ip < 0 || ic < 0) continue
    const both = new Set(prev.filter((d) => cur.includes(d)))
    const aheadPrev = new Set(prev.slice(0, ip).filter((d) => both.has(d)))
    const aheadCur = new Set(cur.slice(0, ic).filter((d) => both.has(d)))
    const mePit = pitted.has(`${driver}/${k}`)
    for (const d of aheadPrev) if (!aheadCur.has(d)) out.push({ lap: k, other: d, kind: 'gain', pit: mePit || pitted.has(`${d}/${k}`), posAfter: ic + 1 })
    for (const d of aheadCur) if (!aheadPrev.has(d)) out.push({ lap: k, other: d, kind: 'loss', pit: mePit || pitted.has(`${d}/${k}`), posAfter: ic + 1 })
  }
  return out
}

/** Position by lap (index = lap, 0 = grid), null where the driver was not running. */
export function positions(driver: string, orders: string[][]): (number | null)[] {
  return orders.map((o) => { const i = o.indexOf(driver); return i < 0 ? null : i + 1 })
}

type Row = { lap_number: number; t: number; lap_dist_m: number; x: number; y: number }
export type LapClock = { dist: number[]; t: number[]; x: number[]; y: number[] }

/** One lap of one driver on the session clock (not zeroed), distance forced non decreasing. */
export function lapClock(rows: Row[], lap: number): LapClock {
  const sel = rows.filter((r) => r.lap_number === lap).sort((a, b) => a.t - b.t)
  const out: LapClock = { dist: [], t: [], x: [], y: [] }
  let last = -Infinity
  for (const r of sel) {
    const d = Math.max(r.lap_dist_m, last)
    if (d === last) continue  // repeated distance would make time ambiguous
    last = d
    out.dist.push(d); out.t.push(r.t); out.x.push(r.x); out.y.push(r.y)
  }
  return out
}

const at = (c: LapClock, d: number, k: 't' | 'x' | 'y') => {
  const i = bisect(c.dist, d)
  const j = Math.min(i + 1, c.dist.length - 1)
  const f = j === i ? 0 : (d - c.dist[i]) / (c.dist[j] - c.dist[i])
  return c[k][i] + f * (c[k][j] - c[k][i])
}

/**
 * Where on the lap `me` got ahead of `other` (kind gain) or fell behind (loss): the last distance
 * at which the gap in time to reach that point changes sign. null when it cannot be seen in the data.
 */
export function passPoint(me: LapClock, other: LapClock, kind: 'gain' | 'loss', step = 5): { d: number; x: number; y: number; early?: boolean } | null {
  if (me.dist.length < 5 || other.dist.length < 5) return null
  const d0 = Math.max(me.dist[0], other.dist[0]), d1 = Math.min(me.dist[me.dist.length - 1], other.dist[other.dist.length - 1])
  let found: number | null = null
  let prev = at(me, d0, 't') - at(other, d0, 't')
  const g1 = at(me, d1, 't') - at(other, d1, 't')
  // Already swapped where the data starts (the start: cars leave the grid before the traces begin)
  const early = kind === 'gain' ? prev <= 0 && g1 <= 0 : prev >= 0 && g1 >= 0
  for (let d = d0 + step; d <= d1; d += step) {
    const g = at(me, d, 't') - at(other, d, 't')
    const flipped = kind === 'gain' ? prev > 0 && g <= 0 : prev < 0 && g >= 0
    if (flipped) found = d - step * (g / (g - prev || 1))
    prev = g
  }
  if (found == null && early) return { d: d0, x: at(me, d0, 'x'), y: at(me, d0, 'y'), early: true }
  return found == null ? null : { d: found, x: at(me, found, 'x'), y: at(me, found, 'y') }
}

/** Corner a pass belongs to: the first apex at or after the point (allowing 80 m past the apex). */
export function cornerAt(d: number, corners: { corner: string; apex_m: number }[], trackM: number): string | null {
  if (!corners.length) return null
  const s = [...corners].sort((a, b) => a.apex_m - b.apex_m)
  const dd = ((d % trackM) + trackM) % trackM
  return (s.find((c) => c.apex_m >= dd - 80) ?? s[0]).corner
}
