// Driver badge: team colour square with the race number (our own design, no photos or F1 artwork).

/** Dark text on light team colours, white on dark ones. */
export function badgeText(hex: string): string {
  const v = parseInt(hex.replace('#', ''), 16)
  if (!Number.isFinite(v)) return '#FFFFFF'
  const r = (v >> 16) & 255, g = (v >> 8) & 255, b = v & 255
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 ? '#0B0E14' : '#FFFFFF'
}

export default function DriverBadge({ num, color, size = 24, title }: { num: string; color: string; size?: number; title?: string }) {
  return (
    <span aria-hidden={title ? undefined : true} title={title}
      className="inline-flex shrink-0 items-center justify-center font-head font-bold leading-none"
      style={{ width: size, height: size, borderRadius: Math.round(size / 4), background: color, color: badgeText(color), fontSize: Math.round(size * (num.length > 1 ? 0.48 : 0.56)) }}>
      {num}
    </span>
  )
}
