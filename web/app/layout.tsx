import type { Metadata } from 'next'
import Link from 'next/link'
import './globals.css'

export const metadata: Metadata = {
  title: 'F1 Telemetry Hub',
  description: 'Every lap, every corner. F1 telemetry analysis.',
  robots: { index: false, follow: false },
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
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3 sm:px-6">
            <Link href="/" aria-label="F1 Telemetry Hub home" className="flex min-h-11 items-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/logo.png`} alt="F1 Telemetry Hub" className="h-6 w-auto" />
            </Link>
            <span className="ml-auto rounded border border-line px-2 py-1 font-mono text-xs text-mute">TEST BUILD · data: OpenF1</span>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-10 pt-4 text-xs text-mute sm:px-6">
          Unofficial. Not associated with Formula 1 companies. F1 and related marks are trademarks of Formula One Licensing B.V.{' '}
          Timing and telemetry: <a className="underline hover:text-ink" href="https://openf1.org">OpenF1</a>. Results and history:{' '}
          <a className="underline hover:text-ink" href="https://github.com/jolpica/jolpica-f1">Jolpica</a> and{' '}
          <a className="underline hover:text-ink" href="https://github.com/f1db/f1db">F1DB</a> (CC BY 4.0).
        </footer>
      </body>
    </html>
  )
}
