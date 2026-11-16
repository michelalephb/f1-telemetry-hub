"""Race week preview ("Up next"): the coming circuit drawn in neon from last year's fastest race lap,
coloured by speed, with numbers measured on that lap. Original artwork only: no F1 logos, photos or
broadcast imagery.

Data (OpenF1, free historical): this season's schedule gives the circuit and session times; last
year's race at the same circuit gives the fastest lap's car data (speed, throttle, brake, gear) and
location. Every number on the graphics and in the caption is computed from that one lap.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from . import style as S
from .captions import FOOTER, clean, event_tag
from .render import DPI, FPS, H_POST, H_REEL, W, Reel, lap_time

log = logging.getLogger(__name__)

FLAT_THROTTLE = 98          # % throttle counted as flat out
BRAKE_MERGE_S = 0.5         # brake applications closer than this are one braking zone
BRAKE_MIN_S = 0.25          # shorter brake blips are ignored


@dataclass
class Preview:
    title: str                    # "LAS VEGAS"
    event: str                    # "Las Vegas Grand Prix"
    season: int
    round: int
    ref_year: int                 # season of the reference lap
    driver: str                   # fastest race lap, last year
    lap_s: float
    t: np.ndarray                 # s from lap start
    dist: np.ndarray              # m
    speed: np.ndarray
    throttle: np.ndarray
    brake: np.ndarray
    gear: np.ndarray
    x: np.ndarray                 # rotated map coordinates
    y: np.ndarray
    sessions: dict                # {"Q": "Fri 8 PM", "R": "Sat 8 PM"} local track time
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------- numbers from the lap

def lap_stats(p: Preview) -> dict:
    d = p.dist
    seg = np.diff(d, prepend=d[0])
    flat = p.throttle >= FLAT_THROTTLE
    longest, run = 0.0, 0.0
    for f, s in zip(flat, seg):
        run = run + s if f else 0.0
        longest = max(longest, run)
    return {
        "top_speed": int(round(float(p.speed.max()))),
        "flat_pct": int(round(100 * float(seg[flat].sum()) / max(float(d[-1] - d[0]), 1))),
        "braking_zones": braking_zones(p.t, p.brake),
        "longest_flat_m": int(round(longest / 10) * 10),
        "lap_m": int(round(float(d[-1] - d[0]) / 10) * 10),
    }


def brake_runs(t: np.ndarray, brake: np.ndarray) -> list[tuple[int, int]]:
    """Index ranges of braking zones: applications closer than BRAKE_MERGE_S merged, blips shorter
    than BRAKE_MIN_S dropped."""
    runs, i0, last = [], None, None
    for i, on in enumerate(brake > 0):
        if not on:
            continue
        if i0 is not None and t[i] - t[last] > BRAKE_MERGE_S:
            runs.append((i0, last))
            i0 = None
        if i0 is None:
            i0 = i
        last = i
    if i0 is not None:
        runs.append((i0, last))
    return [(a, b) for a, b in runs if t[b] - t[a] >= BRAKE_MIN_S]


def braking_zones(t: np.ndarray, brake: np.ndarray) -> int:
    return len(brake_runs(t, brake))


def brake_mask(p: Preview) -> np.ndarray:
    m = np.zeros(len(p.t), bool)
    for a, b in brake_runs(p.t, p.brake):
        m[a:b + 1] = True
    return m


# ---------------------------------------------------------------- data (needs network: GitHub Actions)

def load(season: int, rnd: int) -> Preview:
    from ..__main__ import schedule
    from ..ingest import corner_markers
    from ..openf1 import OpenF1

    oc = OpenF1()
    sess = [s for s in schedule(oc, season) if s["round"] == rnd]
    if not sess:
        raise ValueError(f"round {rnd} not in the {season} schedule")
    ck = sess[0]["circuit_key"]
    location = sess[0].get("location") or sess[0].get("meeting_name") or f"Round {rnd}"
    event = sess[0].get("meeting_name") or f"{location} Grand Prix"

    prev = oc.frame("sessions", year=season - 1, circuit_key=int(ck), session_name="Race")
    if prev.empty:
        raise ValueError(f"no {season - 1} race at circuit {ck}")
    ps = prev.iloc[0]
    laps = oc.frame("laps", session_key=int(ps["session_key"]))
    laps = laps[laps["lap_duration"].notna() & (laps["lap_number"] > 1) & ~laps["is_pit_out_lap"].fillna(False).astype(bool)]
    best = laps.sort_values("lap_duration").iloc[0]
    drv = int(best["driver_number"])
    t0 = pd.Timestamp(best["date_start"])
    t1 = t0 + pd.Timedelta(seconds=float(best["lap_duration"]))
    win = [f"date>={(t0 - pd.Timedelta(seconds=1)).isoformat()}", f"date<={(t1 + pd.Timedelta(seconds=1)).isoformat()}"]
    car = oc.frame("car_data", win, session_key=int(ps["session_key"]), driver_number=drv)
    loc = oc.frame("location", win, session_key=int(ps["session_key"]), driver_number=drv)
    info = oc.frame("drivers", session_key=int(ps["session_key"]), driver_number=drv)
    code = info.iloc[0]["name_acronym"] if len(info) else str(drv)

    ct = (pd.to_datetime(car["date"], format="ISO8601", utc=True) - t0).dt.total_seconds().to_numpy()
    lt = (pd.to_datetime(loc["date"], format="ISO8601", utc=True) - t0).dt.total_seconds().to_numpy()
    keep = (ct >= 0) & (ct <= float(best["lap_duration"]))
    car, ct = car[keep], ct[keep]
    sp = car["speed"].to_numpy(float)
    dist = np.concatenate([[0.0], np.cumsum(np.diff(ct) * (sp[1:] + sp[:-1]) / 2 / 3.6)])
    markers = corner_markers(season - 1, ck)
    rot = markers.attrs.get("rotation", 0.0) if len(markers) else 0.0
    x, y = np.interp(ct, lt, loc["x"].to_numpy(float)), np.interp(ct, lt, loc["y"].to_numpy(float))
    a = math.radians(rot)
    xr, yr = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)

    off = pd.to_timedelta(ps.get("gmt_offset") or "00:00:00")
    times = {}
    for s in sess:
        if s["session_code"] in ("Q", "R", "SQ", "S"):
            local = pd.Timestamp(s["start_utc"]).tz_convert(None) + off
            times[s["session_code"]] = local.strftime("%a %-I %p") if local.minute == 0 else local.strftime("%a %-I:%M %p")
    p = Preview(location.upper(), event, season, rnd, season - 1, code, float(best["lap_duration"]),
                ct, dist, sp, car["throttle"].to_numpy(float), car["brake"].to_numpy(float),
                car["n_gear"].to_numpy(float), xr, yr, times)
    p.stats = lap_stats(p)
    log.info("preview %s: %s %s lap %.3f s, stats %s, sessions %s", p.title, p.ref_year, p.driver, p.lap_s, p.stats, p.sessions)
    return p


# ---------------------------------------------------------------- artwork: black and champagne, editorial

BG0, BG1 = "#09090A", "#17161A"
INK = "#ECE7DD"          # warm white
MUTE = "#8D877C"
GOLD = "#C9A96E"         # champagne
HAIR = "#3A3630"
FONT = "Inter"


def tracked(s: str, gap: int = 1) -> str:
    """Wide letter spacing, the luxury way: spaces between letters, three between words."""
    words = s.split(" ")
    return (" " * (2 * gap + 1)).join((" " * gap).join(w) for w in words)


def canvas(h: int):
    fig = plt.figure(figsize=(W / DPI, h / DPI), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1], zorder=-10)
    yy, xx = np.mgrid[0:1:200j, 0:1:200j]
    r = np.sqrt((xx - 0.5) ** 2 + ((yy - 0.55) * h / W) ** 2)
    ax.imshow(r, cmap=LinearSegmentedColormap.from_list("v", [BG1, BG0]), extent=[0, 1, 0, 1], aspect="auto",
              vmin=0, vmax=0.9 * h / W, interpolation="bicubic")
    rng = np.random.default_rng(3)
    ax.imshow(rng.random((h // 3, W // 3)), cmap="gray", alpha=0.035, extent=[0, 1, 0, 1], aspect="auto")
    ax.axis("off")
    return fig


def label(fig, x, y, s, size=15, color=GOLD, ha="center", alpha=1.0, gap=1):
    return fig.text(x, y, tracked(s.upper(), gap), ha=ha, va="center", fontsize=size, color=color, family=FONT,
                    weight=500, alpha=alpha)


def display(fig, x, y, s, size, color=INK, ha="center", weight=200, alpha=1.0, track=True):
    return fig.text(x, y, tracked(s.upper()) if track else s, ha=ha, va="center", fontsize=size, color=color,
                    family=FONT, weight=weight, alpha=alpha)


def rule(fig, x0, x1, y, color=GOLD, lw=0.8, alpha=1.0):
    return fig.add_artist(plt.Line2D([x0, x1], [y, y], transform=fig.transFigure, color=color, lw=lw, alpha=alpha))


def track_axes(fig, rect, p: Preview):
    ax = fig.add_axes(rect)
    ax.set_aspect("equal")
    ax.axis("off")
    pad = 0.06 * max(np.ptp(p.x), np.ptp(p.y))
    ax.set_xlim(p.x.min() - pad, p.x.max() + pad)
    ax.set_ylim(p.y.min() - pad, p.y.max() + pad)
    return ax


def outline(ax, p: Preview, upto: int | None = None, lw: float = 2.2, color=INK):
    n = len(p.x) if upto is None else max(2, upto)
    ax.plot(p.x[:n], p.y[:n], color="black", lw=lw + 5, alpha=0.35, solid_capstyle="round", solid_joinstyle="round")
    return ax.plot(p.x[:n], p.y[:n], color=color, lw=lw, solid_capstyle="round", solid_joinstyle="round")[0]


def start_line(ax, p: Preview):
    dx, dy = p.x[1] - p.x[0], p.y[1] - p.y[0]
    n = math.hypot(dx, dy) or 1
    L = 0.035 * max(np.ptp(p.x), np.ptp(p.y))
    ax.plot([p.x[0] - dy / n * L, p.x[0] + dy / n * L], [p.y[0] + dx / n * L, p.y[0] - dx / n * L], color=GOLD, lw=2.5)


def callout(ax, p: Preview, i: int, text: str, dx=0.10, dy=0.08):
    span = max(np.ptp(p.x), np.ptp(p.y))
    ax.plot([p.x[i]], [p.y[i]], "o", ms=8, color=GOLD, zorder=5)
    tx, ty = p.x[i] + dx * span, p.y[i] + dy * span
    ax.plot([p.x[i], tx], [p.y[i], ty], color=GOLD, lw=0.8)
    ax.text(tx, ty, " " + tracked(text), color=GOLD, fontsize=14, family=FONT, weight=500,
            ha="left" if dx >= 0 else "right", va="center")


def footer(fig, y=0.035):
    fig.text(0.06, y, S.HANDLE, fontsize=14, color=MUTE, family=FONT, weight=300)
    fig.text(0.94, y, S.SITE, fontsize=14, color=MUTE, family=FONT, weight=300, ha="right")


def times_block(fig, p: Preview, y: float, size: int = 30):
    q = p.sessions.get("SQ") or p.sessions.get("Q")
    r = p.sessions.get("R")
    label(fig, 0.30, y + 0.035, "Qualifying")
    display(fig, 0.30, y, q or "", size, weight=300, track=False)
    fig.add_artist(plt.Line2D([0.5, 0.5], [y - 0.025, y + 0.05], transform=fig.transFigure, color=HAIR, lw=0.8))
    label(fig, 0.70, y + 0.035, "Race")
    display(fig, 0.70, y, r or "", size, weight=300, track=False)
    label(fig, 0.5, y - 0.045, "Local time", size=12, color=MUTE)


def save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, format="jpg", pil_kwargs={"quality": 94, "optimize": True})
    plt.close(fig)
    return path


def km(m: float) -> str:
    return f"{m / 1000:.1f} km"


def carousel(p: Preview, out: Path) -> list[Path]:
    st, paths = p.stats, []
    imax = int(np.argmax(p.speed))

    fig = canvas(H_POST)
    label(fig, 0.06, 0.945, f"Round {p.round}", ha="left")
    label(fig, 0.94, 0.945, f"{p.season} season", ha="right")
    label(fig, 0.5, 0.865, "Up next")
    rule(fig, 0.47, 0.53, 0.835)
    display(fig, 0.5, 0.775, p.title, 64 if len(p.title) <= 10 else 50)
    label(fig, 0.5, 0.725, "Grand Prix", size=13, color=MUTE)
    ax = track_axes(fig, [0.10, 0.25, 0.80, 0.45], p)
    outline(ax, p)
    start_line(ax, p)
    times_block(fig, p, 0.15)
    footer(fig)
    paths.append(save(fig, out / "slide_1.jpg"))

    fig = canvas(H_POST)
    label(fig, 0.5, 0.92, f"Fastest race lap, {p.ref_year}")
    display(fig, 0.5, 0.885, f"{p.driver}   {lap_time(round(p.lap_s * 1000))}", 22, color=MUTE, weight=300, track=False)
    display(fig, 0.5, 0.74, f"{st['top_speed']}", 190, weight=100, track=False)
    label(fig, 0.5, 0.635, "km/h  top speed")
    ax = fig.add_axes([0.08, 0.27, 0.84, 0.30])
    ax.plot(p.dist, p.speed, color=INK, lw=1.6)
    ax.plot([p.dist[imax]], [p.speed[imax]], "o", ms=7, color=GOLD)
    ax.set_xlim(0, p.dist[-1])
    ax.set_ylim(0, p.speed.max() * 1.12)
    ax.axis("off")
    ax.axhline(0, color=HAIR, lw=0.8)
    for k in range(0, int(p.dist[-1] // 1000) + 1):
        ax.text(k * 1000, -p.speed.max() * 0.06, f"{k} km" if k else "0", color=MUTE, fontsize=12, family=FONT, ha="center", weight=300)
    cols = [(f"{st['flat_pct']}%", "flat out"), (km(st["longest_flat_m"]), "longest flat out"), (f"{st['braking_zones']}", "braking zones")]
    for j, (big, small) in enumerate(cols):
        x = 0.2 + 0.3 * j
        display(fig, x, 0.15, big, 40, weight=300, track=False)
        label(fig, x, 0.105, small, size=12, color=MUTE)
        if j:
            fig.add_artist(plt.Line2D([x - 0.15, x - 0.15], [0.09, 0.18], transform=fig.transFigure, color=HAIR, lw=0.8))
    footer(fig)
    paths.append(save(fig, out / "slide_2.jpg"))

    fig = canvas(H_POST)
    label(fig, 0.5, 0.92, "Where they brake")
    display(fig, 0.5, 0.82, f"{st['braking_zones']}", 150, weight=100, track=False)
    label(fig, 0.5, 0.735, "braking zones in one lap")
    ax = track_axes(fig, [0.10, 0.17, 0.80, 0.52], p)
    outline(ax, p, lw=1.6, color="#6F6A61")
    m = brake_mask(p)
    ax.plot(np.where(m, p.x, np.nan), np.where(m, p.y, np.nan), color=GOLD, lw=4, solid_capstyle="round")
    span = max(np.ptp(p.x), np.ptp(p.y))
    for n, (a_, _) in enumerate(brake_runs(p.t, p.brake), 1):
        cx, cy = np.mean(p.x), np.mean(p.y)
        vx, vy = p.x[a_] - cx, p.y[a_] - cy
        d = math.hypot(vx, vy) or 1
        ax.text(p.x[a_] + vx / d * 0.06 * span, p.y[a_] + vy / d * 0.06 * span, str(n), color=GOLD, fontsize=15,
                family=FONT, weight=500, ha="center", va="center")
    fig.text(0.5, 0.12, f"Measured on the fastest {p.ref_year} race lap, {p.driver}", ha="center", fontsize=14, color=MUTE,
             family=FONT, weight=300)
    footer(fig)
    paths.append(save(fig, out / "slide_3.jpg"))

    fig = canvas(H_POST)
    logo = S.logo_image()
    if logo is not None:
        ax = fig.add_axes([0.32, 0.74, 0.36, 0.12])
        ax.imshow(logo)
        ax.axis("off")
    display(fig, 0.5, 0.60, "Every session", 40)
    display(fig, 0.5, 0.545, "Decoded", 40, color=GOLD)
    rule(fig, 0.47, 0.53, 0.49)
    times_block(fig, p, 0.37)
    label(fig, 0.5, 0.22, S.SITE, size=16)
    footer(fig)
    paths.append(save(fig, out / "slide_4.jpg"))
    return paths


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def reel(p: Preview, out: Path, lap_s: float = 6.5) -> tuple[Path, Path]:
    st = p.stats
    imax = int(np.argmax(p.speed))
    r = Reel(out / "reel.mp4")
    fig = canvas(H_REEL)
    up = label(fig, 0.5, 0.90, "Up next", size=18, alpha=0)
    title = display(fig, 0.5, 0.855, p.title, 66 if len(p.title) <= 10 else 52, alpha=0)
    gp = label(fig, 0.5, 0.825, "Grand Prix", size=13, color=MUTE, alpha=0)
    ln = rule(fig, 0.5, 0.5, 0.80)
    ax = track_axes(fig, [0.08, 0.44, 0.84, 0.34], p)
    ax.plot(p.x, p.y, color=HAIR, lw=1.4, solid_capstyle="round")
    drawn = outline(ax, p, upto=2)
    head, = ax.plot([], [], "o", ms=11, color=GOLD, zorder=6)
    spd = display(fig, 0.5, 0.33, "", 150, weight=100, track=False)
    unit = label(fig, 0.5, 0.265, "", size=16)
    footer(fig, 0.03)

    # 1. Title fades in as the gold rule draws outward (motion from the first frame)
    n0 = int(1.2 * FPS)
    for i in range(n0):
        e = ease(i / (n0 - 1))
        ln.set_xdata([0.5 - 0.06 * e, 0.5 + 0.06 * e])
        up.set_alpha(e)
        title.set_alpha(ease(i / (n0 - 1) * 1.3))
        gp.set_alpha(e)
        r.add(fig)

    # 2. One lap, traced in a single line
    n = int(lap_s * FPS)
    for i in range(n + 1):
        k = int(round((len(p.x) - 1) * i / n))
        drawn.remove()
        drawn = ax.plot(p.x[: k + 1], p.y[: k + 1], color=INK, lw=2.4, solid_capstyle="round", solid_joinstyle="round")[0]
        head.set_data([p.x[k]], [p.y[k]])
        spd.set_text(f"{int(p.speed[k])}")
        unit.set_text(tracked("KM/H"))
        if k >= imax and not any(t.get_text().strip().startswith("3") for t in ax.texts):
            callout(ax, p, imax, f"{st['top_speed']} KM/H", dx=-0.12, dy=0.10)
        r.add(fig)
    head.set_data([], [])
    cover = out / "cover.jpg"
    fig.savefig(cover, dpi=DPI, format="jpg", pil_kwargs={"quality": 94})

    # 3. Numbers, fading in one by one
    spd.set_text("")
    unit.set_text("")
    rows = [(f"{st['top_speed']}", "km/h top speed"), (f"{st['flat_pct']}%", "of the lap flat out"),
            (f"{st['braking_zones']}", "braking zones")]
    items = []
    for j, (big, small) in enumerate(rows):
        y = 0.345 - j * 0.07
        items.append((display(fig, 0.40, y, big, 56, weight=100, ha="right", track=False, alpha=0),
                      label(fig, 0.44, y, small, size=14, color=MUTE, ha="left", alpha=0)))
    for j in range(3):
        for i in range(int(0.5 * FPS)):
            e = ease(i / (0.5 * FPS - 1))
            items[j][0].set_alpha(e)
            items[j][1].set_alpha(e)
            r.add(fig)
        r.add(fig, int(0.25 * FPS))
    r.add(fig, int(0.6 * FPS))

    # 4. When, then sign off
    for big, small in items:
        big.set_alpha(0)
        small.set_alpha(0)
    q = p.sessions.get("SQ") or p.sessions.get("Q")
    texts = [label(fig, 0.30, 0.33, "Qualifying", alpha=0), display(fig, 0.30, 0.295, q or "", 34, weight=300, track=False, alpha=0),
             label(fig, 0.70, 0.33, "Race", alpha=0), display(fig, 0.70, 0.295, p.sessions.get("R") or "", 34, weight=300, track=False, alpha=0),
             label(fig, 0.5, 0.25, "Local time", size=12, color=MUTE, alpha=0),
             display(fig, 0.5, 0.17, "Every session", 34, alpha=0), display(fig, 0.5, 0.13, "Decoded", 34, color=GOLD, alpha=0)]
    for i in range(int(0.8 * FPS)):
        e = ease(i / (0.8 * FPS - 1))
        for t in texts:
            t.set_alpha(e)
        r.add(fig)
    r.add(fig, int(1.8 * FPS))
    plt.close(fig)
    return r.close(), cover


def caption(p: Preview, kind: str) -> str:
    st = p.stats
    q = p.sessions.get("SQ") or p.sessions.get("Q")
    r = p.sessions.get("R")
    lines = [f"Up next: {p.title.title()}.",
             "",
             f"On last year's fastest race lap ({p.driver}, {lap_time(round(p.lap_s * 1000))}): {st['top_speed']} km/h at the top, "
             f"{st['flat_pct']}% of the lap flat out, and just {st['braking_zones']} braking zones.",
             "",
             f"Qualifying {q}. Race {r}. Local time." if q and r else "",
             "Every session, decoded, right here." if kind == "reel" else "Swipe for the lap in numbers.",
             "", FOOTER, "", " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Telemetry"])]
    return clean("\n".join(lines))
