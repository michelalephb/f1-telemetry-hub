'use client'

import Link from 'next/link'
import { Failed, Loading, useAsync } from '@/components/useAsync'
import { getEvents, getLatestSeason, getSessions } from '@/lib/api'
import { SESSION_LABEL } from '@/lib/format'

const ORDER = ['FP1', 'FP2', 'FP3', 'SQ', 'S', 'Q', 'R']

export default function Home() {
  const { data, error, loading } = useAsync(async () => {
    const season = await getLatestSeason()
    const [events, sessions] = await Promise.all([getEvents(season), getSessions(season)])
    return { season, events, sessions }
  }, [])
  const { season, events, sessions } = data ?? { season: null, events: [], sessions: [] }
  const ready = sessions.filter((s) => s.status === 'ingested').length

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-mute">{season ?? ''} season</p>
        <h1 className="mt-1 font-head text-3xl font-bold sm:text-4xl">Every lap. Every corner.</h1>
        <p className="mt-2 text-sm text-mute">
          {loading ? ' ' : `${ready} sessions analysed. Open a session for fastest laps, race pace and two driver telemetry.`}
        </p>
      </div>
      {error && <Failed error={error} />}
      {loading && <Loading what="the season" />}
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {[...events].reverse().map((e) => {
          const ss = sessions.filter((s) => s.round === e.round).sort((a, b) => ORDER.indexOf(a.session_code) - ORDER.indexOf(b.session_code))
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
                    <Link key={s.session_id} href={`/session/?id=${s.session_id}`}
                      className="flex min-h-11 items-center rounded-lg border border-cyan/60 px-3 text-sm text-cyan hover:bg-cyan/10">
                      {SESSION_LABEL[s.session_code] ?? s.session_code}
                    </Link>
                  ) : (
                    <span key={s.session_id} title={s.status} className="flex min-h-11 items-center rounded-lg border border-line px-3 text-sm text-mute">
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
