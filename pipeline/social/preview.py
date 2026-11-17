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
from .gp_facts import COMPOUND_COLOR, TYRES, streak_text, trio
from .captions import drv as _drv, paragraphs
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
    corners: list = field(default_factory=list)     # [(number, letter, x, y)] MultiViewer markers, same rotation as x, y
    colors: dict = field(default_factory=dict)      # driver code -> team colour hex in last year's race (caption dots)


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


WET_COMPOUNDS = {"INTERMEDIATE": "INTER", "WET": "WET"}


def quali_conditions(oc, year: int, circuit_key: int, pole_code: str | None) -> dict:
    """Was last year's qualifying wet? Pole sitter's last compound (OpenF1 stints) decides; if that is
    missing, any rainfall in the session weather. Empty dict when OpenF1 has nothing: no guess."""
    qs = oc.frame("sessions", year=year, circuit_key=int(circuit_key), session_name="Qualifying")
    if qs.empty:
        return {}
    sk = int(qs.iloc[0]["session_key"])
    comp = None
    if pole_code:
        drv = oc.frame("drivers", session_key=sk)
        num = drv.loc[drv["name_acronym"] == pole_code, "driver_number"]
        if len(num):
            st = oc.frame("stints", session_key=sk, driver_number=int(num.iloc[0]))
            if len(st) and "compound" in st:
                comp = str(st.sort_values("stint_number")["compound"].dropna().iloc[-1]).upper() or None
    w = oc.frame("weather", session_key=sk)
    rain = bool(len(w) and "rainfall" in w and (w["rainfall"].fillna(0) > 0).any())
    if comp is None and not len(w):
        return {}
    wet = comp in WET_COMPOUNDS if comp else rain
    return {"quali_wet": wet, "pole_compound": comp}


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
    grid = oc.frame("drivers", session_key=int(ps["session_key"]))
    info = grid[grid["driver_number"] == drv] if len(grid) else grid
    code = info.iloc[0]["name_acronym"] if len(info) else str(drv)
    colors = {r["name_acronym"]: "#" + str(r.get("team_colour") or "").lstrip("#") for _, r in grid.iterrows()
              if r.get("team_colour")} if len(grid) else {}

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
    p.colors = colors
    if len(markers):
        mx, my = markers["X"].to_numpy(float), markers["Y"].to_numpy(float)
        p.corners = [(int(n), str(l or ""), float(cx), float(cy)) for n, l, cx, cy in
                     zip(markers["Number"], markers["Letter"].fillna(""),
                         mx * math.cos(a) - my * math.sin(a), mx * math.sin(a) + my * math.cos(a))]
    p.country = sess[0].get("country") or ""
    p.gp = event.replace("Grand Prix", "GP")
    try:
        p.last_year = last_year_results(season, rnd)
    except Exception as e:  # the fact cards still work without it
        log.warning("last year's results unavailable: %s", e)
    try:
        p.last_year |= quali_conditions(oc, season - 1, ck, p.last_year.get("pole"))
    except Exception as e:  # no conditions, no pole comparison card
        log.warning("last year's qualifying conditions unavailable: %s", e)
    log.info("preview %s: %s %s lap %.3f s, stats %s, sessions %s", p.title, p.ref_year, p.driver, p.lap_s, p.stats, p.sessions)
    return p


# ---------------------------------------------------------------- artwork: "Paddock Cyan" fact cards
# Luxury base (obsidian, thin display type, champagne hairlines), cyan brand accent, and the GP's own
# track line colour. One fact per card; every number is large, with its unit right beside it.
# Carousel cards are 1080x1350; story cards are 1080x1920 with Instagram's top and bottom UI kept clear.

FONT = "Inter"
TEXT, MUTED, CYAN, GOLD, BASE = S.TEXT, S.MUTED, S.CYAN, S.GOLD_HAIR, S.TRACK_BASE
EV = CYAN                       # set per GP by set_event()
SPEED_CMAP = LinearSegmentedColormap.from_list("ev", [S.TRACK_BASE, CYAN])


def set_event(p: "Preview") -> None:
    """The GP's own line colour (hot pink for Las Vegas, cyan elsewhere)."""
    global EV, SPEED_CMAP
    EV = S.event_line(p.title)
    SPEED_CMAP = LinearSegmentedColormap.from_list("ev", ["#3A4458", EV])


def tracked(s: str, gap: int = 1) -> str:
    words = s.split(" ")
    return (" " * (2 * gap + 1)).join((" " * gap).join(w) for w in words)


class Card:
    def __init__(self, h: int, story: bool = False):
        self.h, self.story = h, story
        self.fig = plt.figure(figsize=(W / DPI, h / DPI), dpi=DPI)
        ax = self.fig.add_axes([0, 0, 1, 1], zorder=-10)
        yy = np.linspace(0, 1, 240)[:, None, None]
        img = (1 - yy) * np.array(_rgb(S.INK_BG_BOTTOM)) + yy * np.array(_rgb(S.INK_BG_TOP))
        ax.imshow(np.repeat(img, 4, axis=1), extent=[0, 1, 0, 1], aspect="auto", origin="lower", interpolation="bicubic")
        rng = np.random.default_rng(5)
        ax.imshow(rng.random((h // 4, W // 4)), cmap="gray", alpha=0.03, extent=[0, 1, 0, 1], aspect="auto")
        ax.axis("off")
        chequer(self.fig, h)
        self.top = 0.875 if story else 0.948
        self.bottom = 0.14 if story else 0.035

    def text(self, x, y, s, size, color=TEXT, weight=400, ha="center", track=False, **kw):
        return self.fig.text(x, y, tracked(s) if track else s, ha=ha, va="center", fontsize=size, color=color,
                             family=FONT, weight=weight, **kw)

    def rule(self, x0, x1, y, color=GOLD, lw=0.8):
        self.fig.add_artist(plt.Line2D([x0, x1], [y, y], transform=self.fig.transFigure, color=color, lw=lw))

    def header(self, p: "Preview"):
        flag = S.flag_image(p.country)
        y, x = self.top, 0.06
        hh = 0.022 * H_POST / self.h
        if flag is not None:
            w = hh * 1.5 * self.h / W
            ax = self.fig.add_axes([x, y - hh / 2, w, hh])
            ax.imshow(flag, aspect="auto")
            ax.axis("off")
            x += w + 0.018
        self.text(x, y, f"{gp_name(p).upper()} {p.season}", 16, weight=500, ha="left", track=True)
        self.text(0.94, y, f"ROUND {p.round}", 13, color=GOLD, weight=500, ha="right", track=True)
        self.rule(0.06, 0.94, y - 0.028 * H_POST / self.h, lw=0.6)

    def kicker(self, y, s, n=None, total=None):
        self.text(0.5, y, s.upper(), 16, color=CYAN, weight=600, track=True)
        if n:
            self.text(0.94, y, f"{n:02d} / {total:02d}", 13, color=MUTED, weight=400, ha="right")

    def number(self, y, value: str, unit: str, size=170, color=TEXT):
        """Thin hero number with its unit in cyan caps on the same baseline, centred as one block."""
        fig = self.fig
        r = fig.canvas.get_renderer()
        t1 = fig.text(0, y, value, fontsize=size, color=color, family=FONT, weight=200, va="baseline")
        t2 = fig.text(0, y, "  " + tracked(unit.upper()), fontsize=max(22, size * 0.17), color=CYAN, family=FONT,
                      weight=600, va="baseline")
        w1 = t1.get_window_extent(r).width / fig.bbox.width
        w2 = t2.get_window_extent(r).width / fig.bbox.width
        x0 = 0.5 - (w1 + w2) / 2
        t1.set_x(x0)
        t2.set_x(x0 + w1)
        return t1, t2

    def logo(self, x: float, y: float, w: float, ha: str = "left"):
        """The wordmark, w wide (figure fraction), vertically centred on y."""
        img = S.logo_image()
        if img is None:
            return
        h = w * W / S.LOGO_ASPECT / self.h
        x0 = x - w / 2 if ha == "center" else x - w if ha == "right" else x
        ax = self.fig.add_axes([x0, y - h / 2, w, h])
        ax.imshow(img, aspect="auto", interpolation="lanczos")
        ax.axis("off")

    def footer(self, right: str | None = None):
        """Logo left, website centre, optional cue right. On every card, every format."""
        y = self.bottom
        self.logo(0.06, y, 0.20)
        self.text(0.5 if right else 0.94, y, S.SITE.upper(), 13, color=MUTED, weight=500,
                  ha="center" if right else "right", track=True)
        if right:
            self.text(0.94, y, right, 14, color=CYAN, weight=600, ha="right", track=True)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(path, dpi=DPI, format="jpg", pil_kwargs={"quality": 94, "optimize": True})
        plt.close(self.fig)
        return path


def chequer(fig, h: int, sq: int = 12):
    """Chequered flag motif: a two row band along the top edge that fades out towards the centre,
    and a faint waving field rising from the bottom right corner. Drawn behind everything."""
    rgb = _rgb(TEXT)
    # top band, full width, 2 squares tall
    cols, rows = W // sq, 2
    g = (np.add.outer(np.arange(rows), np.arange(cols)) % 2).astype(float)
    x = np.linspace(0, 1, cols)
    fade = np.clip((np.abs(x - 0.5) - 0.12) / 0.38, 0, 1) ** 1.4   # strong at both edges, gone in the middle
    img = np.zeros((rows, cols, 4))
    img[..., :3] = rgb
    img[..., 3] = g * fade[None, :] * 0.45
    ax = fig.add_axes([0, 1 - rows * sq / h, 1, rows * sq / h], zorder=-9)
    ax.imshow(img, aspect="auto", interpolation="nearest", extent=[0, 1, 0, 1])
    ax.axis("off")
    # corner field: larger squares, sheared slightly so it reads as a flag in the wind
    big = 3 * sq
    cols, rows = int(0.46 * W / big), int(0.26 * h / big)
    yy, xx = np.mgrid[0:rows, 0:cols]
    wave = np.sin(xx / cols * math.pi * 1.5) * 0.9
    g = ((xx + np.floor(yy + wave)) % 2).astype(float)
    dx = (cols - 1 - xx) / cols
    dy = yy / rows                                              # row 0 is the bottom
    a = np.clip(1 - np.hypot(dx, dy) / 1.0, 0, 1) ** 2
    img = np.zeros((rows, cols, 4))
    img[..., :3] = rgb
    img[..., 3] = g * a * 0.08
    ax = fig.add_axes([1 - cols * big / W, 0, cols * big / W, rows * big / h], zorder=-9)
    ax.imshow(img, aspect="auto", interpolation="nearest", origin="lower", extent=[0, 1, 0, 1])
    ax.axis("off")


def tyre(ax, cx: float, cy: float, r: float, compound: str, code: str, label: bool = True, alpha: float = 1.0):
    """An original tyre glyph: rubber, a coloured sidewall band in the compound colour, rim, code in the hub."""
    from matplotlib.patches import Circle, Wedge
    col = COMPOUND_COLOR[compound]
    ax.add_patch(Circle((cx, cy), r, fc="#14171D", ec="#3A4150", lw=1.2, alpha=alpha, zorder=5))
    for a0 in (12, 102, 192, 282):                              # band with four short breaks, like sidewall text
        ax.add_patch(Wedge((cx, cy), r * 0.80, a0, a0 + 78, width=r * 0.08, fc=col, ec="none", alpha=alpha, zorder=6))
    ax.add_patch(Circle((cx, cy), r * 0.60, fc="#0B0E14", ec="#5A6272", lw=1.0, alpha=alpha, zorder=6))
    ax.text(cx, cy, code, ha="center", va="center", color=TEXT, fontsize=r * 0.42 * _pt(ax), family=FONT,
            weight=300, alpha=alpha, zorder=7)
    if label:
        ax.text(cx, cy - r * 1.32, compound, ha="center", va="center", color=col, fontsize=15, family=FONT,
                weight=600, alpha=alpha, zorder=7)


def _pt(ax) -> float:
    """Points per data unit along x, for text sized to a glyph."""
    fig = ax.figure
    bb = ax.get_position()
    x0, x1 = ax.get_xlim()
    return bb.width * fig.get_figwidth() * 72 / (x1 - x0)


def tyre_row(ax, t: dict, r: float = 1.0, labels: bool = True, alpha: float = 1.0):
    """Hard, medium, soft side by side in data units: ax spans x 0..9, y -2.2..1.4."""
    ax.set_xlim(0, 9)
    ax.set_ylim(-2.2, 1.4)
    ax.set_aspect("equal")
    ax.axis("off")
    for i, k in enumerate(("hard", "medium", "soft")):
        tyre(ax, 1.5 + 3 * i, 0, r, k.upper(), t[k], label=labels, alpha=alpha)


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


def base_line(ax, p: "Preview", lw=3.2):
    ax.plot(p.x, p.y, color=BASE, lw=lw, solid_capstyle="round", solid_joinstyle="round")


def highlight(ax, p: "Preview", mask: np.ndarray, color=None, lw=5):
    ax.plot(np.where(mask, p.x, np.nan), np.where(mask, p.y, np.nan), color=color or EV, lw=lw, solid_capstyle="round")


def speed_line(ax, p: "Preview", upto: int | None = None, lw=3.2):
    from matplotlib.collections import LineCollection
    n = len(p.x) if upto is None else max(2, upto)
    pts = np.column_stack([p.x[:n], p.y[:n]]).reshape(-1, 1, 2)
    lc = LineCollection(np.concatenate([pts[:-1], pts[1:]], axis=1), cmap=SPEED_CMAP,
                        norm=plt.Normalize(p.speed.min(), p.speed.max()), linewidths=lw, capstyle="round")
    lc.set_array(p.speed[: n - 1])
    ax.add_collection(lc)
    return lc


def dot(ax, x, y, color=None, ms=12, label=None, dx=0.0, dy=0.0, p=None):
    ax.plot([x], [y], "o", ms=ms, color=color or EV, mec=TEXT, mew=1.5, zorder=8)
    if label and p is not None:
        span = max(np.ptp(p.x), np.ptp(p.y))
        ax.plot([x, x + dx * span], [y, y + dy * span], color=GOLD, lw=0.8, zorder=7)
        ax.text(x + dx * span, y + dy * span, "  " + tracked(label.upper()), color=TEXT, fontsize=13, family=FONT,
                weight=600, zorder=9, ha="left", va="center")


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
                             dot(ax, p.x[imax], p.y[imax], label=f"{st['top_speed']} km/h", dx=0.08, dy=0.12, p=p))},
        {"kicker": "Flat out", "number": f"{st['flat_pct']}", "unit": "% of the lap",
         "line": "Throttle pinned, highlighted on the map", "source": f"Measured on the {lap}",
         "draw": lambda ax: (base_line(ax, p), highlight(ax, p, flat))},
        {"kicker": "Longest flat out run", "number": km(st["longest_flat_m"]), "unit": "km",
         "line": "Without lifting once", "source": f"Measured on the {lap}",
         "draw": lambda ax: (base_line(ax, p), highlight(ax, p, longest),
                             dot(ax, p.x[i0], p.y[i0], color=CYAN, ms=11), dot(ax, p.x[i1], p.y[i1], color=CYAN, ms=11))},
        {"kicker": "Braking zones", "number": f"{st['braking_zones']}", "unit": "per lap",
         "line": "Everything else is flat out or close to it", "source": f"Measured on the {lap}",
         "draw": lambda ax: brake_map(ax, p)},
    ]
    ly = p.last_year or {}
    if ly.get("pole_ms") and ly.get("pole"):
        out += pole_vs_race(p, ly)
    t = TYRES.get(p.title)
    if t:
        out.append({"kicker": "Tyres", "number": "3", "unit": f"{trio(t)} of {t['range']}",
                    "line": f"{t['hard']} {t['medium']} {t['soft']}, {streak_text(t)}",
                    "source": f"{t['why']}. Source: {t['source']}", "tyres": t,
                    "draw": lambda ax: tyre_row(ax, t)})
    return out


def pole_vs_race(p: "Preview", ly: dict) -> list[dict]:
    """Last year's pole against the race's fastest lap, always with the reason. A wet qualifying
    gets the rain card with the pole sitter's tyre; a dry one gets pole vs race; unknown
    conditions get no card (an unexplained 14.6 s gap is misleading)."""
    gap = ly["pole_ms"] / 1000 - p.lap_s
    pole_t, race_t = lap_time(ly["pole_ms"]), lap_time(round(p.lap_s * 1000))
    race_src = f"Fastest race lap: {p.driver} {race_t}"
    if ly.get("quali_wet") is True and gap > 0:
        comp = WET_COMPOUNDS.get(ly.get("pole_compound") or "")
        on = f" on {'intermediates' if comp == 'INTER' else 'full wets'}" if comp else ""
        return [{"kicker": f"{p.ref_year} rain qualifying", "number": f"{gap:.1f}", "unit": "s slower",
                 "line": f"Wet pole, {ly['pole']} {pole_t}{on}, vs the dry race",
                 "source": f"{race_src}. Official results; OpenF1 weather and tyre data",
                 "draw": lambda ax: (base_line(ax, p), speed_line(ax, p, lw=6), comp and tyre_badge(ax, comp))}]
    if ly.get("quali_wet") is False and gap < 0:
        return [{"kicker": f"{p.ref_year} pole vs race", "number": f"{-gap:.1f}", "unit": "s faster",
                 "line": f"Pole, {ly['pole']} {pole_t}: low fuel and fresh tyres",
                 "source": f"{race_src}. Official results",
                 "draw": lambda ax: (base_line(ax, p), speed_line(ax, p, lw=6))}]
    return []


def tyre_badge(ax, compound: str):
    """One labelled tyre in the emptiest spot of the track map (furthest from the racing line),
    so it never sits on the track whatever the circuit's shape."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    pts = np.column_stack([ax.lines[0].get_xdata(), ax.lines[0].get_ydata()])[::3] if ax.lines else np.zeros((1, 2))
    gx, gy = np.meshgrid(np.linspace(x0, x1, 48), np.linspace(y0, y1, 36))
    cand = np.column_stack([gx.ravel(), gy.ravel()])
    d = np.sqrt(((cand[:, None, :] - pts[None, :, :]) ** 2).sum(-1)).min(1)
    edge = np.minimum.reduce([cand[:, 0] - x0, x1 - cand[:, 0], cand[:, 1] - y0, y1 - cand[:, 1]])
    room = np.minimum(d, edge)
    k = int(np.argmax(room))
    r = min(0.42 * room[k], 0.09 * (x1 - x0))
    cx, cy = cand[k]
    tyre(ax, cx, cy + 0.3 * r, r, compound, "I" if compound == "INTER" else "W")
    return ax


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


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
        ax.text(p.x[a_] + vx / d * 0.08 * span, p.y[a_] + vy / d * 0.08 * span, str(n), color=TEXT,
                fontsize=15, family=FONT, weight=500, ha="center", va="center", zorder=9,
                bbox=dict(boxstyle="circle,pad=0.4", fc="none", ec=CYAN, lw=1.2))


def cover(p: "Preview", h: int, story: bool, n_facts: int) -> Card:
    c = Card(h, story)
    c.header(p)
    t = c.top
    c.text(0.5, t - 0.075, "UP NEXT", 16, color=CYAN, weight=600, track=True)
    c.text(0.5, t - 0.135, p.title, 76 if len(p.title) <= 10 else 58, weight=200, track=True)
    c.text(0.5, t - (0.205 if not story else 0.19), "How fast is it, really?", 26, color=MUTED, weight=300, style="italic")
    rect = [0.10, 0.27, 0.80, 0.42] if not story else [0.08, 0.33, 0.84, 0.36]
    ax = track_ax(c, rect, p)
    base_line(ax, p, lw=5)
    speed_line(ax, p, lw=3.6)
    q, r = times_text(p)
    y = 0.215 if not story else 0.27
    t = TYRES.get(p.title)
    if t:
        tax = c.fig.add_axes([0.41, y + 0.022, 0.18, 0.05 * H_POST / h])
        tyre_row(tax, t, labels=False)
    else:
        c.rule(0.44, 0.56, y + 0.035)
    c.text(0.5, y, f"{n_facts} FACTS BEFORE LIGHTS OUT", 18, color=CYAN, weight=600, track=True)
    c.text(0.5, y - 0.05, f"Quali {q}   |   Race {r}   |   local time", 17, color=MUTED, weight=400)
    c.footer("SWIPE  →" if not story else "TAP  →")
    return c


def fact_card(p: "Preview", f: dict, n: int, total: int, h: int, story: bool) -> Card:
    c = Card(h, story)
    c.header(p)
    t = c.top
    c.kicker(t - 0.07, f["kicker"], n, total)
    c.number(t - (0.235 if not story else 0.195), f["number"], f["unit"], size=170 if not story else 180)
    c.text(0.5, t - (0.285 if not story else 0.235), f["line"], 24, weight=300)
    if "tyres" in f:
        rect = [0.05, 0.19, 0.90, 0.42] if not story else [0.04, 0.28, 0.92, 0.34]
        f["draw"](c.fig.add_axes(rect))
    else:
        rect = [0.10, 0.16, 0.80, 0.42] if not story else [0.08, 0.29, 0.84, 0.32]
        f["draw"](track_ax(c, rect, p))
    c.text(0.5, (0.115 if not story else 0.235), f["source"], 14, color=MUTED, weight=300)
    c.footer("SWIPE  →" if not story else None)
    return c


def closing(p: "Preview", h: int, story: bool) -> Card:
    c = Card(h, story)
    c.header(p)
    logo = S.logo_image()
    if logo is not None:
        ax = c.fig.add_axes([0.32, 0.67 if not story else 0.62, 0.36, 0.11])
        ax.imshow(logo)
        ax.axis("off")
    q, r = times_text(p)
    for x, k, v in ((0.30, "QUALIFYING", q), (0.70, "RACE", r)):
        c.text(x, 0.53, k, 14, color=CYAN, weight=600, track=True)
        c.text(x, 0.485, v, 38, weight=200)
    c.fig.add_artist(plt.Line2D([0.5, 0.5], [0.46, 0.55], transform=c.fig.transFigure, color=GOLD, lw=0.6))
    c.text(0.5, 0.425, "LOCAL TIME", 12, color=MUTED, weight=500, track=True)
    c.text(0.5, 0.33, "EVERY SESSION", 34, weight=200, track=True)
    c.text(0.5, 0.285, "DECODED", 34, color=CYAN, weight=300, track=True)
    c.rule(0.45, 0.55, 0.245)
    c.text(0.5, 0.20, f"Follow {S.HANDLE} so you don't miss quali", 22, weight=400)
    c.footer()
    return c


def carousel(p: Preview, out: Path) -> list[Path]:
    set_event(p)
    fs = facts(p)
    paths = [cover(p, H_POST, False, len(fs)).save(out / "slide_01.jpg")]
    for i, f in enumerate(fs, 1):
        paths.append(fact_card(p, f, i, len(fs), H_POST, False).save(out / f"slide_{i + 1:02d}.jpg"))
    paths.append(closing(p, H_POST, False).save(out / f"slide_{len(fs) + 2:02d}.jpg"))
    return paths


def stories(p: Preview, out: Path) -> list[Path]:
    set_event(p)
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
    """Title fades in over a moving lap: the GP's line draws itself with a live km/h readout, then the facts."""
    set_event(p)
    st = p.stats
    r = Reel(out / "reel.mp4")
    c = Card(H_REEL, story=True)
    c.header(p)
    up = c.text(0.5, 0.80, "UP NEXT", 18, color=CYAN, weight=600, track=True, alpha=0)
    name = c.text(0.5, 0.755, p.title, 70 if len(p.title) <= 10 else 54, weight=200, track=True, alpha=0)
    ax = track_ax(c, [0.06, 0.36, 0.88, 0.33], p)
    base_line(ax, p, lw=5)
    head, = ax.plot([], [], "o", ms=16, color=TEXT, mec=EV, mew=4, zorder=9)
    num = c.fig.text(0.5, 0.285, "", fontsize=150, color=TEXT, family=FONT, weight=200, ha="center", va="center")
    unit = c.text(0.5, 0.225, "", 20, color=CYAN, weight=600, track=True)
    c.footer()

    n = int(lap_s * FPS)
    line = None
    for i in range(n + 1):
        k = int(round((len(p.x) - 1) * i / n))
        e_ = ease(i / (0.9 * FPS))
        up.set_alpha(e_)
        name.set_alpha(e_)
        if line is not None:
            line.remove()
        line = speed_line(ax, p, upto=k + 1, lw=4)
        head.set_data([p.x[k]], [p.y[k]])
        num.set_text(f"{int(p.speed[k])}")
        unit.set_text("KM/H")
        r.add(c.fig)
        if i == int(0.55 * n):
            c.fig.savefig(out / "cover.jpg", dpi=DPI, format="jpg", pil_kwargs={"quality": 94})
    head.set_data([], [])
    num.set_text("")
    unit.set_text("")

    q, rr = times_text(p)
    flashes = [(f"{st['top_speed']}", "km/h", "Top speed"), (f"{st['flat_pct']}", "% flat out", "Of the lap"),
               (km(st["longest_flat_m"]), "km", "Longest run without lifting"),
               (f"{st['braking_zones']}", "zones", "Braking per lap")]
    for big, u, lbl in flashes:
        t1, t2 = c.number(0.25, big, u, size=150)
        t3 = c.text(0.5, 0.20, lbl.upper(), 18, color=MUTED, weight=500, track=True)
        for i in range(int(0.9 * FPS)):
            a_ = ease(i / (0.25 * FPS))
            for t in (t1, t2, t3):
                t.set_alpha(a_)
            r.add(c.fig)
        for t in (t1, t2, t3):
            t.remove()
    t = TYRES.get(p.title)
    if t:                                                       # the tyres, so it reads F1 at a glance
        tax = c.fig.add_axes([0.12, 0.175, 0.76, 0.12])
        lbl = c.text(0.5, 0.345, f"TYRES  {t['hard']}  {t['medium']}  {t['soft']}", 18, color=CYAN, weight=600, track=True)
        sub = c.text(0.5, 0.312, f"{trio(t).upper()} 3 OF {t['range']}", 15, color=MUTED, weight=500, track=True)
        for i in range(int(1.4 * FPS)):
            a_ = ease(i / (0.3 * FPS))
            tax.clear()
            tyre_row(tax, t, labels=True, alpha=a_)
            lbl.set_alpha(a_)
            sub.set_alpha(a_)
            r.add(c.fig)
        tax.remove()
        lbl.remove()
        sub.remove()
    c.text(0.5, 0.27, f"QUALI  {q.upper()}", 30, weight=300, track=False)
    c.text(0.5, 0.23, f"RACE  {rr.upper()}", 30, color=CYAN, weight=400)
    c.text(0.5, 0.195, "LOCAL TIME", 13, color=MUTED, weight=500, track=True)
    r.add(c.fig, int(1.8 * FPS))
    plt.close(c.fig)
    return r.close(), out / "cover.jpg"


def caption(p: Preview, kind: str) -> str:
    st = p.stats
    q, r = times_text(p)
    ly = p.last_year or {}
    c = p.colors
    t = TYRES.get(p.title)
    lap = [f"📊 Last year's fastest race lap: {_drv(p.driver, c)}, {lap_time(round(p.lap_s * 1000))}",
           f"🚀 Top speed: {st['top_speed']} km/h",
           f"🟢 Flat out: {st['flat_pct']}% of the lap",
           f"📏 Longest run without lifting: {km(st['longest_flat_m'])} km",
           f"🛑 Braking zones: {st['braking_zones']}"]
    tyres = ([f"🛞 Tyres: {t['hard']} hard, {t['medium']} medium, {t['soft']} soft",
              f"Pirelli's {trio(t)} 3 of {t['range']}, {streak_text(t)}. {t['why']}."] if t else None)
    last = None
    if ly.get("winner"):
        last = f"🏆 Last year: {_drv(ly['winner'], c)} won" + (f", {_drv(ly['pole'], c)} took pole" if ly.get("pole") else "")
    return clean(paragraphs(
        f"🏎️ How fast is {p.title.title()}? {st['top_speed']} km/h fast.",
        lap, tyres, last,
        f"⏰ Quali {q}\n🏁 Race {r}\n(local time)",
        "💾 Save this for race week and follow so you don't miss quali." if kind != "reel"
        else "🔔 Follow so you don't miss quali.",
        "💬 Where will pole be won? Tell us below.",
        FOOTER, " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Telemetry", "#RaceWeek"])))
