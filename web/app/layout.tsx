import type { Metadata } from 'next'
import Link from 'next/link'
import './globals.css'
import BugReport from '@/components/BugReport'

// Link previews (WhatsApp, iMessage, X, LinkedIn, Slack): the preview image, favicon and Apple icon come from the
// files next to this layout (opengraph-image.png, twitter-image.png, icon.png, apple-icon.png). The preview is the
// F1 mark on a square 1200 x 1200 tile, under 300 KB (WhatsApp drops larger ones); square, so no app crops the
// mark, and X uses its square "summary" card for the same reason (Michel, 20 Nov 2026).
const SITE = process.env.NEXT_PUBLIC_BASE_PATH === '' ? 'https://f1telemetryhub.com' : 'https://michelalephb.github.io'
const DESCRIPTION = 'Every F1 session, decoded in telemetry. Braking points, pedal traces, pole laps.'

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: 'F1 Telemetry Hub',
  description: DESCRIPTION,
  openGraph: {
    type: 'website',
    siteName: 'F1 Telemetry Hub',
    title: 'F1 Telemetry Hub',
    description: DESCRIPTION,
    url: '/',
  },
  twitter: {
    card: 'summary',
    title: 'F1 Telemetry Hub',
    description: DESCRIPTION,
  },
  // Launch switch: search engines may index the site only when it is served from its own domain
  // (Pages base path ""), i.e. f1telemetryhub.com. The github.io test build stays noindex.
  robots: process.env.NEXT_PUBLIC_BASE_PATH === '' ? { index: true, follow: true } : { index: false, follow: false },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap"
        />
      </head>
      <body>
        <header className="border-b border-line">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 sm:px-6">
            <Link href="/" aria-label="F1 Telemetry Hub home" className="flex min-h-11 items-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/logo.png`} alt="F1 Telemetry Hub" className="h-6 w-auto" />
            </Link>
            <nav aria-label="Main" className="-ml-3 flex w-full flex-wrap items-center gap-1 text-sm sm:ml-auto sm:w-auto">
              <Link href="/" className="flex min-h-11 items-center rounded-lg px-3 text-mute hover:text-ink">Season</Link>
              <Link href="/historique/" className="flex min-h-11 items-center rounded-lg px-3 text-mute hover:text-ink"><span className="sm:hidden">History</span><span className="hidden sm:inline">F1 History Analytics</span></Link>
              <a href="https://www.instagram.com/f1telemetryhub/" target="_blank" rel="noopener noreferrer"
                className="ml-auto flex min-h-11 items-center gap-1.5 rounded-lg border border-line px-3 text-ink hover:border-ink/60 sm:ml-1">
                Instagram
                <svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M7 17 17 7" /><path d="M8 7h9v9" />
                </svg>
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-10 pt-4 text-xs text-mute sm:px-6">
          <div className="mb-4 flex flex-wrap items-start gap-3 border-t border-line pt-6">
            <BugReport />
            <a href="https://www.instagram.com/f1telemetryhub/" target="_blank" rel="noopener noreferrer"
              className="flex min-h-11 items-center rounded-lg border border-line px-4 text-sm text-ink hover:border-ink/60">@f1telemetryhub on Instagram</a>
          </div>
          Unofficial. Not associated with Formula 1 companies. F1 and related marks are trademarks of Formula One Licensing B.V.{' '}
          Timing and telemetry: <a className="underline hover:text-ink" href="https://openf1.org">OpenF1</a>. Results and history:{' '}
          <a className="underline hover:text-ink" href="https://github.com/jolpica/jolpica-f1">Jolpica</a> and{' '}
          <a className="underline hover:text-ink" href="https://github.com/f1db/f1db">F1DB</a> (CC BY 4.0).
        </footer>
      </body>
    </html>
  )
}
