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

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap

from . import style as S
from .captions import FOOTER, clean, event_tag
from .render import DPI, FPS, H_POST, H_REEL, JPEG_QUALITY, W, Reel, lap_time

log = logging.getLogger(__name__)

FLAT_THROTTLE = 98          # % throttle counted as flat out
BRAKE_MERGE_S = 0.5         # brake applications closer than this are one braking zone
BRAKE_MIN_S = 0.25          # shorter brake blips are ignored
NEON = LinearSegmentedColormap.from_list("neon", ["#3B0A8C", "#B026FF", "#FF2E97", "#FF8A00", "#FFE14D"])
GOLD = "#FFE14D"
PINK = "#FF2E97"


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


# ---------------------------------------------------------------- artwork

def backdrop(fig) -> None:
    ax = fig.add_axes([0, 0, 1, 1], zorder=-10)
    g = np.linspace(0, 1, 256)[:, None]
    ax.imshow(g, cmap=LinearSegmentedColormap.from_list("bg", ["#14062B", "#07070F", "#000000"]), aspect="auto", extent=[0, 1, 0, 1])
    rng = np.random.default_rng(7)
    ax.scatter(rng.random(160), 0.35 + 0.65 * rng.random(160), s=rng.random(160) * 3, color="white", alpha=0.35, lw=0)
    ax.axis("off")


def neon_text(fig, x, y, s, size, glow=GOLD, alpha=1.0):
    t = fig.text(x, y, s, ha="center", va="center", fontsize=size, color="#FFF6CC", weight="heavy", family=S.HEAD)
    set_glow(t, glow, alpha)
    return t


def set_glow(t, glow: str, alpha: float) -> None:
    """Neon look: wide faint strokes under a bright core. Alpha drives the flicker."""
    t.set_alpha(alpha)
    t.set_path_effects([pe.Stroke(linewidth=w, foreground=glow, alpha=a * alpha) for w, a in ((26, 0.06), (16, 0.12), (8, 0.35), (3, 0.9))]
                       + [pe.Normal()])


def neon_track(ax, p: Preview, upto: int | None = None, lw: float = 7) -> None:
    n = len(p.x) if upto is None else max(2, upto)
    pts = np.column_stack([p.x[:n], p.y[:n]]).reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    norm = plt.Normalize(p.speed.min(), p.speed.max())
    for w, a in ((lw * 5, 0.05), (lw * 3, 0.10), (lw * 1.8, 0.25), (lw, 1.0)):
        lc = LineCollection(segs, cmap=NEON, norm=norm, linewidths=w, alpha=a, capstyle="round")
        lc.set_array(p.speed[: n - 1])
        ax.add_collection(lc)


def map_axes(fig, rect, p: Preview):
    ax = fig.add_axes(rect)
    ax.set_aspect("equal")
    ax.axis("off")
    pad = 0.08 * max(np.ptp(p.x), np.ptp(p.y))
    ax.set_xlim(p.x.min() - pad, p.x.max() + pad)
    ax.set_ylim(p.y.min() - pad, p.y.max() + pad)
    return ax


def footer(fig, y=0.03):
    fig.text(0.06, y, S.HANDLE, fontsize=20, color="#B9A9D9", family=S.MONO)
    fig.text(0.94, y, S.SITE, fontsize=20, color="#B9A9D9", family=S.MONO, ha="right")


def speed_bar(fig, rect, p: Preview):
    ax = fig.add_axes(rect)
    ax.imshow(np.linspace(0, 1, 256)[None, :], cmap=NEON, aspect="auto", extent=[p.speed.min(), p.speed.max(), 0, 1])
    ax.set_yticks([])
    ax.tick_params(colors="#B9A9D9", labelsize=16)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("km/h", color="#B9A9D9", fontsize=16)
    ax.grid(False)


def times_line(p: Preview) -> str:
    q = p.sessions.get("SQ") or p.sessions.get("Q")
    r = p.sessions.get("R")
    parts = ([f"QUALI {q}"] if q else []) + ([f"RACE {r}"] if r else [])
    return "   |   ".join(parts) + "   LOCAL TIME"


def save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, format="jpg", pil_kwargs={"quality": JPEG_QUALITY, "optimize": True})
    plt.close(fig)
    return path


def carousel(p: Preview, out: Path) -> list[Path]:
    st, paths = p.stats, []

    fig = plt.figure(figsize=(W / DPI, H_POST / DPI), dpi=DPI)
    backdrop(fig)
    fig.text(0.5, 0.905, "U P   N E X T", ha="center", fontsize=34, color="white", weight="bold", family=S.HEAD)
    neon_text(fig, 0.5, 0.82, p.title, 96 if len(p.title) <= 10 else 72)
    neon_track(map_axes(fig, [0.06, 0.24, 0.88, 0.50], p), p)
    speed_bar(fig, [0.25, 0.20, 0.5, 0.012], p)
    fig.text(0.5, 0.115, times_line(p), ha="center", fontsize=22, color=GOLD, weight="bold", family=S.MONO)
    fig.text(0.5, 0.075, f"Circuit drawn from the fastest {p.ref_year} race lap, coloured by speed", ha="center", fontsize=17, color="#B9A9D9")
    footer(fig)
    paths.append(save(fig, out / "slide_1.jpg"))

    fig = plt.figure(figsize=(W / DPI, H_POST / DPI), dpi=DPI)
    backdrop(fig)
    fig.text(0.06, 0.93, f"{p.title}  |  {p.ref_year} FASTEST RACE LAP", fontsize=22, color=PINK, weight="bold", family=S.HEAD)
    neon_text(fig, 0.5, 0.80, f"{st['top_speed']} km/h", 88)
    fig.text(0.5, 0.71, f"top speed  |  {st['flat_pct']}% of the lap flat out", ha="center", fontsize=30, color="white")
    ax = fig.add_axes([0.10, 0.16, 0.84, 0.46])
    ax.set_facecolor("none")
    pts = np.column_stack([p.dist, p.speed]).reshape(-1, 1, 2)
    norm = plt.Normalize(p.speed.min(), p.speed.max())
    for w, a in ((14, 0.08), (7, 0.25), (3, 1.0)):
        lc = LineCollection(np.concatenate([pts[:-1], pts[1:]], axis=1), cmap=NEON, norm=norm, linewidths=w, alpha=a)
        lc.set_array(p.speed[:-1])
        ax.add_collection(lc)
    ax.set_xlim(0, p.dist[-1])
    ax.set_ylim(max(0, p.speed.min() - 30), p.speed.max() + 25)
    ax.set_xlabel("Distance (m)", color="#B9A9D9")
    ax.set_ylabel("Speed (km/h)", color="#B9A9D9")
    ax.tick_params(colors="#B9A9D9")
    ax.grid(color="#2A2140")
    for s in ax.spines.values():
        s.set_color("#2A2140")
    fig.text(0.5, 0.075, f"{p.driver}, {lap_time(round(p.lap_s * 1000))}, longest flat out stretch {st['longest_flat_m']} m",
             ha="center", fontsize=20, color="#B9A9D9", family=S.MONO)
    footer(fig)
    paths.append(save(fig, out / "slide_2.jpg"))

    fig = plt.figure(figsize=(W / DPI, H_POST / DPI), dpi=DPI)
    backdrop(fig)
    fig.text(0.06, 0.93, f"{p.title}  |  WHERE THEY BRAKE", fontsize=22, color=PINK, weight="bold", family=S.HEAD)
    neon_text(fig, 0.5, 0.82, f"{st['braking_zones']} braking zones", 64, glow=PINK)
    ax = map_axes(fig, [0.06, 0.16, 0.88, 0.58], p)
    ax.plot(p.x, p.y, color="#3A2A5C", lw=10, solid_capstyle="round")
    m = brake_mask(p)
    xb, yb = np.where(m, p.x, np.nan), np.where(m, p.y, np.nan)
    for w, a in ((34, 0.08), (20, 0.2), (9, 1.0)):
        ax.plot(xb, yb, color=PINK if w > 9 else "#FF6B6B", lw=w, alpha=a, solid_capstyle="round")
    fig.text(0.5, 0.10, f"Braking on the fastest {p.ref_year} race lap ({p.driver})", ha="center", fontsize=20, color="#B9A9D9")
    footer(fig)
    paths.append(save(fig, out / "slide_3.jpg"))

    fig = plt.figure(figsize=(W / DPI, H_POST / DPI), dpi=DPI)
    backdrop(fig)
    logo = S.logo_image()
    if logo is not None:
        ax = fig.add_axes([0.25, 0.55, 0.5, 0.2])
        ax.imshow(logo)
        ax.axis("off")
    neon_text(fig, 0.5, 0.46, "Lights on. Data on.", 54, glow=PINK)
    fig.text(0.5, 0.38, times_line(p), ha="center", fontsize=22, color=GOLD, weight="bold", family=S.MONO)
    fig.text(0.5, 0.31, "Pole lap and race breakdowns land here after every session", ha="center", fontsize=24, color="white")
    fig.text(0.5, 0.24, S.SITE, ha="center", fontsize=40, color=S.CYAN, weight="bold", family=S.MONO)
    footer(fig)
    paths.append(save(fig, out / "slide_4.jpg"))
    return paths


def reel(p: Preview, out: Path, lap_s: float = 6.0) -> tuple[Path, Path]:
    st = p.stats
    r = Reel(out / "reel.mp4")
    fig = plt.figure(figsize=(W / DPI, H_REEL / DPI), dpi=DPI)
    backdrop(fig)
    up = fig.text(0.5, 0.90, "", ha="center", fontsize=40, color="white", weight="bold", family=S.HEAD)
    title = neon_text(fig, 0.5, 0.84, p.title, 104 if len(p.title) <= 10 else 78, alpha=0.0)
    ax = map_axes(fig, [0.04, 0.38, 0.92, 0.40], p)
    ax.plot(p.x, p.y, color="#2A1E45", lw=10, solid_capstyle="round")
    head, = ax.plot([], [], "o", ms=30, color="white", mec=GOLD, mew=6)
    spd = fig.text(0.5, 0.31, "", ha="center", fontsize=110, weight="heavy", color="white", family=S.MONO)
    unit = fig.text(0.5, 0.255, "", ha="center", fontsize=30, color="#B9A9D9", family=S.MONO)
    footer(fig, 0.025)

    # 1. Title flickers on while UP NEXT types itself (motion from frame 1)
    word = "UP NEXT"
    for i in range(int(0.9 * FPS)):
        up.set_text("  ".join(word[: 1 + i * len(word) // int(0.9 * FPS)]))
        flick = [0.15, 0.9, 0.3, 1.0, 0.6, 1.0][i % 6] if i < int(0.6 * FPS) else 1.0
        set_glow(title, GOLD, flick)
        r.add(fig)
    cover = out / "cover.jpg"
    # 2. One lap, drawn in neon as it is driven
    n = int(lap_s * FPS)
    coll = []
    for i in range(n + 1):
        k = int(round((len(p.x) - 1) * i / n))
        for c in coll:
            c.remove()
        before = set(ax.collections)
        neon_track(ax, p, upto=k + 1, lw=6)
        coll = [c for c in ax.collections if c not in before]
        head.set_data([p.x[k]], [p.y[k]])
        spd.set_text(f"{int(p.speed[k])}")
        spd.set_color(NEON((p.speed[k] - p.speed.min()) / max(np.ptp(p.speed), 1)))
        unit.set_text(f"km/h   gear {int(p.gear[k])}")
        r.add(fig)
        if i == int(0.8 * n):
            fig.savefig(cover, dpi=DPI, format="jpg", pil_kwargs={"quality": JPEG_QUALITY})
    head.set_data([], [])
    spd.set_text("")
    unit.set_text("")
    # 3. Three numbers, one at a time
    cards = [(f"{st['top_speed']}", "km/h top speed", GOLD), (f"{st['flat_pct']}%", "of the lap flat out", GOLD),
             (f"{st['braking_zones']}", "braking zones", PINK)]
    shown = []
    for j, (big, small, glow) in enumerate(cards):
        y = 0.30 - j * 0.085
        b = neon_text(fig, 0.30, y, big, 60, glow=glow)
        s_ = fig.text(0.47, y, small, ha="left", va="center", fontsize=30, color="white")
        shown += [b, s_]
        r.add(fig, int(0.7 * FPS))
    r.add(fig, int(0.6 * FPS))
    for t in shown:
        t.remove()
    # 4. When to watch
    fig.text(0.5, 0.28, times_line(p).replace("   LOCAL TIME", ""), ha="center", fontsize=30, color=GOLD, weight="bold", family=S.MONO)
    fig.text(0.5, 0.235, "local time", ha="center", fontsize=24, color="#B9A9D9")
    fig.text(0.5, 0.16, "Telemetry after every session", ha="center", fontsize=34, color="white")
    fig.text(0.5, 0.115, S.HANDLE, ha="center", fontsize=40, color=S.CYAN, weight="bold", family=S.MONO)
    r.add(fig, int(1.6 * FPS))
    plt.close(fig)
    return r.close(), cover


def caption(p: Preview, kind: str) -> str:
    st = p.stats
    q = p.sessions.get("SQ") or p.sessions.get("Q")
    lines = [f"{p.title.title()} week. {st['top_speed']} km/h under the neon.",
             "",
             f"Last year's fastest race lap ({p.driver}, {lap_time(round(p.lap_s * 1000))}) was flat out for {st['flat_pct']}% of the lap, "
             f"with {st['braking_zones']} braking zones and a longest flat out stretch of {st['longest_flat_m']} m.",
             "",
             f"Quali {q} local. Race {p.sessions.get('R')} local." if q and p.sessions.get("R") else "",
             "Pole lap and race breakdowns land here after every session." if kind == "reel" else "Swipe for top speed and where they brake.",
             "", FOOTER, "", " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Telemetry", "#DataViz"])]
    return clean("\n".join(lines))
