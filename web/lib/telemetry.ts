// Pure telemetry helpers, no I/O. Shared by the server pages and the unit tests.

/** One row of a per driver trace file (pipeline: trace_<driver>.parquet). */
export type Sample = {
  lap_number: number; t: number; lap_dist_m: number; in_lap: boolean
  speed: number; throttle: number; brake: number; gear: number; drs: number; x: number; y: number; rpm?: number
}

/** One lap of one driver: every raw car sample with its distance, lap time and map position. */
export type LapTrace = {
  dist: number[]      // m from the timing line
  time: number[]      // s since lap start
  speed: number[]
  throttle: number[]
  brake: number[]     // 0 or 1
  gear: number[]
  drs: number[]
  x: number[]         // map position (FastF1 / OpenF1 units, 1/10 m), interpolated at the car sample time
  y: number[]
}

/** Index of the last element <= v in an ascending array (clamped). */
export function bisect(a: ArrayLike<number>, v: number): number {
  let lo = 0, hi = a.length - 1
  if (hi < 0) return -1
  if (v <= a[0]) return 0
  if (v >= a[hi]) return hi
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (a[mid] <= v) lo = mid
    else hi = mid
  }
  return lo
}

/** Linear interpolation of ys at x over ascending xs (clamped at the ends). */
export function interp(x: number, xs: ArrayLike<number>, ys: ArrayLike<number>): number {
  const n = xs.length
  if (n === 0) return NaN
  if (x <= xs[0]) return ys[0]
  if (x >= xs[n - 1]) return ys[n - 1]
  const i = bisect(xs, x)
  const f = (x - xs[i]) / (xs[i + 1] - xs[i] || 1)
  return ys[i] + f * (ys[i + 1] - ys[i])
}

/**
 * One lap from a driver's samples: from just before the timing line to just after the next crossing,
 * with the lap clock at zero at distance 0 (interpolated), so two laps line up exactly at the line.
 */
export function lapTrace(rows: Sample[], lap: number, trackM: number): LapTrace {
  const sel = rows.filter((r) => r.lap_number === lap && r.lap_dist_m >= -40 && r.lap_dist_m <= trackM + 40).sort((a, b) => a.t - b.t)
  const out: LapTrace = { dist: [], time: [], speed: [], throttle: [], brake: [], gear: [], drs: [], x: [], y: [] }
  let lastD = -Infinity
  let prev: Sample | null = null
  for (const r of sel) {
    // The feed sometimes repeats the previous sample unchanged for several ticks; a moving car never
    // holds speed, rpm, gear, throttle and brake all identical, so keep the first and drop the copies.
    // The line then runs straight to the next real value instead of drawing a false plateau and a jump.
    const frozen = prev != null && r.speed > 0 && r.speed === prev.speed && r.rpm === prev.rpm && r.gear === prev.gear
      && r.throttle === prev.throttle && r.brake === prev.brake
    prev = r
    if (frozen) continue
    const d = Math.max(r.lap_dist_m, lastD) // distance never runs backwards
    lastD = d
    out.dist.push(d)
    out.time.push(r.t)
    out.speed.push(r.speed)
    out.throttle.push(r.throttle)
    out.brake.push(r.brake > 0 ? 1 : 0)
    out.gear.push(r.gear)
    out.drs.push(r.drs)
    out.x.push(r.x)
    out.y.push(r.y)
  }
  if (out.dist.length > 1) {
    const t0 = extrap(0, out.dist, out.time)
    for (let i = 0; i < out.time.length; i++) out.time[i] -= t0
  }
  return out
}

/** Like interp but extends the first or last segment linearly beyond the ends. */
export function extrap(x: number, xs: number[], ys: number[]): number {
  const n = xs.length
  if (n < 2) return ys[0] ?? NaN
  const [i, j] = x < xs[0] ? [0, 1] : x > xs[n - 1] ? [n - 2, n - 1] : [-1, -1]
  if (i < 0) return interp(x, xs, ys)
  return ys[i] + ((x - xs[i]) / (xs[j] - xs[i] || 1)) * (ys[j] - ys[i])
}

/** Time gap of B to A at distance d, with linear extension past the ends. */
export function deltaAt(a: LapTrace, b: LapTrace, d: number): number {
  return extrap(d, b.dist, b.time) - extrap(d, a.dist, a.time)
}

/**
 * Running time gap of B to A at A's sample distances: positive = B behind (A faster so far).
 * Both traces must be ascending in distance.
 */
export function deltaTime(a: LapTrace, b: LapTrace): number[] {
  if (!a.dist.length || !b.dist.length) return []
  return a.dist.map((d, i) => interp(d, b.dist, b.time) - a.time[i])
}

/** Clamp a distance range to the samples available and return index bounds. */
export function rangeIdx(dist: number[], lo: number, hi: number): [number, number] {
  return [Math.max(0, bisect(dist, lo)), Math.min(dist.length - 1, bisect(dist, hi) + 1)]
}
