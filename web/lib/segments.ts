// Qualifying segments from the running itself: Q1, Q2 and Q3 are separated by the two longest
// breaks with no car on a timed lap. OpenF1 does not label segments, so this is derived.

type L = { driver_number: string; lap_number: number; lap_start_s: number | null; lap_end_s: number | null; lap_time_ms?: number | null }

/**
 * Laps that are real running: the feed also logs "laps" that span a whole stop in the garage
 * (Miami 2026: 671 s and 918 s), which bridge the breaks between segments. A lap counts as running
 * when it lasted under twice the session's fastest lap.
 */
function running<T extends L>(laps: T[]): T[] {
  const dur = (l: L) => (l.lap_start_s != null && l.lap_end_s != null ? l.lap_end_s - l.lap_start_s : NaN)
  const timed = laps.map((l) => l.lap_time_ms).filter((v): v is number => v != null && v > 0)
  const best = timed.length ? Math.min(...timed) / 1000 : NaN
  if (!Number.isFinite(best)) return laps
  return laps.filter((l) => dur(l) < 2 * best)
}

/** Map "driver/lap" to segment index 0, 1, 2 (Q1, Q2, Q3). Empty for non qualifying sessions. */
export function qualiSegments(laps: L[], code: string): Map<string, number> {
  const out = new Map<string, number>()
  if (code !== 'Q' && code !== 'SQ') return out
  const iv = running(laps)
    .filter((l) => l.lap_start_s != null && l.lap_end_s != null)
    .map((l) => [l.lap_start_s as number, l.lap_end_s as number] as const)
    .sort((a, b) => a[0] - b[0])
  if (!iv.length) return out
  // merge overlapping activity, collect the gaps between busy periods
  const gaps: { at: number; len: number }[] = []
  let end = iv[0][1]
  for (const [s, e] of iv.slice(1)) {
    if (s > end) gaps.push({ at: (s + end) / 2, len: s - end })
    end = Math.max(end, e)
  }
  const cuts = gaps.filter((g) => g.len >= 120).sort((a, b) => b.len - a.len).slice(0, 2).map((g) => g.at).sort((a, b) => a - b)
  for (const l of laps) {
    if (l.lap_start_s == null) continue
    out.set(`${l.driver_number}/${l.lap_number}`, cuts.filter((c) => l.lap_start_s! > c).length)
  }
  return out
}

export const segLabel = (code: string, i: number) => `${code === 'SQ' ? 'SQ' : 'Q'}${i + 1}`

type R = { driver_number: string; q3_ms: number | null; position?: number | null }

/** Q3 (and SQ3) runs with the top ten of Q2. */
const FINAL_SEGMENT_CARS = 10

/**
 * Keys ("driver/lap") of laps in the final segment (Q3 / SQ3), or null for non qualifying sessions.
 * With the official result: Q3 starts after the last lap of any driver who did not reach Q3
 * (they stop running when Q2 ends), so red flags or long stoppages cannot move the boundary.
 * Without it: fall back to the two longest breaks in running.
 */
export function finalSegmentKeys(laps: L[], code: string, results: R[] = []): Set<string> | null {
  if (code !== 'Q' && code !== 'SQ') return null
  // A driver can reach Q3 and set no time (Miami 2026: Hadjar), so the top ten count too
  const inQ3 = new Set(results.filter((r) => r.q3_ms != null || (r.position != null && r.position <= FINAL_SEGMENT_CARS)).map((r) => r.driver_number))
  if (inQ3.size > 0 && results.length > inQ3.size) {
    const cut = Math.max(...running(laps).filter((l) => !inQ3.has(l.driver_number) && l.lap_end_s != null).map((l) => l.lap_end_s as number))
    if (Number.isFinite(cut)) {
      return new Set(laps.filter((l) => inQ3.has(l.driver_number) && l.lap_start_s != null && l.lap_start_s >= cut).map((l) => `${l.driver_number}/${l.lap_number}`))
    }
  }
  const seg = qualiSegments(laps, code)
  const last = seg.size ? Math.max(...seg.values()) : 0
  return new Set([...seg].filter(([, v]) => v === last).map(([k]) => k))
}

type S = { lap_time_ms: number | null; sector1_ms: number | null; sector2_ms: number | null; sector3_ms: number | null }

/** True when all three sectors are present and add up to the lap time (within 2 ms of rounding). */
export function sectorsAddUp(l: S): boolean {
  if (l.lap_time_ms == null || l.sector1_ms == null || l.sector2_ms == null || l.sector3_ms == null) return false
  return Math.abs(l.sector1_ms + l.sector2_ms + l.sector3_ms - l.lap_time_ms) <= 2
}
