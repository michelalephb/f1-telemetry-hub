import Link from 'next/link'
import { getEvents, getSessions } from '@/lib/db'
import { SESSION_LABEL } from '@/lib/format'

export const dynamic = "force-dynamic"

const SEASON = 2026
const ORDER = ['FP1', 'FP2', 'FP3', 'SQ', 'S', 'Q', 'R']

export default async function Home() {
  const [events, sessions] = await Promise.all([getEvents(SEASON), getSessions(SEASON)])
  const byRound = new Map<number, typeof sessions>()
  for (const s of sessions) byRound.set(s.round, [...(byRound.get(s.round) ?? []), s])
  const rounds = [...events].reverse()
  const ready = sessions.filter((s) => s.status === 'ingested').length

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-mute">{SEASON} season</p>
        <h1 className="mt-1 font-head text-3xl font-bold sm:text-4xl">Every lap. Every corner.</h1>
        <p className="mt-2 text-sm text-mute">{ready} sessions analysed. Open a session for fastest laps, race pace and two driver telemetry.</p>
      </div>
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {rounds.map((e) => {
          const ss = (byRound.get(e.round) ?? []).sort((a, b) => ORDER.indexOf(a.session_code) - ORDER.indexOf(b.session_code))
          const any = ss.some((s) => s.status === 'ingested')
          return (
            <li key={e.round} className={`rounded-xl border border-line bg-card p-4 ${any ? '' : 'opacity-60'}`}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-xs text-mute">R{String(e.round).padStart(2, '0')} · {e.event_date}</span>
                <span className="text-xs text-mute">{e.location ?? e.country}</span>
              </div>
              <h2 className="mt-1 font-head text-lg font-bold">{e.event_name}</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                {ss.map((s) =>
                  s.status === 'ingested' ? (
                    <Link key={s.session_id} href={`/s/${s.session_id}`}
                      className="flex min-h-11 items-center rounded-lg border border-cyan/60 px-3 text-sm text-cyan hover:bg-cyan/10">
                      {SESSION_LABEL[s.session_code] ?? s.session_code}
                    </Link>
                  ) : (
                    <span key={s.session_id} className="flex min-h-11 items-center rounded-lg border border-line px-3 text-sm text-mute"
                      title={s.status}>
                      {SESSION_LABEL[s.session_code] ?? s.session_code}
                    </span>
                  ),
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
