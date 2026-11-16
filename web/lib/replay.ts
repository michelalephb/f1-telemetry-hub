// Race replay: where every car is, every second (pipeline/replay.py writes replay.parquet).
// Pure helpers are exported for tests; loadReplay does the fetch.
import { parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'
import { SUPABASE_URL } from './api.ts'

export type ReplayCar = { num: string; first: number; last: number; m: Float64Array }  // m in metres covered, NaN where absent
export type Replay = { t0: number; step: number; n: number; cars: ReplayCar[] }

const num = (v: unknown) => (v == null ? NaN : typeof v === 'bigint' ? Number(v) : Number(v))

/** Columns of deltas (first value absolute, null when absent) to absolute series. */
export function decode(cols: Record<string, (number | null)[]>, step = 1): Replay {
  const t = cols._t ?? []
  let acc = 0
  const tAbs = t.map((v) => (acc += num(v)))
  const n = tAbs.length
  const cars: ReplayCar[] = []
  for (const [k, vals] of Object.entries(cols)) {
    if (k === '_t') continue
    const m = new Float64Array(n).fill(NaN)
    let s = 0, first = -1, last = -1
    for (let i = 0; i < n; i++) {
      const v = vals[i]
      if (v == null) continue
      s += num(v)
      m[i] = s
      if (first < 0) first = i
      last = i
    }
    if (first >= 0) cars.push({ num: k, first, last, m })
  }
  return { t0: tAbs[0] ?? 0, step, n, cars }
}

const cache = new Map<string, Promise<Replay | null>>()

/** Replay for a session (trace prefix), or null if it has not been built. */
export function loadReplay(prefix: string): Promise<Replay | null> {
  const url = `${SUPABASE_URL}/storage/v1/object/public/web/${prefix}replay.parquet`
  let p = cache.get(url)
  if (!p) {
    p = (async () => {
      const res = await fetch(url)
      if (!res.ok) return null
      const rows = (await parquetReadObjects({ file: await res.arrayBuffer(), compressors })) as Record<string, unknown>[]
      if (!rows.length) return null
      const cols: Record<string, (number | null)[]> = {}
      for (const k of Object.keys(rows[0])) cols[k] = rows.map((r) => (r[k] == null ? null : num(r[k])))
      return decode(cols)
    })().catch(() => null)
    cache.set(url, p)
  }
  return p
}

/** Metres covered by a car at session time t, or NaN when it is not on track. */
export function metresAt(r: Replay, c: ReplayCar, t: number): number {
  const x = (t - r.t0) / r.step
  if (x < c.first || x > c.last) return NaN
  const i = Math.floor(x), f = x - i
  const a = c.m[i], b = c.m[Math.min(i + 1, c.last)]
  return Number.isFinite(b) ? a + f * (b - a) : a
}

/** Session time at which a car first reached `metres` (inverse of metresAt, binary search). */
export function timeAt(r: Replay, c: ReplayCar, metres: number): number {
  let lo = c.first, hi = c.last
  if (metres <= c.m[lo]) return r.t0 + lo * r.step
  if (metres >= c.m[hi]) return r.t0 + hi * r.step
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (c.m[mid] < metres) lo = mid
    else hi = mid
  }
  const f = (metres - c.m[lo]) / ((c.m[hi] - c.m[lo]) || 1)
  return r.t0 + (lo + f) * r.step
}

export type CarState = {
  num: string; metres: number; onTrack: boolean; finished: boolean; out: boolean; finT?: number
}

/**
 * Every car at time t. Before a car's first sample it waits on the grid (behind the line by its slot)
 * and moves to its first sample; after its last sample it is finished (classified) or out (retired).
 */
export function stateAt(r: Replay, t: number, grid: Map<string, number | null>, classified: Set<string>): CarState[] {
  const start = r.t0 + Math.min(...r.cars.map((c) => c.first)) * r.step
  return r.cars.map((c) => {
    const ft = r.t0 + c.first * r.step, lt = r.t0 + c.last * r.step
    const g = grid.get(c.num)
    const slot = g && g > 0 ? g - 1 : 21
    if (t < ft) {
      const pre = Math.min(c.m[c.first], -12 - 8 * slot)
      const f = ft > start ? Math.max(0, (t - start) / (ft - start)) : 1
      return { num: c.num, metres: pre + f * (c.m[c.first] - pre), onTrack: true, finished: false, out: false }
    }
    if (t > lt) {
      const fin = classified.has(c.num)
      return { num: c.num, metres: c.m[c.last], onTrack: fin, finished: fin, out: !fin && t > lt + 30, finT: lt }
    }
    return { num: c.num, metres: metresAt(r, c, t), onTrack: true, finished: false, out: false }
  })
}

/**
 * Running order at time t, with laps behind the leader. No gap in seconds: the replay runs on the
 * car data clock at one sample a second, and its gaps differed from the official ones by 0.1 to 0.6 s
 * (time penalties not included either), so they are not shown.
 */
export function runningOrder(r: Replay, states: CarState[], t: number, trackM: number) {
  // Cars that took the flag on the same lap are ranked by when they finished, not where they stopped.
  const lapOf = (s: CarState) => Math.floor(s.metres / trackM)
  const live = states.filter((s) => !s.out).sort((a, b) =>
    a.finished && b.finished && lapOf(a) === lapOf(b) ? (a.finT ?? 0) - (b.finT ?? 0) : b.metres - a.metres)
  const lead = live[0]
  return live.map((s, i) => {
    let gap: string
    if (i === 0) gap = 'Leader'
    else {
      // Once both have stopped, laps behind is the difference in completed laps (a car classified
      // after stopping on its last lap is a lap down); while running, a full lap of distance.
      const laps = s.finished && lead.finished ? lapOf(lead) - lapOf(s) : Math.floor((lead.metres - s.metres) / trackM)
      gap = laps >= 1 ? `+${laps} ${laps === 1 ? 'lap' : 'laps'}` : ''
    }
    return { ...s, pos: i + 1, gap }
  })
}

/** Lap the leader is on (1 based, capped at the race distance). */
export function leaderLap(states: CarState[], trackM: number, laps: number): number {
  const m = Math.max(...states.filter((s) => !s.out).map((s) => s.metres))
  return Math.max(1, Math.min(laps, Math.floor(m / trackM) + 1))
}
