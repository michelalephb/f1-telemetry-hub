// Google Analytics 4, loaded only after the visitor accepts on the consent banner.
// The measurement ID is public by design (it sits in every page that uses Analytics).
export const GA_ID = 'G-97ZQ2RDVX6'
const KEY = 'f1th_analytics_consent'   // 'yes' | 'no'

type W = Window & { dataLayer?: unknown[]; gtag?: (...a: unknown[]) => void }

export function consent(): 'yes' | 'no' | null {
  try { const v = window.localStorage.getItem(KEY); return v === 'yes' || v === 'no' ? v : null } catch { return null }
}
export function setConsent(v: 'yes' | 'no') {
  try { window.localStorage.setItem(KEY, v) } catch { /* private mode: ask again next visit */ }
  if (v === 'yes') start()
}

/** Load Analytics once. Page views, including moves between pages, come from GA's enhanced measurement. */
export function start() {
  const w = window as W
  if (w.gtag) return
  w.dataLayer = w.dataLayer || []
  // gtag must push the arguments object itself, not an array
  w.gtag = function gtag() { w.dataLayer!.push(arguments) } // eslint-disable-line prefer-rest-params
  w.gtag('js', new Date())
  w.gtag('config', GA_ID)
  const s = document.createElement('script')
  s.async = true
  s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`
  document.head.appendChild(s)
}

/** Feature event; does nothing unless the visitor accepted. */
export function track(name: string, params: Record<string, string | number> = {}) {
  const w = window as W
  if (w.gtag) w.gtag('event', name, params)
}
