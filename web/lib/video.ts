// Race replay video: draws the replay on a canvas and records it with MediaRecorder, all in the browser.

export type VideoCar = { num: string; code: string; color: string; fg: string; u: number; v: number; me: boolean; pos: number }
export type VideoRow = { pos: number; num: string; code: string; color: string; fg: string; gap: string }
export type VideoFrame = { cars: VideoCar[]; rows: VideoRow[]; lap: string; sub: string }

export const VIDEO_W = 1080, VIDEO_H = 1350  // 4:5, the tallest feed format on Instagram

/** Best recording format this browser can make: mp4 where possible, else webm. */
export function videoFormat(): { mime: string; ext: string } | null {
  if (typeof MediaRecorder === 'undefined') return null
  for (const [mime, ext] of [['video/mp4;codecs=avc1', 'mp4'], ['video/mp4', 'mp4'], ['video/webm;codecs=vp9', 'webm'], ['video/webm', 'webm']] as const) {
    if (MediaRecorder.isTypeSupported(mime)) return { mime, ext }
  }
  return null
}

type Scene = { title: string; outlinePts: [number, number][]; ow: number; oh: number; logo: HTMLImageElement | null }

export function drawFrame(ctx: CanvasRenderingContext2D, s: Scene, f: VideoFrame, accent: string) {
  const W = VIDEO_W, H = VIDEO_H
  ctx.fillStyle = '#0B0E14'; ctx.fillRect(0, 0, W, H)
  // header: logo, lap
  if (s.logo?.complete && s.logo.naturalWidth) {
    const h = 46, w = (s.logo.naturalWidth / s.logo.naturalHeight) * h
    ctx.drawImage(s.logo, 60, 52, w, h)
  }
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = '#93A0B4'; ctx.font = '500 22px "JetBrains Mono", monospace'; ctx.textAlign = 'right'
  ctx.fillText('LAP', W - 60, 70)
  ctx.fillStyle = '#E8ECF2'; ctx.font = '700 44px "JetBrains Mono", monospace'
  ctx.fillText(f.lap, W - 60, 112)
  ctx.textAlign = 'left'
  ctx.fillStyle = '#E8ECF2'; ctx.font = '700 46px "Space Grotesk", Inter, sans-serif'
  ctx.fillText(s.title, 60, 186)
  ctx.fillStyle = '#93A0B4'; ctx.font = '400 26px Inter, sans-serif'
  ctx.fillText(f.sub, 60, 226)

  // map, fitted in its box
  const bx = 60, by = 260, bw = W - 120, bh = 700
  const k = Math.min(bw / s.ow, bh / s.oh)
  const ox = bx + (bw - s.ow * k) / 2, oy = by + (bh - s.oh * k) / 2
  const X = (u: number) => ox + u * k, Y = (v: number) => oy + v * k
  ctx.lineJoin = 'round'
  ctx.strokeStyle = '#232D3F'; ctx.lineWidth = 26
  ctx.beginPath(); s.outlinePts.forEach(([u, v], i) => (i ? ctx.lineTo(X(u), Y(v)) : ctx.moveTo(X(u), Y(v)))); ctx.closePath(); ctx.stroke()
  for (const c of [...f.cars].sort((a, b) => Number(a.me) - Number(b.me))) {
    const r = c.me ? 19 : 14
    if (c.me) {
      ctx.strokeStyle = accent; ctx.lineWidth = 4
      ctx.beginPath(); ctx.arc(X(c.u), Y(c.v), r + 8, 0, Math.PI * 2); ctx.stroke()
      const tag = `${c.code} P${c.pos}`
      ctx.font = '700 24px "JetBrains Mono", monospace'
      const tw = ctx.measureText(tag).width + 24
      ctx.fillStyle = accent
      roundRect(ctx, X(c.u) - tw / 2, Y(c.v) - r - 58, tw, 36, 8); ctx.fill()
      ctx.fillStyle = '#0B0E14'; ctx.textAlign = 'center'; ctx.fillText(tag, X(c.u), Y(c.v) - r - 32)
    }
    ctx.fillStyle = c.color; ctx.strokeStyle = '#0B0E14'; ctx.lineWidth = 3
    ctx.beginPath(); ctx.arc(X(c.u), Y(c.v), r, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
    ctx.fillStyle = c.fg; ctx.textAlign = 'center'; ctx.font = `700 ${c.me ? 20 : 15}px "Space Grotesk", sans-serif`
    ctx.fillText(c.num, X(c.u), Y(c.v) + (c.me ? 7 : 5))
  }

  // top 10, two columns
  ctx.textAlign = 'left'
  f.rows.slice(0, 10).forEach((r, i) => {
    const col = i < 5 ? 0 : 1, row = i % 5
    const x = 60 + col * 490, y = 1000 + row * 54
    ctx.fillStyle = '#93A0B4'; ctx.font = '500 24px "JetBrains Mono", monospace'; ctx.textAlign = 'right'
    ctx.fillText(String(r.pos), x + 34, y + 30)
    ctx.fillStyle = r.color; roundRect(ctx, x + 48, y + 4, 40, 36, 8); ctx.fill()
    ctx.fillStyle = r.fg; ctx.textAlign = 'center'; ctx.font = '700 20px "Space Grotesk", sans-serif'
    ctx.fillText(r.num, x + 68, y + 29)
    ctx.textAlign = 'left'; ctx.fillStyle = '#E8ECF2'; ctx.font = '700 26px "JetBrains Mono", monospace'
    ctx.fillText(r.code, x + 104, y + 31)
    ctx.textAlign = 'right'; ctx.fillStyle = '#C4CAD2'; ctx.font = '400 24px "JetBrains Mono", monospace'
    ctx.fillText(r.gap, x + 450, y + 31)
  })
  ctx.textAlign = 'left'; ctx.fillStyle = '#5D6B82'; ctx.font = '400 20px Inter, sans-serif'
  ctx.fillText('f1telemetryhub.com · data: OpenF1 · unofficial', 60, H - 30)
  ctx.textAlign = 'right'; ctx.fillText('@f1telemetryhub', W - 60, H - 30)
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath()
}

/**
 * Record `seconds` of video. frameAt(p) gives the frame for race progress p in [0, 1]; the first
 * half second and the last 1.5 s hold still so the start and the result can be read.
 */
export function recordReplay(opts: {
  title: string; outlinePts: [number, number][]; ow: number; oh: number; logoUrl: string; accent: string
  seconds: number; frameAt: (p: number) => VideoFrame; onProgress: (p: number) => void
}): Promise<{ blob: Blob; ext: string }> {
  const fmt = videoFormat()
  if (!fmt) return Promise.reject(new Error('this browser cannot record video'))
  const canvas = document.createElement('canvas')
  canvas.width = VIDEO_W; canvas.height = VIDEO_H
  const ctx = canvas.getContext('2d')!
  const logo = new Image()
  logo.src = opts.logoUrl
  const scene: Scene = { title: opts.title, outlinePts: opts.outlinePts, ow: opts.ow, oh: opts.oh, logo }
  const HOLD0 = 0.5, HOLD1 = 1.5, total = opts.seconds + HOLD0 + HOLD1
  return new Promise((resolve, reject) => {
    const begin = () => {
      drawFrame(ctx, scene, opts.frameAt(0), opts.accent)
      const stream = canvas.captureStream(30)
      const rec = new MediaRecorder(stream, { mimeType: fmt.mime, videoBitsPerSecond: 8_000_000 })
      const chunks: Blob[] = []
      rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
      rec.onstop = () => resolve({ blob: new Blob(chunks, { type: fmt.mime.split(';')[0] }), ext: fmt.ext })
      rec.onerror = () => reject(new Error('recording failed'))
      rec.start(250)
      const t0 = performance.now()
      const tick = () => {
        const el = (performance.now() - t0) / 1000
        const p = Math.min(1, Math.max(0, (el - HOLD0) / opts.seconds))
        drawFrame(ctx, scene, opts.frameAt(p), opts.accent)
        opts.onProgress(Math.min(1, el / total))
        if (el < total) requestAnimationFrame(tick)
        else rec.stop()
      }
      requestAnimationFrame(tick)
    }
    if (logo.complete) begin()
    else { logo.onload = begin; logo.onerror = begin }
  })
}
