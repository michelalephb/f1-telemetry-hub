"""Page level pieces in the Paddock Cyan template: the pinned "Start here" carousel, the race day
numbers card, and the story highlight covers (2027 set). Original glyphs only.
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle, Wedge

from . import preview as P
from . import style as S
from .captions import FOOTER, clean, event_tag, paragraphs
from .gp_facts import RACE_DAY, TYRES, trio
from .render import H_POST, H_REEL, W


def brand_header(c: P.Card, right: str = "2026 SEASON"):
    y = c.top
    c.text(0.06, y, "F1 TELEMETRY HUB", 16, weight=500, ha="left", track=True)
    c.text(0.94, y, right, 13, color=P.GOLD, weight=500, ha="right", track=True)
    c.rule(0.06, 0.94, y - 0.028 * H_POST / c.h, lw=0.6)


# ---------------------------------------------------------------- Start here (pinned)

def _row(c, y, title, line, glyph):
    ax = c.fig.add_axes([0.08, y - 0.045, 0.12, 0.09 * W / W])
    glyph(ax)
    c.text(0.25, y + 0.014, title, 26, weight=400, ha="left")
    c.text(0.25, y - 0.022, line, 18, color=P.MUTED, weight=300, ha="left")


def start_here(out: Path) -> list[Path]:
    paths = []
    c = P.Card(H_POST)
    brand_header(c, "START HERE")
    c.logo(0.5, 0.70, 0.62, ha="center")
    c.text(0.5, 0.58, "EVERY SESSION", 44, weight=200, track=True)
    c.text(0.5, 0.525, "DECODED", 44, color=P.CYAN, weight=300, track=True)
    ax = c.fig.add_axes([0.35, 0.33, 0.30, 0.12])
    tyres_glyph(ax)
    c.text(0.5, 0.26, "Formula 1 in numbers, not opinions", 26, weight=300)
    c.text(0.5, 0.215, "Official timing. Real telemetry. Every number sourced.", 19, color=P.MUTED, weight=300)
    c.footer("SWIPE  →")
    paths.append(c.save(out / "slide_01.jpg"))

    c = P.Card(H_POST)
    brand_header(c, "WHAT YOU GET")
    c.text(0.5, 0.86, "EVERY RACE WEEKEND", 16, color=P.CYAN, weight=600, track=True)
    rows = [("Race week", "6 facts on the next track, from last year's fastest lap", glyph_track),
            ("Qualifying decoded", "Pole lap vs P2, sector by sector, apex speeds", glyph_stopwatch),
            ("Race decoded", "Top 5 lap by lap, the biggest climb", glyph_flag),
            ("Telemetry", "Speed, throttle, brake and gear against distance", glyph_trace),
            ("History in numbers", "Every circuit's past, every fact sourced", glyph_history)]
    for k, (t, l, g) in enumerate(rows):
        _row(c, 0.76 - k * 0.125, t, l, g)
    c.footer("SWIPE  →")
    paths.append(c.save(out / "slide_02.jpg"))

    c = P.Card(H_POST)
    brand_header(c, "HOW IT WORKS")
    steps = [("01", "Chequered flag", "The session ends"),
             ("02", "Official timing", "Results, sectors, lap times"),
             ("03", "Telemetry", "Speed, throttle, brake, gear, position"),
             ("04", "Posted here", "Charts within hours, numbers checked")]
    for k, (n, t, l) in enumerate(steps):
        y = 0.80 - k * 0.15
        c.text(0.10, y, n, 64, color=P.CYAN, weight=200, ha="left")
        c.text(0.30, y + 0.018, t, 28, weight=400, ha="left")
        c.text(0.30, y - 0.022, l, 19, color=P.MUTED, weight=300, ha="left")
        if k < 3:
            c.rule(0.30, 0.94, y - 0.07, color="#1E2533", lw=0.8)
    c.text(0.5, 0.17, "Unofficial fan analysis. Not associated with Formula 1.", 15, color=P.MUTED, weight=300)
    c.footer("SWIPE  →")
    paths.append(c.save(out / "slide_03.jpg"))

    c = P.Card(H_POST)
    brand_header(c, "FOLLOW")
    c.logo(0.5, 0.66, 0.66, ha="center")
    c.text(0.5, 0.53, "f1telemetryhub.com", 40, color=P.CYAN, weight=300)
    c.text(0.5, 0.48, "Compare any two drivers, corner by corner. Link in bio", 20, color=P.MUTED, weight=300)
    c.rule(0.45, 0.55, 0.42)
    c.text(0.5, 0.36, f"Follow {S.HANDLE}", 30, weight=300)
    c.text(0.5, 0.315, "so you never miss a session decoded", 20, color=P.MUTED, weight=300)
    c.footer()
    paths.append(c.save(out / "slide_04.jpg"))
    return paths


def start_here_caption() -> str:
    return clean("\n".join([
        "Start here. F1 Telemetry Hub decodes every Formula 1 session in numbers.",
        "",
        "Every race weekend:",
        "Race week: 6 facts on the next track, from last year's fastest lap.",
        "Qualifying decoded: pole lap vs P2, sector by sector, apex speeds.",
        "Race decoded: top 5 lap by lap and the biggest climb.",
        "Telemetry: speed, throttle, brake and gear against distance.",
        "History in numbers: every circuit's past, every fact sourced.",
        "",
        "Official timing and real telemetry. No opinions, no guesses.",
        "", FOOTER, "", "#F1 #Formula1 #F1Telemetry #F1Data #DataViz"]))


# ---------------------------------------------------------------- Race day in numbers

def race_day(p, out: Path) -> Path:
    P.set_event(p)
    f = RACE_DAY[p.title]
    t = TYRES.get(p.title)
    c = P.Card(H_POST)
    c.header(p)
    top = c.top
    c.kicker(top - 0.07, "Race day in numbers")
    q, r = P.times_text(p)
    c.text(0.5, top - 0.115, f"Lights out {r}, local time", 24, weight=300)
    tiles = [(str(f["laps"]), "LAPS"), (f["lap_km"], "KM A LAP"), (f["race_km"], "KM RACE DISTANCE"),
             (str(f["corners"]), "CORNERS"), (f["lap_record"], f"LAP RECORD, {f['lap_record_by']}"),
             (f"{t['hard']} {t['medium']} {t['soft']}" if t else "",
              f"TYRES, {trio(t).upper()} 3 OF {t['range']}" if t else "TYRES")]
    for k, (v, u) in enumerate(tiles):
        col, row = k % 2, k // 2
        x0, y0 = 0.07 + col * 0.44, 0.60 - row * 0.19
        c.fig.add_artist(FancyBboxPatch((x0, y0), 0.42, 0.165, boxstyle="round,pad=0,rounding_size=0.012",
                                        transform=c.fig.transFigure, fc="#141923", ec="#232D3F", lw=1, zorder=1))
        c.text(x0 + 0.21, y0 + 0.10, v, 54 if len(v) < 7 else 44, weight=200, zorder=2)
        c.text(x0 + 0.21, y0 + 0.035, u, 12, color=P.CYAN, weight=600, track=True, zorder=2)
    c.text(0.5, 0.115, f"Source: {f['source']}", 14, color=P.MUTED, weight=300)
    c.footer()
    path = out / "race_day.jpg"
    c.save(path)
    return path


def race_day_caption(p) -> str:
    f = RACE_DAY[p.title]
    t = TYRES.get(p.title)
    q, r = P.times_text(p)
    return clean(paragraphs(
        f"🏁 Race day in {p.title.title()}. Lights out {r}, local time.",
        [f"🔁 {f['laps']} laps of {f['lap_km']} km", f"📏 {f['race_km']} km in all", f"↪️ {f['corners']} corners a lap",
         f"⏱️ Lap record: {f['lap_record']}, {f['lap_record_by']}"]
        + ([f"🛞 Tyres: {t['hard']} hard, {t['medium']} medium, {t['soft']} soft"] if t else []),
        f"📚 Sources: {f['source']}.",
        "🔔 Race decoded here after the flag. Follow so you don't miss it.\n💬 Your winner? Tell us below.",
        FOOTER, " ".join(["#F1", "#Formula1", event_tag(p.event), "#RaceDay", "#F1Telemetry"])))


# ---------------------------------------------------------------- glyphs (original, line style)

def _glyph_ax(ax, lim=1.2):
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.axis("off")


def glyph_stopwatch(ax, col=None, lw=3):
    col = col or P.CYAN
    _glyph_ax(ax)
    ax.add_patch(Circle((0, -0.1), 0.85, fc="none", ec=col, lw=lw))
    ax.plot([0, 0], [-0.1, 0.45], color=col, lw=lw, solid_capstyle="round")
    ax.plot([0, 0.35], [-0.1, -0.3], color=col, lw=lw, solid_capstyle="round")
    ax.add_patch(Rectangle((-0.18, 0.8), 0.36, 0.16, fc=col, ec="none"))


def glyph_flag(ax, col=None, lw=3):
    col = col or P.CYAN
    _glyph_ax(ax)
    ax.plot([-0.75, -0.75], [-1.0, 0.95], color=col, lw=lw, solid_capstyle="round")
    n, s = 4, 0.4
    for i in range(n):
        for j in range(3):
            if (i + j) % 2 == 0:
                ax.add_patch(Rectangle((-0.75 + i * s, 0.95 - (j + 1) * s), s, s, fc=col, ec="none"))
    ax.add_patch(Rectangle((-0.75, 0.95 - 3 * s), n * s, 3 * s, fc="none", ec=col, lw=lw * 0.6))


def glyph_trace(ax, col=None, lw=3):
    """A speed trace: straights and braking dips, like the lap in data chart."""
    col = col or P.CYAN
    _glyph_ax(ax)
    x = np.linspace(-1, 1, 200)
    y = 0.6 - sum(1.1 * np.exp(-((x - c) / w) ** 2) for c, w in ((-0.55, 0.06), (0.05, 0.08), (0.6, 0.05)))
    ax.plot(x, y, color=col, lw=lw, solid_capstyle="round", solid_joinstyle="round")
    ax.plot([-1, 1], [-0.85, -0.85], color=col, lw=lw * 0.5, alpha=0.5)


def glyph_history(ax, col=None, lw=3):
    col = col or P.CYAN
    _glyph_ax(ax)
    ax.plot([-1, 1], [0, 0], color=col, lw=lw * 0.6, alpha=0.7)
    for x in (-0.9, -0.3, 0.3, 0.9):
        ax.add_patch(Circle((x, 0), 0.13, fc=col, ec="none"))
    ax.add_patch(Circle((0.9, 0), 0.26, fc="none", ec=col, lw=lw * 0.7))


def glyph_track(ax, col=None, lw=3):
    """A generic circuit: long straight, hairpin, esses. Not any real track."""
    col = col or P.CYAN
    _glyph_ax(ax)
    pts = np.array([(-0.95, -0.55), (0.75, -0.55), (0.95, -0.35), (0.95, 0.05), (0.55, 0.15), (0.35, 0.55),
                    (0.05, 0.6), (-0.15, 0.3), (-0.45, 0.35), (-0.6, 0.65), (-0.9, 0.6), (-0.95, -0.55)])
    t = np.linspace(0, 1, len(pts))
    tt = np.linspace(0, 1, 300)
    from scipy.interpolate import make_interp_spline
    try:
        sx = make_interp_spline(t, pts[:, 0], k=2)(tt)
        sy = make_interp_spline(t, pts[:, 1], k=2)(tt)
    except Exception:
        sx, sy = pts[:, 0], pts[:, 1]
    ax.plot(sx, sy, color=col, lw=lw, solid_capstyle="round", solid_joinstyle="round")
    ax.add_patch(Circle((sx[20], sy[20]), 0.1, fc=P.TEXT, ec="none"))


def glyph_info(ax, col=None, lw=3):
    col = col or P.CYAN
    _glyph_ax(ax)
    ax.add_patch(Circle((0, 0), 0.95, fc="none", ec=col, lw=lw))
    ax.add_patch(Circle((0, 0.45), 0.11, fc=col, ec="none"))
    ax.plot([0, 0], [-0.55, 0.12], color=col, lw=lw * 1.6, solid_capstyle="round")


def tyres_glyph(ax):
    P.tyre_row(ax, {"hard": "", "medium": "", "soft": ""}, labels=False)


def glyph_tyre(ax, col=None, lw=3):
    _glyph_ax(ax, 1.2)
    P.tyre(ax, 0, 0, 1.15, "SOFT", "S", label=False)


def glyph_year(text):
    def g(ax, col=None, lw=3):
        _glyph_ax(ax)
        ax.text(0, 0, text, ha="center", va="center", color=col or P.CYAN, fontsize=200, family=P.FONT, weight=200)
    return g


# ---------------------------------------------------------------- highlight covers (2027 set)

HIGHLIGHTS = [("start", "START HERE", glyph_info), ("raceweek", "RACE WEEK", glyph_track),
              ("quali", "QUALI", glyph_stopwatch), ("races", "RACES", glyph_flag),
              ("tyres", "TYRES", glyph_tyre), ("data", "TELEMETRY", glyph_trace),
              ("history", "HISTORY", glyph_history), ("2026", "2026", glyph_year("26"))]


def highlight_cover(key: str, glyph, out: Path) -> Path:
    """1080x1920 story image; Instagram crops the highlight bubble to the centre circle, so the
    glyph sits inside a champagne ring centred on the frame. Nothing else matters outside it."""
    c = P.Card(H_REEL, story=True)
    cx, cy = 0.5, 0.5
    r = 0.46                                  # of the width
    rh = r * W / H_REEL
    ring = c.fig.add_axes([cx - r, cy - rh, 2 * r, 2 * rh])
    ring.set_xlim(-1, 1)
    ring.set_ylim(-1, 1)
    ring.set_aspect("equal")
    ring.axis("off")
    ring.add_patch(Circle((0, 0), 0.98, fc="#0B0E14", ec=P.GOLD, lw=2.2))
    ring.add_patch(Circle((0, 0), 0.90, fc="none", ec="#232D3F", lw=1))
    g = 0.27
    gh = g * W / H_REEL
    glyph(c.fig.add_axes([cx - g, cy - gh, 2 * g, 2 * gh]), lw=7)
    path = out / f"highlight_{key}.jpg"
    c.save(path)
    return path


def highlight_covers(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    return [highlight_cover(k, g, out) for k, _, g in HIGHLIGHTS]
