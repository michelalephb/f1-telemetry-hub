"""Profile assets for @f1telemetryhub (Michel, 20 Nov 2026 growth plan): highlight covers that never go out of
date (no flags, no years) and the three Start here story cards that explain the Reels to a new visitor.

Instagram shows a highlight cover as a circle cut from the centre of a 9:16 image, so every glyph sits inside
the central circle. Highlights cannot be set through the publishing API: Michel adds them in the app.

    python -m pipeline.social.highlights OUT_DIR
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from . import preview as P
from . import style as S
from .brand import brand_header, tyres_glyph
from .render import H_REEL, W

COVERS = ("start_here", "braking", "pedal_data", "rules_2026", "this_gp")
THROTTLE, BRAKE = "#10B981", "#EF4444"          # same colours as the pedal Reels


def _glyph_axes(c: P.Card):
    """A square axes on the central circle Instagram keeps, in data units -1..1, with a champagne hairline ring."""
    side = 0.62                                   # share of the width
    h = side * W / H_REEL
    ax = c.fig.add_axes([(1 - side) / 2, 0.5 - h / 2, side, h])
    ax.set_xlim(-1, 1), ax.set_ylim(-1, 1), ax.set_aspect("equal"), ax.axis("off")
    t = np.linspace(0, 2 * np.pi, 400)
    ax.plot(0.97 * np.cos(t), 0.97 * np.sin(t), color=P.GOLD, lw=1.6)
    return ax


def cover(name: str, out: Path) -> Path:
    c = P.Card(H_REEL, story=True)
    ax = _glyph_axes(c)
    lw = 9
    if name == "start_here":                      # play
        ax.add_patch(plt.Polygon([[-0.28, -0.42], [-0.28, 0.42], [0.46, 0.0]], closed=True, fill=False,
                                 ec=P.CYAN, lw=lw, joinstyle="round"))
    elif name == "braking":                       # speed into a corner: flat, brake, apex, power out
        x = np.linspace(-0.62, 0.62, 300)
        v = np.where(x < -0.15, 0.38, 0.0)
        v = np.where((x >= -0.15) & (x < 0.12), 0.38 - 1.15 * (x + 0.15) * (1 - 0.6 * (x + 0.15)), v)
        apex = 0.38 - 1.15 * 0.27 * (1 - 0.6 * 0.27)
        v = np.where(x >= 0.12, apex + 0.9 * (x - 0.12), v)
        v = np.minimum(v, 0.38)
        ax.plot(x, v - 0.05, color=P.CYAN, lw=lw, solid_capstyle="round", solid_joinstyle="round")
        ax.plot([0.12], [apex - 0.05], "o", ms=22, color=P.GOLD)
        ax.plot([-0.15, -0.15], [-0.45, 0.45], color=P.MUTED, lw=2.5, ls=(0, (2, 3)))
    elif name == "pedal_data":                    # throttle and brake bars
        for x0, hgt, col in ((-0.36, 0.86, THROTTLE), (0.10, 0.40, BRAKE)):
            ax.add_patch(plt.Rectangle((x0, -0.45), 0.26, 0.9, fill=False, ec="#3A4252", lw=3))
            ax.add_patch(plt.Rectangle((x0, -0.45), 0.26, hgt, fc=col, ec="none"))
    elif name == "rules_2026":
        ax.text(0, -0.02, "26", ha="center", va="center", fontsize=230, color=P.CYAN, family=P.FONT, weight=200)
    elif name == "this_gp":                       # chequered flag
        n, s = 5, 0.17
        for i in range(n):
            for j in range(n):
                if (i + j) % 2 == 0:
                    ax.add_patch(plt.Rectangle((-n * s / 2 + i * s, -n * s / 2 + j * s), s, s, fc=P.TEXT, ec="none"))
        ax.add_patch(plt.Rectangle((-n * s / 2, -n * s / 2), n * s, n * s, fill=False, ec=P.CYAN, lw=3))
    else:
        raise ValueError(name)
    return c.save(out)


def _story(title: str) -> P.Card:
    c = P.Card(H_REEL, story=True)
    brand_header(c, title)
    return c


def start_here(out: Path) -> list[Path]:
    """Three 9:16 story cards for the START HERE highlight: what this is, how to read the two Reels people
    watch most (pedal and braking), and where to find more."""
    paths = []

    c = _story("START HERE")
    c.logo(0.5, 0.70, 0.62, ha="center")
    c.text(0.5, 0.60, "EVERY F1 SESSION", 34, weight=200, track=True)
    c.text(0.5, 0.565, "DECODED IN TELEMETRY", 34, color=P.CYAN, weight=300, track=True)
    ax = c.fig.add_axes([0.35, 0.43, 0.30, 0.07])
    tyres_glyph(ax)
    c.text(0.5, 0.375, "Braking points. Pedal traces. Pole laps.", 28, weight=300)
    c.text(0.5, 0.34, "New Reels after every qualifying and race", 20, color=P.MUTED, weight=300)
    c.text(0.5, 0.29, "Official timing and OpenF1 telemetry, every number sourced", 17, color=P.MUTED, weight=300)
    c.footer("TAP  →")
    paths.append(c.save(out / "start_here_01.jpg"))

    c = _story("HOW TO READ")
    c.text(0.5, 0.80, "THE PEDAL REELS", 16, color=P.CYAN, weight=600, track=True)
    c.text(0.5, 0.765, "One lap from the inside, live on the track map", 24, weight=300)
    rows = [(THROTTLE, "Throttle", "Green bar: how far the pedal is down, 0 to 100 %"),
            (BRAKE, "Brake", "Red bar: brake on or off"),
            (P.TEXT, "Gear", "The big number, 1 to 8"),
            (P.CYAN, "Speed", "km/h at that point of the lap"),
            (P.GOLD, "Clock", "Turns gold on the official lap time")]
    for k, (col, t, line) in enumerate(rows):
        y = 0.68 - k * 0.085
        c.fig.add_artist(plt.Rectangle((0.10, y - 0.018), 0.035, 0.036 * W / H_REEL * 1.0,
                                       transform=c.fig.transFigure, fc=col, ec="none"))
        c.text(0.18, y + 0.012, t, 28, weight=400, ha="left")
        c.text(0.18, y - 0.016, line, 18, color=P.MUTED, weight=300, ha="left")
    c.text(0.5, 0.22, "Shown faster than real time; the speed factor is on screen", 16, color=P.MUTED, weight=300)
    c.footer("TAP  →")
    paths.append(c.save(out / "start_here_02.jpg"))

    c = _story("HOW TO READ")
    c.text(0.5, 0.80, "WHO BRAKES LATEST", 16, color=P.CYAN, weight=600, track=True)
    c.text(0.5, 0.765, "Every green lap of a race, one braking zone", 24, weight=300)
    c.text(0.5, 0.735, "EXAMPLE", 12, color=P.MUTED, weight=600, track=True)
    ax = c.fig.add_axes([0.14, 0.58, 0.72, 0.14])
    ax.set_xlim(0, 140), ax.set_ylim(-0.6, 2.6), ax.invert_yaxis(), ax.axis("off")
    # team colours, never brand cyan for data (palette v02); example values, not real data
    for k, (m, e, col, lead) in enumerate(((92, 3, "#3671C6", True), (97, 4, "#FF8000", False), (118, 14, "#3A4252", False))):
        ax.barh(k, m, height=0.6, color=col, edgecolor=P.GOLD if lead else "none", linewidth=2.5)
        ax.text(m + 3, k, f"{m} m  ±{e}", va="center", fontsize=15, color=P.GOLD if lead else P.TEXT, family=P.FONT)
    rows = [("Shorter bar", "Brakes later: metres from brake on to the slowest point"),
            ("Gold outline", "The latest braker with a clean measurement"),
            ("±", "Standard error over that driver's laps"),
            ("Grey", "Fewer than 10 laps or ±10 m or more: low confidence")]
    for k, (t, line) in enumerate(rows):
        y = 0.51 - k * 0.07
        c.text(0.10, y + 0.012, t, 26, weight=400, ha="left")
        c.text(0.10, y - 0.015, line, 18, color=P.MUTED, weight=300, ha="left")
    c.rule(0.45, 0.55, 0.24)
    c.text(0.5, 0.21, f"Follow {S.HANDLE}  ·  {S.SITE}", 20, color=P.CYAN, weight=300)
    c.footer()
    paths.append(c.save(out / "start_here_03.jpg"))
    return paths


def build(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    return [cover(n, out / f"cover_{n}.jpg") for n in COVERS] + start_here(out)


if __name__ == "__main__":
    for p in build(Path(sys.argv[1] if len(sys.argv) > 1 else "out/highlights")):
        print(p)
