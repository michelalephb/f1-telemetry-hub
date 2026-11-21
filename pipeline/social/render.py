"""Carousel slides (1080x1350 JPEG) and Reels (1080x1920 H.264 MP4, no audio) from a story.

Reel spec checked against Meta's IG User Media reference: MP4, moov atom first (faststart),
H.264 progressive, closed GOP, 4:2:0, 23 to 60 fps, 3 s to 15 min, 300 MB max, 9:16 recommended.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from . import style as S
from .story import Lap, QualiStory, RaceStory, corner_label, sector_text

W, H_POST, H_REEL = 1080, 1350, 1920
DPI = 100
FPS = 30
JPEG_QUALITY = 92


# ---------------------------------------------------------------- shared pieces

def lap_time(ms: int) -> str:
    m, s = divmod(ms / 1000.0, 60)
    return f"{int(m)}:{s:06.3f}"


def rotate_xy(x: np.ndarray, y: np.ndarray, deg: float) -> tuple[np.ndarray, np.ndarray]:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


_META: dict = {}            # session the figures being drawn belong to (flag, GP name, season)


def new_fig(h: int):
    """Paddock Cyan card: gradient, grain and chequered motif (template v01)."""
    from .preview import Card
    return Card(h, story=False).fig


def chrome(fig, kicker: str, title: str, reel: bool = False) -> None:
    """Header (flag, GP and season, session in champagne, hairline), title, and footer (logo left,
    website right) on every slide and frame."""
    from .preview import tracked
    hfig = fig.get_figheight() * DPI
    top = 0.93 if reel else 0.948
    x = 0.06
    flag = S.flag_image(_META.get("country"))
    if flag is not None:
        hh = 0.022 * H_POST / hfig
        w = hh * 1.5 * hfig / W
        ax = fig.add_axes([x, top - hh / 2, w, hh])
        ax.imshow(flag, aspect="auto")
        ax.axis("off")
        x += w + 0.018
    ev, _, sess = kicker.partition("|")
    name = (_META.get("event") or ev.strip()).replace("Grand Prix", "GP").upper()
    season = f" {_META['season']}" if _META.get("season") else ""
    fig.text(x, top, tracked(name + season), fontsize=16, color=S.TEXT, weight=500, va="center", family=S.HEAD)
    if sess.strip():
        fig.text(0.94, top, tracked(sess.strip().upper()), fontsize=13, color=S.GOLD_HAIR, weight=500, ha="right",
                 va="center", family=S.HEAD)
    y = top - 0.028 * H_POST / hfig
    fig.add_artist(plt.Line2D([0.06, 0.94], [y, y], transform=fig.transFigure, color=S.GOLD_HAIR, lw=0.6))
    fig.text(0.06, y - (0.045 if not reel else 0.035), title, fontsize=40, color=S.TEXT, weight=300, va="center",
             family=S.HEAD)
    fy = 0.03 if not reel else 0.025
    logo = S.logo_image()
    lw = 0.20
    lh = lw * W / S.LOGO_ASPECT / hfig
    ax = fig.add_axes([0.06, fy - lh / 2, lw, lh])
    ax.imshow(logo, aspect="auto", interpolation="lanczos")
    ax.axis("off")
    fig.text(0.94, fy, tracked(S.SITE.upper()), fontsize=13, color=S.MUTED, weight=500, ha="right", va="center",
             family=S.HEAD)


def track_axes(fig, rect):
    ax = fig.add_axes(rect)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax


def lap_xy(lap: Lap, rot: float, d: np.ndarray | None = None):
    x, y = rotate_xy(lap.x, lap.y, rot)
    if d is None:
        return x, y
    return np.interp(d, lap.dist, x), np.interp(d, lap.dist, y)


def sector_map(ax, st: QualiStory, rot: float, lw: float = 10, labels: bool = True) -> None:
    """Track coloured by who was faster in each official sector, with the sector gaps."""
    edges = [0.0, *st.split_m, st.track_m]
    for k in range(3):
        d = np.linspace(edges[k], edges[k + 1], 200)
        x, y = lap_xy(st.a, rot, d)
        g = st.sector_gaps[k]
        col = S.MUTE if abs(g) < 0.0005 else st.a.color if g > 0 else st.b.color
        ax.plot(x, y, color=col, lw=lw, solid_capstyle="round")
        if labels:
            ax.annotate(f"S{k + 1}  {sector_text(g, st.a.code, st.b.code, '')}", (x[100], y[100]), xytext=(0, 0), textcoords="offset points",
                        ha="center", va="center", fontsize=20, color=S.INK, family=S.MONO, weight=400,
                        bbox=dict(boxstyle="round,pad=0.35", fc=S.CARD, ec=col, lw=2))
    ax.autoscale()
    ax.margins(0.08)


def sector_bars(ax, st: QualiStory) -> None:
    g = st.sector_gaps
    cols = [st.a.color if v > 0 else st.b.color for v in g]
    ax.barh(["S1", "S2", "S3"], np.abs(g), color=cols, height=0.6)
    for i, v in enumerate(g):
        ax.text(abs(v), i, "  " + sector_text(v, st.a.code, st.b.code), va="center", fontsize=22, family=S.MONO)
    ax.invert_yaxis()
    ax.set_xlim(0, max(np.abs(g)) * 1.9 + 0.01)
    ax.set_xlabel("Official sector time gained (s)")
    ax.grid(axis="y", visible=False)


def save_jpeg(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, format="jpg", pil_kwargs={"quality": JPEG_QUALITY, "optimize": True})
    plt.close(fig)
    return path


# ---------------------------------------------------------------- carousel: qualifying

def quali_carousel(st: QualiStory, meta: dict, rot: float, out: Path) -> list[Path]:
    _META.clear()
    _META.update(meta)
    a, b = st.a, st.b
    seg = "SQ3" if meta["code"] == "SQ" else "Q3"
    kick = f"{meta['event']}  |  {seg}"
    paths = []

    fig = new_fig(H_POST)
    from .gp_facts import grid_pole
    gp = grid_pole(meta.get("season"), meta.get("round"), a.code)
    chrome(fig, kick, f"{a.code} {'fastest' if gp else 'on pole'} by {st.official_gap_s:.3f} s")
    sector_map(track_axes(fig, [0.06, 0.25, 0.88, 0.57]), st, rot)
    fig.text(0.06, 0.19, f"{a.code}  {lap_time(a.lap_ms)}", fontsize=34, color=a.color, family=S.MONO, weight=400)
    fig.text(0.06, 0.14, f"{b.code}  {lap_time(b.lap_ms)}", fontsize=34, color=b.color, family=S.MONO, weight=400)
    fig.text(0.94, 0.165, "Track coloured by who won\neach official sector", fontsize=18, color=S.MUTE, ha="right", va="center")
    paths.append(save_jpeg(fig, out / "slide_1.jpg"))

    fig = new_fig(H_POST)
    chrome(fig, kick, "Sector by sector")
    sector_bars(fig.add_axes([0.1, 0.62, 0.84, 0.19]), st)
    ax = fig.add_axes([0.1, 0.12, 0.84, 0.40])
    ax.plot(a.dist, a.speed, color=a.color, lw=2.6, label=a.code)
    ax.plot(b.dist, b.speed, color=b.color, lw=2.2, label=b.code, alpha=0.9)
    for d in st.split_m:
        ax.axvline(d, color=S.MUTE, lw=1, ls=":")
    ax.set_ylabel("Speed (km/h)")
    ax.set_xlabel("Distance (m)")
    ax.set_xlim(0, st.track_m)
    ax.legend(loc="lower right", frameon=False, fontsize=20)
    for c in (st.best_a, st.best_b):
        if c:
            ax.text(c.apex_m, ax.get_ylim()[1], f"T{c.corner}", ha="center", va="bottom", color=S.GOLD_HAIR, fontsize=18)
    paths.append(save_jpeg(fig, out / "slide_2.jpg"))

    for i, c in enumerate((st.best_a, st.best_b)):
        if c is None:
            continue
        lead = a if c.diff > 0 else b
        fig = new_fig(H_POST)
        chrome(fig, kick, f"{corner_label(c.corner)}: {lead.code} +{abs(c.diff):.0f} km/h")
        corner_zoom(fig.add_axes([0.1, 0.30, 0.84, 0.50]), a, b, c)
        fig.text(0.06, 0.19, f"Apex speed  {a.code} {c.min_a:.0f}  |  {b.code} {c.min_b:.0f} km/h", fontsize=26, family=S.MONO)
        fig.text(0.06, 0.14, f"{lead.code} carries {abs(c.diff):.0f} km/h more through {corner_label(c.corner)}", fontsize=26,
                 color=lead.color, family=S.MONO)
        paths.append(save_jpeg(fig, out / f"slide_{3 + i}.jpg"))

    paths.append(cta_slide(kick, out / f"slide_{len(paths) + 1}.jpg"))
    return paths


def corner_zoom(ax, a: Lap, b: Lap, g, upto: float | None = None) -> None:
    lo, hi = g.apex_m - 250, g.apex_m + 150
    for L, lw in ((a, 3.2), (b, 2.6)):
        m = (L.dist >= lo) & (L.dist <= (hi if upto is None else min(hi, upto)))
        ax.plot(L.dist[m] - g.apex_m, L.speed[m], color=L.color, lw=lw, label=L.code)
    ax.axvline(0, color=S.GOLD_HAIR, lw=1.5, ls="--")
    ax.set_xlim(-250, 150)
    sp = np.concatenate([L.speed[(L.dist >= lo) & (L.dist <= hi)] for L in (a, b)])
    ax.set_ylim(max(0, sp.min() - 25), sp.max() + 15)
    ax.set_xlabel("Metres from apex")
    ax.set_ylabel("Speed (km/h)")
    ax.legend(loc="lower left", frameon=False, fontsize=20)


def cta_slide(kick: str, path: Path) -> Path:
    fig = new_fig(H_POST)
    chrome(fig, kick, "Every lap. Every corner.")
    logo = S.logo_image()
    if logo is not None:
        ax = fig.add_axes([0.25, 0.42, 0.5, 0.25])
        ax.imshow(logo)
        ax.axis("off")
    fig.text(0.5, 0.34, "Compare any two drivers, corner by corner", ha="center", fontsize=30)
    fig.text(0.5, 0.27, S.SITE, ha="center", fontsize=40, color=S.CYAN, weight=400, family=S.MONO)
    fig.text(0.5, 0.21, "link in bio", ha="center", fontsize=22, color=S.MUTE)
    return save_jpeg(fig, path)


# ---------------------------------------------------------------- carousel: race

def race_carousel(st: RaceStory, meta: dict, out: Path) -> list[Path]:
    _META.clear()
    _META.update(meta)
    kick = f"{meta['event']}  |  {'Sprint' if meta['code'] == 'S' else 'Race'}"
    w = st.winner
    paths = []

    fig = new_fig(H_POST)
    chrome(fig, kick, f"{w['code']} wins")
    for i, p in enumerate(st.podium):
        y = 0.62 - i * 0.13
        g = st.gaps.get(p["code"])
        gap = "" if i == 0 or g is None or not np.isfinite(g) else f"+{g:.3f} s"
        fig.text(0.08, y, f"P{p['position']}", fontsize=60, color=S.GOLD_HAIR if i == 0 else S.MUTE, weight=400, family=S.MONO)
        fig.text(0.30, y, p["code"], fontsize=60, color=p["color"], weight=400, family=S.HEAD)
        fig.text(0.92, y + 0.01, gap, fontsize=34, ha="right", family=S.MONO)
    if st.mover:
        m = st.mover
        fig.text(0.08, 0.17, f"Biggest climb: {m['code']} P{m['grid']} to P{m['position']}", fontsize=28, color=S.CYAN)
    paths.append(save_jpeg(fig, out / "slide_1.jpg"))

    fig = new_fig(H_POST)
    chrome(fig, kick, "Top 5, lap by lap")
    order_axes(fig.add_axes([0.12, 0.18, 0.82, 0.62]), st)
    paths.append(save_jpeg(fig, out / "slide_2.jpg"))

    if st.mover:
        m = st.mover
        fig = new_fig(H_POST)
        chrome(fig, kick, f"{m['code']}: P{m['grid']} to P{m['position']}")
        mover_axes(fig.add_axes([0.12, 0.12, 0.82, 0.68]), st)
        paths.append(save_jpeg(fig, out / "slide_3.jpg"))

    paths.append(cta_slide(kick, out / f"slide_{len(paths) + 1}.jpg"))
    return paths


def order_axes(ax, st: RaceStory, upto: int | None = None) -> None:
    """Running position of the top 5 finishers (pit stops show as dips)."""
    laps = np.arange(0, st.n_laps + 1)
    k = st.n_laps if upto is None else upto
    top = [p["code"] for p in st.podium] + [c for c in st.positions if c not in [p["code"] for p in st.podium]]
    for code in top[:5]:
        p = st.positions[code]
        ax.plot(laps[: k + 1], p[: k + 1], color=st.colors[code], lw=3.5, drawstyle="steps-post", label=code)
        last = p[: k + 1][np.isfinite(p[: k + 1])]
        if len(last):
            ax.text(k + 0.6, last[-1], code, color=st.colors[code], va="center", fontsize=18, weight=400)
    ax.set_xlim(0, st.n_laps + 4)
    ax.set_ylim(min(22.5, np.nanmax([np.nanmax(st.positions[c]) for c in top[:5]]) + 1.5), 0.5)
    ax.set_yticks([1, 3, 5, 10, 15, 20])
    ax.set_xlabel("Lap (0 = grid)")
    ax.set_ylabel("Position")


def mover_axes(ax, st: RaceStory, upto: int | None = None) -> None:
    m = st.mover
    k = st.n_laps if upto is None else upto
    laps = np.arange(0, st.n_laps + 1)
    ax.plot(laps[: k + 1], st.positions[m["code"]][: k + 1], color=m["color"], lw=4, drawstyle="steps-post")
    ax.set_xlim(0, st.n_laps)
    ax.set_ylim(22.5, 0.5)
    ax.set_yticks([1, 5, 10, 15, 20])
    ax.set_xlabel("Lap (0 = grid)")
    ax.set_ylabel("Position")


# ---------------------------------------------------------------- reels

class Reel:
    """Pipes RGBA frames from matplotlib into ffmpeg. No audio track (-an)."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.n = 0
        self.p = subprocess.Popen([
            "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H_REEL}",
            "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast",
            "-crf", "21", "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p",
            "-g", str(FPS * 2), "-keyint_min", str(FPS * 2), "-sc_threshold", "0", "-x264-params", "open-gop=0",
            "-movflags", "+faststart", str(path),
        ], stdin=subprocess.PIPE)

    def add(self, fig, times: int = 1) -> None:
        fig.canvas.draw()
        buf = bytes(fig.canvas.buffer_rgba())
        if len(buf) != W * H_REEL * 4:
            raise RuntimeError(f"frame is {len(buf)} bytes, expected {W * H_REEL * 4}")
        for _ in range(times):
            self.p.stdin.write(buf)
            self.n += 1

    def close(self) -> Path:
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        return self.path


def reel_fig(kick: str, title: str):
    fig = new_fig(H_REEL)
    chrome(fig, kick, title, reel=True)
    return fig


def quali_reel(st: QualiStory, meta: dict, rot: float, out: Path, lap_s: float = 11.0) -> tuple[Path, Path]:
    _META.clear()
    _META.update(meta)
    a, b = st.a, st.b
    seg = "SQ3" if meta["code"] == "SQ" else "Q3"
    kick = f"{meta['event']}  |  {seg}"
    r = Reel(out / "reel.mp4")

    # 1. Intro, 1.5 s
    from .gp_facts import grid_pole
    gp = grid_pole(meta.get("season"), meta.get("round"), st.a.code)
    fig = reel_fig(kick, "Fastest lap vs P2" if gp else "Pole lap vs P2")
    fig.text(0.5, 0.56, a.code, ha="center", fontsize=150, color=a.color, weight=400)
    fig.text(0.5, 0.49, "vs", ha="center", fontsize=50, color=S.MUTE)
    fig.text(0.5, 0.39, b.code, ha="center", fontsize=150, color=b.color, weight=400)
    fig.text(0.5, 0.30, "Same clock. Who wins where?", ha="center", fontsize=40, color=S.CYAN)
    r.add(fig, int(1.5 * FPS))
    cover = save_jpeg_reel(fig, out / "cover.jpg")
    plt.close(fig)

    # 2. Both laps replayed on the same clock: each dot is a car's own position at that moment,
    #    so the gap between the dots is real. Sector gaps (official) appear as pole crosses each split.
    fig = reel_fig(kick, f"{a.code} vs {b.code}, same clock")
    axm = track_axes(fig, [0.06, 0.50, 0.88, 0.36])
    xa, ya = lap_xy(a, rot)
    xb, yb = lap_xy(b, rot)
    axm.plot(xa, ya, color=S.BORDER, lw=14, solid_capstyle="round")
    axm.margins(0.05)
    dot_b, = axm.plot([], [], "o", ms=26, color=b.color, mec=S.BG, mew=3)
    dot_a, = axm.plot([], [], "o", ms=26, color=a.color, mec=S.BG, mew=3)
    sec_txt = [fig.text(0.5, 0.465 - 0.03 * k, "", ha="center", fontsize=34, weight=400, family=S.MONO) for k in range(3)]
    clock = fig.text(0.5, 0.375, "", ha="center", fontsize=26, color=S.MUTE, family=S.MONO)
    axs = fig.add_axes([0.12, 0.08, 0.82, 0.26])
    la, = axs.plot([], [], color=a.color, lw=3.5, label=a.code)
    lb, = axs.plot([], [], color=b.color, lw=3, label=b.code)
    axs.set_xlim(0, st.track_m)
    axs.set_ylim(max(0, min(a.speed.min(), b.speed.min()) - 20), max(a.speed.max(), b.speed.max()) + 15)
    axs.set_ylabel("Speed (km/h)")
    axs.set_xlabel("Distance (m)")
    axs.legend(loc="lower right", frameon=False, fontsize=22)
    total = a.time[-1] if a.time[-1] > 0 else a.lap_ms / 1000
    marks = [*st.split_m, st.track_m]
    n = int(lap_s * FPS)
    for i in range(n + 1):
        tau = total * i / n
        da, db = np.interp(tau, a.time, a.dist), np.interp(tau, b.time, b.dist)
        dot_a.set_data([np.interp(tau, a.time, xa)], [np.interp(tau, a.time, ya)])
        dot_b.set_data([np.interp(tau, b.time, xb)], [np.interp(tau, b.time, yb)])
        ma, mb = a.dist <= da, b.dist <= db
        la.set_data(a.dist[ma], a.speed[ma])
        lb.set_data(b.dist[mb], b.speed[mb])
        for k, m in enumerate(marks):
            if da >= m - 1 or i == n:
                g = st.sector_gaps[k]
                sec_txt[k].set_text(f"S{k + 1}  {sector_text(g, a.code, b.code)}")
                sec_txt[k].set_color(S.MUTE if abs(g) < 0.0005 else (a if g > 0 else b).color)
        clock.set_text(f"{tau:5.1f} s   {min(da, st.track_m):4.0f} m")
        r.add(fig)
    r.add(fig, int(0.7 * FPS))
    plt.close(fig)

    # 3. The corner where pole carried the most extra speed, 3.5 s
    c = st.best_a
    fig = reel_fig(kick, f"{corner_label(c.corner)}: {a.code} +{c.diff:.0f} km/h")
    axm = track_axes(fig, [0.30, 0.66, 0.40, 0.20])
    axm.plot(xa, ya, color=S.BORDER, lw=8)
    cx, cy = np.interp(c.apex_m, a.dist, xa), np.interp(c.apex_m, a.dist, ya)
    axm.plot([cx], [cy], "o", ms=30, mfc="none", mec=S.GOLD_HAIR, mew=4)
    axm.margins(0.05)
    axz = fig.add_axes([0.12, 0.24, 0.82, 0.36])
    badge = fig.text(0.5, 0.13, "", ha="center", fontsize=34, family=S.MONO)
    steps = int(2.5 * FPS)
    for i in range(steps + 1):
        axz.cla()
        corner_zoom(axz, a, b, c, upto=c.apex_m - 250 + 400 * i / steps)
        if i == steps:
            badge.set_text(f"Apex  {a.code} {c.min_a:.0f}  |  {b.code} {c.min_b:.0f} km/h")
        r.add(fig)
    r.add(fig, FPS)
    plt.close(fig)

    # 4. End card, 2.5 s
    fig = reel_fig(kick, "Fastest in qualifying" if gp else "Pole position")
    fig.text(0.5, 0.60, a.code, ha="center", fontsize=170, color=a.color, weight=400)
    fig.text(0.5, 0.52, lap_time(a.lap_ms), ha="center", fontsize=64, family=S.MONO)
    fig.text(0.5, 0.46, f"{b.code} +{st.official_gap_s:.3f} s", ha="center", fontsize=44, color=b.color, family=S.MONO)
    fig.text(0.5, 0.33, "Full lap, every corner", ha="center", fontsize=40)
    fig.text(0.5, 0.28, S.SITE, ha="center", fontsize=48, color=S.CYAN, weight=400, family=S.MONO)
    r.add(fig, int(2.5 * FPS))
    plt.close(fig)
    return r.close(), cover


def race_reel(st: RaceStory, meta: dict, out: Path) -> tuple[Path, Path]:
    _META.clear()
    _META.update(meta)
    kick = f"{meta['event']}  |  {'Sprint' if meta['code'] == 'S' else 'Race'}"
    w = st.winner
    r = Reel(out / "reel.mp4")

    fig = reel_fig(kick, "How it was won")
    fig.text(0.5, 0.50, w["code"], ha="center", fontsize=190, color=w["color"], weight=400)
    fig.text(0.5, 0.41, f"wins the {'Sprint' if meta['code'] == 'S' else meta['event']}", ha="center", fontsize=42)
    r.add(fig, int(1.5 * FPS))
    cover = save_jpeg_reel(fig, out / "cover.jpg")
    plt.close(fig)

    fig = reel_fig(kick, "Top 5, lap by lap")
    ax = fig.add_axes([0.13, 0.12, 0.81, 0.68])
    lap_txt = fig.text(0.5, 0.835, "", ha="center", fontsize=40, family=S.MONO, color=S.CYAN)
    n = int(8 * FPS)
    for i in range(n + 1):
        k = max(1, round(st.n_laps * i / n))
        ax.cla()
        order_axes(ax, st, upto=k)
        lap_txt.set_text(f"Lap {k} / {st.n_laps}")
        r.add(fig)
    r.add(fig, FPS)
    plt.close(fig)

    if st.mover:
        m = st.mover
        fig = reel_fig(kick, f"{m['code']} from P{m['grid']}")
        ax = fig.add_axes([0.13, 0.14, 0.81, 0.60])
        big = fig.text(0.5, 0.78, "", ha="center", fontsize=90, weight=400, color=m["color"], family=S.MONO)
        n = int(4 * FPS)
        for i in range(n + 1):
            k = round(st.n_laps * i / n)
            ax.cla()
            mover_axes(ax, st, upto=k)
            p = st.positions[m["code"]][: k + 1]
            p = p[np.isfinite(p)]
            big.set_text(f"P{int(p[-1]) if len(p) else m['grid']}")
            r.add(fig)
        r.add(fig, FPS)
        plt.close(fig)

    fig = reel_fig(kick, "Every lap of every GP")
    fig.text(0.5, 0.52, w["code"], ha="center", fontsize=150, color=w["color"], weight=400)
    fig.text(0.5, 0.44, "Race story, passes and pace", ha="center", fontsize=40)
    fig.text(0.5, 0.37, S.SITE, ha="center", fontsize=48, color=S.CYAN, weight=400, family=S.MONO)
    r.add(fig, int(2.5 * FPS))
    plt.close(fig)
    return r.close(), cover


def save_jpeg_reel(fig, path: Path) -> Path:
    """Reel cover from the intro frame (does not close the figure)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, format="jpg", pil_kwargs={"quality": JPEG_QUALITY})
    return path
