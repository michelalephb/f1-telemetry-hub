// Qualifying segments from the running itself: Q1, Q2 and Q3 are separated by the two longest
// breaks with no car on a timed lap. OpenF1 does not label segments, so this is derived.

type L = { driver_number: string; lap_number: number; lap_start_s: number | null; lap_end_s: number | null }

/** Map "driver/lap" to segment index 0, 1, 2 (Q1, Q2, Q3). Empty for non qualifying sessions. */
export function qualiSegments(laps: L[], code: string): Map<string, number> {
  const out = new Map<string, number>()
  if (code !== 'Q' && code !== 'SQ') return out
  const iv = laps
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
