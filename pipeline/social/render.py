"""Carousel slides (1080x1350 JPEG) and Reels (1080x1920 H.264 MP4, no audio) from a story.

Reel spec checked against Meta's IG User Media reference: MP4, moov atom first (faststart),
H.264 progressive, closed GOP, 4:2:0, 23 to 60 fps, 3 s to 15 min, 300 MB max, 9:16 recommended.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from matplotlib.collections import LineCollection
import matplotlib.pyplot as plt

from . import style as S
from .story import Lap, QualiStory, RaceStory, corner_label

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


def new_fig(h: int):
    fig = plt.figure(figsize=(W / DPI, h / DPI), dpi=DPI)
    fig.patch.set_facecolor(S.BG)
    return fig


def chrome(fig, kicker: str, title: str, reel: bool = False) -> None:
    """Header (kicker, title, logo) and footer (handle, site) on every slide and frame."""
    top = 0.955 if reel else 0.94
    fig.text(0.06, top, kicker.upper(), fontsize=22, color=S.CYAN, weight="bold", family=S.HEAD)
    fig.text(0.06, top - (0.035 if reel else 0.05), title, fontsize=44, color=S.INK, weight="bold", family=S.HEAD)
    logo = S.logo_image()
    if logo is not None:
        h = 0.05 if reel else 0.07
        ax = fig.add_axes([0.80, top - h + 0.02, 0.14, h])
        ax.imshow(logo)
        ax.axis("off")
    y = 0.025 if reel else 0.03
    fig.text(0.06, y, S.HANDLE, fontsize=20, color=S.MUTE, family=S.MONO)
    fig.text(0.94, y, S.SITE, fontsize=20, color=S.MUTE, family=S.MONO, ha="right")


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


def gain_map(ax, st: QualiStory, rot: float, n_seg: int = 30, lw: float = 9) -> None:
    """Track coloured by who gained time in each of n_seg equal stretches."""
    x, y = lap_xy(st.a, rot, st.grid)
    edges = np.linspace(0, st.track_m, n_seg + 1)
    dd = np.diff(np.interp(edges, st.grid, st.delta))
    pts = np.column_stack([x, y]).reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    idx = np.clip(np.searchsorted(edges, st.grid[:-1], side="right") - 1, 0, n_seg - 1)
    cols = [S.MUTE if abs(dd[i]) < 0.002 else st.a.color if dd[i] > 0 else st.b.color for i in idx]
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=lw, capstyle="round"))
    ax.autoscale()
    ax.margins(0.06)


def save_jpeg(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, format="jpg", pil_kwargs={"quality": JPEG_QUALITY, "optimize": True})
    plt.close(fig)
    return path


# ---------------------------------------------------------------- carousel: qualifying

def quali_carousel(st: QualiStory, meta: dict, rot: float, out: Path) -> list[Path]:
    a, b = st.a, st.b
    seg = "SQ3" if meta["code"] == "SQ" else "Q3"
    kick = f"{meta['event']}  |  {seg}"
    paths = []

    fig = new_fig(H_POST)
    chrome(fig, kick, f"{a.code} on pole by {st.official_gap_s:.3f} s")
    ax = track_axes(fig, [0.06, 0.25, 0.88, 0.55])
    gain_map(ax, st, rot)
    fig.text(0.06, 0.19, f"{a.code}  {lap_time(a.lap_ms)}", fontsize=34, color=a.color, family=S.MONO, weight="bold")
    fig.text(0.06, 0.14, f"{b.code}  {lap_time(b.lap_ms)}", fontsize=34, color=b.color, family=S.MONO, weight="bold")
    fig.text(0.94, 0.165, "Track coloured by who\ngained time in each stretch\n(grey: level)", fontsize=18, color=S.MUTE, ha="right", va="center")
    paths.append(save_jpeg(fig, out / "slide_1.jpg"))

    fig = new_fig(H_POST)
    chrome(fig, kick, "Where the lap was won")
    ax1 = fig.add_axes([0.1, 0.56, 0.84, 0.25])
    ax2 = fig.add_axes([0.1, 0.12, 0.84, 0.40], sharex=ax1)
    ax1.axhline(0, color=S.MUTE, lw=1)
    ax1.fill_between(st.grid, st.delta, 0, where=st.delta >= 0, color=a.color, alpha=0.35, lw=0)
    ax1.fill_between(st.grid, st.delta, 0, where=st.delta < 0, color=b.color, alpha=0.35, lw=0)
    ax1.plot(st.grid, st.delta, color=S.INK, lw=2)
    ax1.set_ylabel(f"{a.code} ahead (s)")
    ax1.tick_params(labelbottom=False)
    ax2.plot(a.dist, a.speed, color=a.color, lw=2.6, label=a.code)
    ax2.plot(b.dist, b.speed, color=b.color, lw=2.2, label=b.code, alpha=0.9)
    ax2.set_ylabel("Speed (km/h)")
    ax2.set_xlabel("Distance (m)")
    ax2.set_xlim(0, st.track_m)
    ax2.legend(loc="lower right", frameon=False, fontsize=20)
    for g in (st.best_a, st.best_b):
        if g:
            ax2.axvspan(g.apex_m - 250, g.apex_m + 150, color=S.PURPLE, alpha=0.12, lw=0)
            ax2.text(g.apex_m, ax2.get_ylim()[1], f"T{g.corner}", ha="center", va="bottom", color=S.PURPLE, fontsize=18)
    paths.append(save_jpeg(fig, out / "slide_2.jpg"))

    for i, (g, lead) in enumerate([(st.best_a, a), (st.best_b, b)]):
        if g is None:
            continue
        fig = new_fig(H_POST)
        gain = abs(g.gain_s)
        chrome(fig, kick, f"{corner_label(g.corner)}: {lead.code} finds {gain:.3f} s")
        corner_zoom(fig.add_axes([0.1, 0.30, 0.84, 0.50]), a, b, g)
        da = g.apex_a - g.apex_b
        fig.text(0.06, 0.19, f"Minimum speed  {a.code} {g.apex_a:.0f}  |  {b.code} {g.apex_b:.0f} km/h", fontsize=26, family=S.MONO)
        fig.text(0.06, 0.14, f"{'+' if da >= 0 else ''}{da:.0f} km/h for {a.code} at the apex", fontsize=26,
                 color=S.GAIN if da >= 0 else S.LOSS, family=S.MONO)
        paths.append(save_jpeg(fig, out / f"slide_{3 + i}.jpg"))

    paths.append(cta_slide(kick, out / f"slide_{len(paths) + 1}.jpg"))
    return paths


def corner_zoom(ax, a: Lap, b: Lap, g, upto: float | None = None) -> None:
    lo, hi = g.apex_m - 250, g.apex_m + 150
    for L, lw in ((a, 3.2), (b, 2.6)):
        m = (L.dist >= lo) & (L.dist <= (hi if upto is None else min(hi, upto)))
        ax.plot(L.dist[m] - g.apex_m, L.speed[m], color=L.color, lw=lw, label=L.code)
    ax.axvline(0, color=S.PURPLE, lw=1.5, ls="--")
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
    fig.text(0.5, 0.27, S.SITE, ha="center", fontsize=40, color=S.CYAN, weight="bold", family=S.MONO)
    fig.text(0.5, 0.21, "link in bio", ha="center", fontsize=22, color=S.MUTE)
    return save_jpeg(fig, path)


# ---------------------------------------------------------------- carousel: race

def race_carousel(st: RaceStory, meta: dict, out: Path) -> list[Path]:
    kick = f"{meta['event']}  |  {'Sprint' if meta['code'] == 'S' else 'Race'}"
    w = st.winner
    paths = []

    fig = new_fig(H_POST)
    chrome(fig, kick, f"{w['code']} wins")
    for i, p in enumerate(st.podium):
        y = 0.62 - i * 0.13
        g = st.gaps.get(p["code"])
        gap = "" if i == 0 or g is None or np.isnan(g[-1]) else f"+{g[-1]:.3f} s"
        fig.text(0.08, y, f"P{p['position']}", fontsize=60, color=S.GOLD if i == 0 else S.MUTE, weight="bold", family=S.MONO)
        fig.text(0.30, y, p["code"], fontsize=60, color=p["color"], weight="bold", family=S.HEAD)
        fig.text(0.92, y + 0.01, gap, fontsize=34, ha="right", family=S.MONO)
    if st.mover:
        m = st.mover
        fig.text(0.08, 0.17, f"Biggest climb: {m['code']} P{m['grid']} to P{m['position']}", fontsize=28, color=S.CYAN)
    paths.append(save_jpeg(fig, out / "slide_1.jpg"))

    fig = new_fig(H_POST)
    chrome(fig, kick, "Gap to the winner, lap by lap")
    gap_axes(fig.add_axes([0.12, 0.18, 0.82, 0.62]), st)
    paths.append(save_jpeg(fig, out / "slide_2.jpg"))

    if st.mover:
        m = st.mover
        fig = new_fig(H_POST)
        chrome(fig, kick, f"{m['code']}: P{m['grid']} to P{m['position']}")
        mover_axes(fig.add_axes([0.12, 0.12, 0.82, 0.68]), st)
        paths.append(save_jpeg(fig, out / "slide_3.jpg"))

    paths.append(cta_slide(kick, out / f"slide_{len(paths) + 1}.jpg"))
    return paths


def gap_limits(st: RaceStory) -> float:
    ends = [np.nanmax(g) for g in st.gaps.values() if np.isfinite(g).any()]
    return float(min(max(ends + [5.0]) * 1.08, 90.0))


def gap_axes(ax, st: RaceStory, upto: int | None = None) -> None:
    laps = np.arange(1, st.n_laps + 1)
    k = st.n_laps if upto is None else upto
    for code, g in st.gaps.items():
        ax.plot(laps[:k], g[:k], color=st.colors[code], lw=3, label=code)
        if k and np.isfinite(g[k - 1]):
            ax.plot(laps[k - 1], g[k - 1], "o", color=st.colors[code], ms=10)
    ax.set_xlim(1, st.n_laps)
    ax.set_ylim(gap_limits(st), -1)
    ax.set_xlabel("Lap")
    ax.set_ylabel("Seconds behind the winner")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), frameon=False, fontsize=20, ncol=5)


def mover_axes(ax, st: RaceStory, upto: int | None = None) -> None:
    m = st.mover
    k = st.n_laps if upto is None else upto
    laps = np.arange(0, st.n_laps + 1)
    ax.plot(laps[: k + 1], st.positions[: k + 1], color=m["color"], lw=4, drawstyle="steps-post")
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
    a, b = st.a, st.b
    seg = "SQ3" if meta["code"] == "SQ" else "Q3"
    kick = f"{meta['event']}  |  {seg}"
    r = Reel(out / "reel.mp4")

    # 1. Intro, 1.5 s
    fig = reel_fig(kick, "Pole lap vs P2")
    fig.text(0.5, 0.56, a.code, ha="center", fontsize=150, color=a.color, weight="bold")
    fig.text(0.5, 0.49, "vs", ha="center", fontsize=50, color=S.MUTE)
    fig.text(0.5, 0.39, b.code, ha="center", fontsize=150, color=b.color, weight="bold")
    fig.text(0.5, 0.30, "Who wins where?", ha="center", fontsize=40, color=S.CYAN)
    r.add(fig, int(1.5 * FPS))
    cover = save_jpeg_reel(fig, out / "cover.jpg")

    # 2. Lap replay at speed lap_s for the whole lap
    fig = reel_fig(kick, f"{a.code} vs {b.code}, same clock")
    axm = track_axes(fig, [0.06, 0.50, 0.88, 0.36])
    xa, ya = lap_xy(a, rot)
    xb, yb = lap_xy(b, rot)
    axm.plot(xa, ya, color=S.BORDER, lw=14, solid_capstyle="round")
    axm.margins(0.05)
    dot_b, = axm.plot([], [], "o", ms=26, color=b.color, mec=S.BG, mew=3)
    dot_a, = axm.plot([], [], "o", ms=26, color=a.color, mec=S.BG, mew=3)
    lead = fig.text(0.5, 0.455, "", ha="center", fontsize=54, weight="bold", family=S.MONO)
    clock = fig.text(0.5, 0.42, "", ha="center", fontsize=28, color=S.MUTE, family=S.MONO)
    axs = fig.add_axes([0.12, 0.10, 0.82, 0.28])
    la, = axs.plot([], [], color=a.color, lw=3.5, label=a.code)
    lb, = axs.plot([], [], color=b.color, lw=3, label=b.code)
    axs.set_xlim(0, st.track_m)
    axs.set_ylim(max(0, min(a.speed.min(), b.speed.min()) - 20), max(a.speed.max(), b.speed.max()) + 15)
    axs.set_ylabel("Speed (km/h)")
    axs.set_xlabel("Distance (m)")
    axs.legend(loc="lower right", frameon=False, fontsize=22)
    total = a.time[-1] if a.time[-1] > 0 else a.lap_ms / 1000
    n = int(lap_s * FPS)
    for i in range(n + 1):
        tau = total * i / n
        da, db = np.interp(tau, a.time, a.dist), np.interp(tau, b.time, b.dist)
        dot_a.set_data([np.interp(tau, a.time, xa)], [np.interp(tau, a.time, ya)])
        dot_b.set_data([np.interp(tau, b.time, xb)], [np.interp(tau, b.time, yb)])
        ma, mb = a.dist <= da, b.dist <= db
        la.set_data(a.dist[ma], a.speed[ma])
        lb.set_data(b.dist[mb], b.speed[mb])
        d = float(np.interp(min(da, db, st.track_m), st.grid, st.delta))
        who = a if d >= 0 else b
        lead.set_text(f"{who.code} +{abs(d):.3f} s")
        lead.set_color(who.color)
        clock.set_text(f"{tau:5.1f} s   {min(da, st.track_m):4.0f} m")
        r.add(fig)
    r.add(fig, int(0.5 * FPS))
    plt.close(fig)

    # 3. Key corner, 3.5 s
    g = st.best_a
    fig = reel_fig(kick, f"{corner_label(g.corner)}: {a.code} +{g.gain_s:.3f} s")
    axm = track_axes(fig, [0.30, 0.66, 0.40, 0.20])
    axm.plot(xa, ya, color=S.BORDER, lw=8)
    cx, cy = np.interp(g.apex_m, a.dist, xa), np.interp(g.apex_m, a.dist, ya)
    axm.plot([cx], [cy], "o", ms=30, mfc="none", mec=S.PURPLE, mew=4)
    axm.margins(0.05)
    axz = fig.add_axes([0.12, 0.24, 0.82, 0.36])
    badge = fig.text(0.5, 0.13, "", ha="center", fontsize=34, family=S.MONO)
    steps = int(2.5 * FPS)
    for i in range(steps + 1):
        axz.cla()
        corner_zoom(axz, a, b, g, upto=g.apex_m - 250 + 400 * i / steps)
        if i == steps:
            badge.set_text(f"Apex  {a.code} {g.apex_a:.0f}  |  {b.code} {g.apex_b:.0f} km/h")
        r.add(fig)
    r.add(fig, FPS)
    plt.close(fig)

    # 4. End card, 2.5 s
    fig = reel_fig(kick, "Pole position")
    fig.text(0.5, 0.60, a.code, ha="center", fontsize=170, color=a.color, weight="bold")
    fig.text(0.5, 0.52, lap_time(a.lap_ms), ha="center", fontsize=64, family=S.MONO)
    fig.text(0.5, 0.46, f"{b.code} +{st.official_gap_s:.3f} s", ha="center", fontsize=44, color=b.color, family=S.MONO)
    fig.text(0.5, 0.33, "Full lap, every corner", ha="center", fontsize=40)
    fig.text(0.5, 0.28, S.SITE, ha="center", fontsize=48, color=S.CYAN, weight="bold", family=S.MONO)
    r.add(fig, int(2.5 * FPS))
    plt.close(fig)
    return r.close(), cover


def race_reel(st: RaceStory, meta: dict, out: Path) -> tuple[Path, Path]:
    kick = f"{meta['event']}  |  {'Sprint' if meta['code'] == 'S' else 'Race'}"
    w = st.winner
    r = Reel(out / "reel.mp4")

    fig = reel_fig(kick, "How it was won")
    fig.text(0.5, 0.50, w["code"], ha="center", fontsize=190, color=w["color"], weight="bold")
    fig.text(0.5, 0.41, f"wins the {meta['event']}", ha="center", fontsize=42)
    r.add(fig, int(1.5 * FPS))
    cover = save_jpeg_reel(fig, out / "cover.jpg")

    fig = reel_fig(kick, "Gap to the winner")
    ax = fig.add_axes([0.13, 0.17, 0.81, 0.63])
    lap_txt = fig.text(0.5, 0.835, "", ha="center", fontsize=40, family=S.MONO, color=S.CYAN)
    n = int(8 * FPS)
    for i in range(n + 1):
        k = max(1, round(st.n_laps * i / n))
        ax.cla()
        gap_axes(ax, st, upto=k)
        lap_txt.set_text(f"Lap {k} / {st.n_laps}")
        r.add(fig)
    r.add(fig, FPS)
    plt.close(fig)

    if st.mover:
        m = st.mover
        fig = reel_fig(kick, f"{m['code']} from P{m['grid']}")
        ax = fig.add_axes([0.13, 0.14, 0.81, 0.60])
        big = fig.text(0.5, 0.78, "", ha="center", fontsize=90, weight="bold", color=m["color"], family=S.MONO)
        n = int(4 * FPS)
        for i in range(n + 1):
            k = round(st.n_laps * i / n)
            ax.cla()
            mover_axes(ax, st, upto=k)
            p = st.positions[: k + 1]
            p = p[np.isfinite(p)]
            big.set_text(f"P{int(p[-1]) if len(p) else m['grid']}")
            r.add(fig)
        r.add(fig, FPS)
        plt.close(fig)

    fig = reel_fig(kick, "Every lap of every GP")
    fig.text(0.5, 0.52, w["code"], ha="center", fontsize=150, color=w["color"], weight="bold")
    fig.text(0.5, 0.44, "Race story, passes and pace", ha="center", fontsize=40)
    fig.text(0.5, 0.37, S.SITE, ha="center", fontsize=48, color=S.CYAN, weight="bold", family=S.MONO)
    r.add(fig, int(2.5 * FPS))
    plt.close(fig)
    return r.close(), cover


def save_jpeg_reel(fig, path: Path) -> Path:
    """Reel cover from the intro frame (does not close the figure)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, format="jpg", pil_kwargs={"quality": JPEG_QUALITY})
    return path
