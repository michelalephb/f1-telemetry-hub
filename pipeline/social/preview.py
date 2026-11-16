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
    country: str = ""             # host country, for the flag
    gp: str = ""                  # "Las Vegas GP"
    last_year: dict = field(default_factory=dict)   # official results of last year's race here (Jolpica)


# ---------------------------------------------------------------- numbers from the lap

def lap_stats(p: Preview) -> dict:
    d = p.dist
    seg = np.diff(d, prepend=d[0])
    flat = p.throttle >= FLAT_THROTTLE
    longest, run, start, best = 0.0, 0.0, 0, (0, 0)
    for i, (f, s) in enumerate(zip(flat, seg)):
        if f:
            if run == 0.0:
                start = i
            run += s
            if run > longest:
                longest, best = run, (start, i)
        else:
            run = 0.0
    return {
        "longest_flat_idx": best,
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

def last_year_results(season: int, rnd: int) -> dict:
    """Winner, pole and disqualifications of last year's race at the same circuit (Jolpica, official)."""
    from .. import jolpica

    cid = next(e["circuit_id"] for e in jolpica.events(season) if e["round"] == rnd)
    prev = next((e for e in jolpica.events(season - 1) if e["circuit_id"] == cid), None)
    if prev is None:
        return {}
    res = jolpica.results(season - 1, prev["round"])
    race = sorted([r for r in res if r["session_code"] == "R" and r["position"]], key=lambda r: r["position"])
    quali = sorted([r for r in res if r["session_code"] == "Q" and r["position"]], key=lambda r: r["position"])
    pole = quali[0] if quali else None
    pole_ms = (pole.get("q3_ms") or pole.get("q2_ms") or pole.get("q1_ms")) if pole else None
    return {
        "winner": race[0]["driver_code"] if race else None,
        "podium": [r["driver_code"] for r in race[:3]],
        "pole": pole["driver_code"] if pole else None,
        "pole_ms": pole_ms,
        "dsq": [r["driver_code"] for r in res if r["session_code"] == "R" and "isqualif" in (r.get("status") or "")],
    }


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
    p.country = sess[0].get("country") or ""
    p.gp = event.replace("Grand Prix", "GP")
    try:
        p.last_year = last_year_results(season, rnd)
    except Exception as e:  # the fact cards still work without it
        log.warning("last year's results unavailable: %s", e)
    log.info("preview %s: %s %s lap %.3f s, stats %s, sessions %s", p.title, p.ref_year, p.driver, p.lap_s, p.stats, p.sessions)
    return p


# ---------------------------------------------------------------- artwork: "Pink Night" fact cards
# One fact per card. Every number is huge, in Hot Pink, with its unit right beside it.
# Carousel cards are 1080x1350; story cards are 1080x1920 with Instagram's top and bottom UI kept clear.

FONT = "Inter"
PINK, SUN, SNOW, LILAC, LINE = S.PINK, S.SUN, S.SNOW, S.LILAC, S.LINE
SPEED_CMAP = LinearSegmentedColormap.from_list("pinksun", [S.PINK, "#FF7A6B", S.SUN])


def tracked(s: str, gap: int = 1) -> str:
    words = s.split(" ")
    return (" " * (2 * gap + 1)).join((" " * gap).join(w) for w in words)


class Card:
    """A 1080 wide canvas with layout helpers in figure coordinates."""

    def __init__(self, h: int, story: bool = False):
        self.h, self.story = h, story
        self.fig = plt.figure(figsize=(W / DPI, h / DPI), dpi=DPI)
        ax = self.fig.add_axes([0, 0, 1, 1], zorder=-10)
        yy, xx = np.mgrid[0:1:240j, 0:1:240j]
        base = np.dstack([np.interp(yy, [0, 1], [c0, c1]) for c0, c1 in zip(_rgb(S.NIGHT_BOTTOM), _rgb(S.NIGHT_TOP))])
        glow = np.exp(-(((xx - 0.5) / 0.55) ** 2 + ((yy - 0.55) * h / W / 0.5) ** 2))[..., None]
        img = np.clip(base + glow * (np.array(_rgb(PINK)) * 0.16), 0, 1)
        ax.imshow(img, extent=[0, 1, 0, 1], aspect="auto", origin="lower", interpolation="bicubic")
        rng = np.random.default_rng(5)
        ax.imshow(rng.random((h // 4, W // 4)), cmap="gray", alpha=0.03, extent=[0, 1, 0, 1], aspect="auto")
        ax.axis("off")
        # vertical positions: stories keep clear of the profile bar (top) and reply bar (bottom)
        self.top = 0.875 if story else 0.948
        self.bottom = 0.14 if story else 0.035

    def text(self, x, y, s, size, color=SNOW, weight=500, ha="center", track=False, **kw):
        return self.fig.text(x, y, tracked(s) if track else s, ha=ha, va="center", fontsize=size, color=color,
                             family=FONT, weight=weight, **kw)

    def header(self, p: "Preview"):
        flag = S.flag_image(p.country)
        y, x = self.top, 0.06
        hh = 0.026 * H_POST / self.h
        if flag is not None:
            w = hh * 1.5 * self.h / W
            ax = self.fig.add_axes([x, y - hh / 2, w, hh])
            ax.imshow(flag, aspect="auto")
            ax.axis("off")
            x += w + 0.018
        self.text(x, y, f"{gp_name(p).upper()} {p.season}", 19, weight=700, ha="left", track=True)
        self.text(0.94, y, f"ROUND {p.round}", 14, color=PINK, weight=700, ha="right", track=True,
                  bbox=dict(boxstyle="round,pad=0.45,rounding_size=0.8", fc="none", ec=PINK, lw=1.4))

    def kicker(self, y, s, n=None, total=None):
        self.text(0.5, y, s.upper(), 18, color=SUN, weight=700, track=True)
        if n:
            self.text(0.94, y, f"{n}/{total}", 15, color=LILAC, weight=600, ha="right")

    def number(self, y, value: str, unit: str, size=170, color=PINK):
        """Hero number with its unit on the same baseline, centred as one block."""
        fig = self.fig
        r = fig.canvas.get_renderer()
        t1 = fig.text(0, y, value, fontsize=size, color=color, family=FONT, weight=900, va="baseline")
        t2 = fig.text(0, y, " " + unit, fontsize=size * 0.32, color=SNOW, family=FONT, weight=700, va="baseline")
        w1 = t1.get_window_extent(r).width / fig.bbox.width
        w2 = t2.get_window_extent(r).width / fig.bbox.width
        x0 = 0.5 - (w1 + w2) / 2
        t1.set_x(x0)
        t2.set_x(x0 + w1)
        return t1, t2

    def footer(self, right: str | None = None):
        self.text(0.06, self.bottom, S.HANDLE, 15, color=LILAC, weight=500, ha="left")
        if right:
            self.text(0.94, self.bottom, right, 15, color=SUN, weight=800, ha="right", track=True)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(path, dpi=DPI, format="jpg", pil_kwargs={"quality": 94, "optimize": True})
        plt.close(self.fig)
        return path


def _rgb(hexs: str):
    return [int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def gp_name(p: "Preview") -> str:
    return p.gp or p.event.replace("Grand Prix", "GP") or p.title.title()


def track_ax(card: Card, rect, p: "Preview"):
    ax = card.fig.add_axes(rect)
    ax.set_aspect("equal")
    ax.axis("off")
    pad = 0.07 * max(np.ptp(p.x), np.ptp(p.y))
    ax.set_xlim(p.x.min() - pad, p.x.max() + pad)
    ax.set_ylim(p.y.min() - pad, p.y.max() + pad)
    return ax


def base_line(ax, p: "Preview", lw=7):
    ax.plot(p.x, p.y, color=LINE, lw=lw, solid_capstyle="round", solid_joinstyle="round")


def highlight(ax, p: "Preview", mask: np.ndarray, color=PINK, lw=9):
    ax.plot(np.where(mask, p.x, np.nan), np.where(mask, p.y, np.nan), color=color, lw=lw, solid_capstyle="round")


def speed_line(ax, p: "Preview", upto: int | None = None, lw=7):
    from matplotlib.collections import LineCollection
    n = len(p.x) if upto is None else max(2, upto)
    pts = np.column_stack([p.x[:n], p.y[:n]]).reshape(-1, 1, 2)
    lc = LineCollection(np.concatenate([pts[:-1], pts[1:]], axis=1), cmap=SPEED_CMAP,
                        norm=plt.Normalize(p.speed.min(), p.speed.max()), linewidths=lw, capstyle="round")
    lc.set_array(p.speed[: n - 1])
    ax.add_collection(lc)
    return lc


def dot(ax, x, y, color=PINK, ms=16, label=None, dx=0.0, dy=0.0, p=None):
    ax.plot([x], [y], "o", ms=ms, color=color, mec=S.NIGHT_BOTTOM, mew=3, zorder=8)
    if label and p is not None:
        span = max(np.ptp(p.x), np.ptp(p.y))
        ax.text(x + dx * span, y + dy * span, label, color=SNOW, fontsize=16, family=FONT, weight=800, zorder=9,
                ha="center", va="center", bbox=dict(boxstyle="round,pad=0.4,rounding_size=0.7", fc=color, ec="none"))


def times_text(p: "Preview") -> tuple[str, str]:
    q = p.sessions.get("SQ") or p.sessions.get("Q") or ""
    r = p.sessions.get("R") or ""
    return q, r


def km(m: float) -> str:
    return f"{m / 1000:.1f}"


DAYS = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}


def facts(p: "Preview") -> list[dict]:
    """The fact cards for a circuit, in order. Each: kicker, number, unit, line, source, draw(ax)."""
    st = p.stats
    imax = int(np.argmax(p.speed))
    lap = f"fastest {p.ref_year} race lap, {p.driver} {lap_time(round(p.lap_s * 1000))}"
    flat = p.throttle >= FLAT_THROTTLE
    i0, i1 = st["longest_flat_idx"]
    longest = np.zeros(len(p.x), bool)
    longest[i0:i1 + 1] = True
    out = [
        {"kicker": "Top speed", "number": f"{st['top_speed']}", "unit": "km/h",
         "line": "The fastest point of the lap", "source": f"Measured on the {lap}",
         "draw": lambda ax: (base_line(ax, p), highlight(ax, p, p.speed >= st["top_speed"] - 12),
                             dot(ax, p.x[imax], p.y[imax], label=f"{st['top_speed']} km/h", dy=0.11, p=p))},
        {"kicker": "Flat out", "number": f"{st['flat_pct']}", "unit": "% of the lap",
         "line": "Throttle pinned, pink on the map", "source": f"Measured on the {lap}",
         "draw": lambda ax: (base_line(ax, p), highlight(ax, p, flat))},
        {"kicker": "Longest flat out run", "number": km(st["longest_flat_m"]), "unit": "km",
         "line": "Without lifting once", "source": f"Measured on the {lap}",
         "draw": lambda ax: (base_line(ax, p), highlight(ax, p, longest),
                             dot(ax, p.x[i0], p.y[i0], color=SUN, ms=13), dot(ax, p.x[i1], p.y[i1], color=SUN, ms=13))},
        {"kicker": "Braking zones", "number": f"{st['braking_zones']}", "unit": "per lap",
         "line": "Everything else is flat out or close to it", "source": f"Measured on the {lap}",
         "draw": lambda ax: brake_map(ax, p)},
    ]
    ly = p.last_year or {}
    if ly.get("pole_ms") and ly.get("pole"):
        gap = ly["pole_ms"] / 1000 - p.lap_s
        if gap > 1:
            out.append({"kicker": f"{p.ref_year} flashback", "number": f"{gap:.1f}", "unit": "s",
                        "line": f"Pole ({ly['pole']} {lap_time(ly['pole_ms'])}) was slower than the race's fastest lap",
                        "source": f"Fastest race lap: {p.driver} {lap_time(round(p.lap_s * 1000))}. Official results",
                        "draw": lambda ax: (base_line(ax, p), speed_line(ax, p, lw=6))})
    out.append({"kicker": "New for 2026", "number": "0", "unit": "DRS zones",
                "line": "Straight Mode wings and Overtake Mode replace it", "source": "2026 technical and sporting regulations",
                "draw": lambda ax: (base_line(ax, p), speed_line(ax, p, lw=6))})
    return out


def brake_map(ax, p: "Preview"):
    base_line(ax, p)
    m = np.zeros(len(p.x), bool)
    runs = brake_runs(p.t, p.brake)
    for a_, b_ in runs:
        m[a_:b_ + 1] = True
    highlight(ax, p, m)
    span = max(np.ptp(p.x), np.ptp(p.y))
    cx, cy = np.mean(p.x), np.mean(p.y)
    for n, (a_, _) in enumerate(runs, 1):
        vx, vy = p.x[a_] - cx, p.y[a_] - cy
        d = math.hypot(vx, vy) or 1
        ax.text(p.x[a_] + vx / d * 0.08 * span, p.y[a_] + vy / d * 0.08 * span, str(n), color=S.NIGHT_BOTTOM,
                fontsize=17, family=FONT, weight=900, ha="center", va="center", zorder=9,
                bbox=dict(boxstyle="circle,pad=0.35", fc=SUN, ec="none"))


def cover(p: "Preview", h: int, story: bool, n_facts: int) -> Card:
    c = Card(h, story)
    c.header(p)
    t = c.top
    c.text(0.5, t - 0.09, "HOW FAST IS", 54 if not story else 60, weight=900)
    c.text(0.5, t - 0.16, p.title + "?", 92 if len(p.title) <= 10 else 70, color=PINK, weight=900)
    rect = [0.08, 0.27, 0.84, 0.40] if not story else [0.06, 0.33, 0.88, 0.36]
    ax = track_ax(c, rect, p)
    base_line(ax, p, lw=9)
    speed_line(ax, p, lw=7)
    q, r = times_text(p)
    y = 0.215 if not story else 0.27
    c.text(0.5, y, f"{n_facts} FACTS BEFORE LIGHTS OUT", 22, color=SUN, weight=800, track=True)
    c.text(0.5, y - 0.055, f"QUALI {q.upper()}   |   RACE {r.upper()}   |   LOCAL", 17, color=LILAC, weight=600)
    c.footer("SWIPE  >" if not story else "TAP FOR FACTS  >")
    return c


def fact_card(p: "Preview", f: dict, n: int, total: int, h: int, story: bool) -> Card:
    c = Card(h, story)
    c.header(p)
    t = c.top
    c.kicker(t - 0.065, f["kicker"], n, total)
    c.number(t - (0.245 if not story else 0.20), f["number"], f["unit"], size=160 if not story else 175)
    c.text(0.5, t - (0.295 if not story else 0.24), f["line"], 25, weight=600)
    rect = [0.08, 0.15, 0.84, 0.44] if not story else [0.08, 0.28, 0.84, 0.32]
    f["draw"](track_ax(c, rect, p))
    c.text(0.5, (0.115 if not story else 0.235), f["source"], 15, color=LILAC, weight=500)
    c.footer("SWIPE  >" if not story else None)
    return c


def closing(p: "Preview", h: int, story: bool) -> Card:
    c = Card(h, story)
    c.header(p)
    logo = S.logo_image()
    if logo is not None:
        ax = c.fig.add_axes([0.30, 0.66 if not story else 0.62, 0.40, 0.12])
        ax.imshow(logo)
        ax.axis("off")
    q, r = times_text(p)
    for x, k, v in ((0.30, "QUALIFYING", q), (0.70, "RACE", r)):
        c.text(x, 0.53, k, 16, color=SUN, weight=800, track=True)
        c.text(x, 0.48, v, 40, weight=900)
    c.text(0.5, 0.425, "LOCAL TIME", 13, color=LILAC, weight=600, track=True)
    c.text(0.5, 0.33, "Every session, decoded.", 34, weight=800)
    c.text(0.5, 0.28, "Follow so you don't miss quali.", 24, color=PINK, weight=700)
    c.text(0.5, 0.20, "SAVE THIS FOR RACE WEEK", 16, color=SUN, weight=800, track=True)
    c.footer(S.SITE.upper() if not story else None)
    return c


def carousel(p: Preview, out: Path) -> list[Path]:
    fs = facts(p)
    paths = [cover(p, H_POST, False, len(fs)).save(out / "slide_01.jpg")]
    for i, f in enumerate(fs, 1):
        paths.append(fact_card(p, f, i, len(fs), H_POST, False).save(out / f"slide_{i + 1:02d}.jpg"))
    paths.append(closing(p, H_POST, False).save(out / f"slide_{len(fs) + 2:02d}.jpg"))
    return paths


def stories(p: Preview, out: Path) -> list[Path]:
    fs = facts(p)
    paths = [cover(p, H_REEL, True, len(fs)).save(out / "story_01.jpg")]
    for i, f in enumerate(fs, 1):
        paths.append(fact_card(p, f, i, len(fs), H_REEL, True).save(out / f"story_{i + 1:02d}.jpg"))
    paths.append(closing(p, H_REEL, True).save(out / f"story_{len(fs) + 2:02d}.jpg"))
    return paths


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def reel(p: Preview, out: Path, lap_s: float = 6.0) -> tuple[Path, Path]:
    """Hook in frame 1, one lap traced in pink to yellow by speed with a live km/h readout, then the facts."""
    st = p.stats
    r = Reel(out / "reel.mp4")
    c = Card(H_REEL, story=True)
    c.header(p)
    hook = c.text(0.5, 0.80, "HOW FAST IS", 58, weight=900)
    name = c.text(0.5, 0.745, p.title + "?", 88 if len(p.title) <= 10 else 66, color=PINK, weight=900)
    ax = track_ax(c, [0.06, 0.36, 0.88, 0.34], p)
    base_line(ax, p, lw=9)
    head, = ax.plot([], [], "o", ms=20, color=SNOW, mec=PINK, mew=5, zorder=9)
    num = c.fig.text(0.5, 0.29, "", fontsize=150, color=PINK, family=FONT, weight=900, ha="center", va="center")
    unit = c.text(0.5, 0.225, "", 30, weight=800, track=True)
    c.footer()

    n = int(lap_s * FPS)
    line = None
    for i in range(n + 1):
        k = int(round((len(p.x) - 1) * i / n))
        if line is not None:
            line.remove()
        line = speed_line(ax, p, upto=k + 1, lw=8)
        head.set_data([p.x[k]], [p.y[k]])
        num.set_text(f"{int(p.speed[k])}")
        num.set_color(SPEED_CMAP((p.speed[k] - p.speed.min()) / max(np.ptp(p.speed), 1)))
        unit.set_text(tracked("KM/H"))
        r.add(c.fig)
        if i == int(0.55 * n):
            c.fig.savefig(out / "cover.jpg", dpi=DPI, format="jpg", pil_kwargs={"quality": 94})
    head.set_data([], [])
    num.set_text("")
    unit.set_text("")
    hook.set_text("")
    name.set_text("")

    q, rr = times_text(p)
    flashes = [(f"{st['top_speed']}", "km/h", "TOP SPEED"), (f"{st['flat_pct']}", "%", "OF THE LAP FLAT OUT"),
               (f"{st['braking_zones']}", "zones", "BRAKING PER LAP"), ("0", "DRS zones", "NEW FOR 2026")]
    for big, u, lbl in flashes:
        t1, t2 = c.number(0.255, big, u, size=150)
        t3 = c.text(0.5, 0.215, lbl, 24, color=SUN, weight=800, track=True)
        r.add(c.fig, int(0.9 * FPS))
        for t in (t1, t2, t3):
            t.remove()
    c.text(0.5, 0.80, f"QUALI {q.upper()}", 44, weight=900)
    c.text(0.5, 0.75, f"RACE {rr.upper()}", 44, color=PINK, weight=900)
    c.text(0.5, 0.71, "LOCAL TIME", 16, color=LILAC, weight=600, track=True)
    c.text(0.5, 0.29, "Follow so you don't miss quali", 30, weight=800)
    r.add(c.fig, int(1.8 * FPS))
    plt.close(c.fig)
    return r.close(), out / "cover.jpg"


def caption(p: Preview, kind: str) -> str:
    st = p.stats
    q, r = times_text(p)
    ly = p.last_year or {}
    lines = [f"How fast is {p.title.title()}? {st['top_speed']} km/h fast.",
             "",
             f"On last year's fastest race lap ({p.driver}, {lap_time(round(p.lap_s * 1000))}): {st['flat_pct']}% of the lap flat out, "
             f"one run of {km(st['longest_flat_m'])} km without lifting, and only {st['braking_zones']} braking zones.",
             "And for 2026: zero DRS zones. Straight Mode and Overtake Mode take over.",
             ]
    if ly.get("winner"):
        lines.append(f"Last year: {ly['winner']} won" + (f", {ly['pole']} took pole" if ly.get("pole") else "") + ".")
    lines += ["", f"Quali {q}. Race {r}. Local time.",
              "Save this for race week and follow so you don't miss quali." if kind != "reel" else "Follow so you don't miss quali.",
              "", FOOTER, "", " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Telemetry", "#RaceWeek"])]
    return clean("\n".join(lines))
