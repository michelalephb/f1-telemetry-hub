import { flagIso } from '@/lib/flags'

/** Host country flag (3:2 SVG). Renders nothing for an unknown country. */
export default function Flag({ country, className = 'h-4' }: { country: string | null | undefined; className?: string }) {
  const iso = flagIso(country)
  if (!iso) return null
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/flags/${iso}.svg`} alt={`${country} flag`} title={country ?? ''}
      className={`${className} w-auto shrink-0 rounded-[2px] ring-1 ring-white/15`} loading="lazy" />
  )
}
