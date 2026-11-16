'use client'

import { useEffect, useState } from 'react'
import { getOutline, type Outline } from '@/lib/track'

/** Small layout of the circuit for a round. Keeps its space while loading or if not built yet. */
export default function TrackThumb({ season, round, className = '' }: { season: number; round: number; className?: string }) {
  const [o, setO] = useState<Outline | null | undefined>(undefined)
  useEffect(() => {
    let live = true
    getOutline(season, round).then((v) => live && setO(v))
    return () => { live = false }
  }, [season, round])
  const start = o?.pts.split(' ', 1)[0]?.split(',').map(Number)
  return (
    <div className={`flex items-center justify-center ${className}`} aria-hidden="true">
      {o && (
        <svg viewBox={`0 0 ${o.w} ${o.h}`} className="h-full w-full" preserveAspectRatio="xMidYMid meet">
          <polygon points={o.pts} fill="none" stroke="#E8ECF2" strokeOpacity="0.85" strokeWidth={Math.max(o.w, o.h) / 40} strokeLinejoin="round" />
          {start && <circle cx={start[0]} cy={start[1]} r={Math.max(o.w, o.h) / 28} fill="#00E5FF" />}
        </svg>
      )}
    </div>
  )
}
