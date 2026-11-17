"""History Reel ("A history in numbers"): one hand checked fact per chapter, each with a hero number,
its unit and its source, walked along a timeline with a tyre as the marker. Same Paddock Cyan
template as the preview: flag and GP name on top, chequered motif, logo and website on every frame.

Facts come from gp_facts.HISTORY only. A GP with no entry gets no history Reel.
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from . import style as S
from .captions import FOOTER, clean, event_tag
from .gp_facts import HISTORY
from .preview import (CYAN, FONT, GOLD, MUTED, TEXT, Card, Preview, ease, gp_name, set_event, times_text, tyre)
from .render import FPS, H_REEL, W, Reel

HOLD_S = 2.3        # each chapter on screen
FADE_S = 0.3


def available(p: Preview) -> bool:
    return p.title in HISTORY


def _years(ch: dict) -> list[int]:
    return [int(y) for y in re.findall(r"\d{4}", ch["year"])]


class Timeline:
    """Years along the bottom, a break for the gap, a soft tyre that travels to the active year."""

    def __init__(self, c: Card, years: list[int], y: float = 0.29):
        self.c, self.years = c, years
        w, h = 0.86, 0.07
        self.ax = c.fig.add_axes([0.07, y - h / 2, w, h])
        ax = self.ax
        x0, x1 = -0.6, len(years) - 0.4
        half = (x1 - x0) * (h * c.h) / (w * W) / 2           # equal aspect, so the tyre stays round
        ax.set_xlim(x0, x1)
        ax.set_ylim(-half, half)
        ax.axis("off")
        self.u = half                                       # y unit: half the axes height
        gaps = [i for i in range(len(years) - 1) if years[i + 1] - years[i] > 5]
        for i in range(len(years) - 1):
            ls = (0, (2, 3)) if i in gaps else "-"
            ax.plot([i, i + 1], [0, 0], color="#3A4458", lw=1.4, ls=ls, zorder=1)
        for i in gaps:
            ax.text(i + 0.5, 0.45 * self.u, f"{years[i + 1] - years[i]} YEARS", ha="center", va="center", color=MUTED,
                    fontsize=13, family=FONT, weight=500)
        self.dots = [ax.plot(i, 0, "o", ms=9, color="#3A4458", zorder=2)[0] for i in range(len(years))]
        self.labels = [ax.text(i, -0.72 * self.u, str(yv), ha="center", va="center", color=MUTED, fontsize=17, family=FONT,
                               weight=500) for i, yv in enumerate(years)]
        self.marker = []

    def pos(self, year: int) -> float:
        return float(self.years.index(year)) if year in self.years else 0.0

    def show(self, x: float, lit: list[int], gold: list[int] | None = None):
        for m in self.marker:
            m.remove()
        self.marker = []
        for i, yv in enumerate(self.years):
            on = yv in lit
            g = gold and yv in gold
            self.dots[i].set_color(GOLD if g else CYAN if on else "#3A4458")
            self.labels[i].set_color(TEXT if on or g else MUTED)
        if x is None:                                       # the titles chapter shows no marker
            return
        before, nt = set(self.ax.patches), len(self.ax.texts)
        tyre(self.ax, x, 0, 0.36 * self.u, "SOFT", "", label=False)
        self.marker = [pt for pt in self.ax.patches if pt not in before] + list(self.ax.texts[nt:])


def reel(p: Preview, out: Path) -> tuple[Path, Path]:
    set_event(p)
    h = HISTORY[p.title]
    chs = h["chapters"]
    years = sorted({y for ch in chs for y in _years(ch)} | {p.season})
    r = Reel(out / "reel.mp4")
    c = Card(H_REEL, story=True)
    c.header(p)
    c.footer()
    tl = Timeline(c, years)

    # intro, 2 s
    k = c.text(0.5, 0.70, "LAS VEGAS GP" if p.title == "LAS VEGAS" else gp_name(p).upper(), 18, color=CYAN, weight=600, track=True)
    t1 = c.text(0.5, 0.63, "A HISTORY", 64, weight=200, track=True)
    t2 = c.text(0.5, 0.57, "IN NUMBERS", 64, color=CYAN, weight=300, track=True)
    t3 = c.text(0.5, 0.48, f"{len(chs)} facts, {years[0]} to {years[-2]}, every one sourced", 22, color=MUTED, weight=300,
                style="italic")
    n = int(2.0 * FPS)
    for i in range(n):
        a_ = ease(i / (0.5 * FPS))
        for t in (k, t1, t2, t3):
            t.set_alpha(a_)
        tl.show(-0.6 + 0.6 * a_, [])
        r.add(c.fig)
        if i == int(1.6 * FPS):
            c.fig.savefig(out / "cover.jpg", dpi=c.fig.dpi, format="jpg", pil_kwargs={"quality": 94})
    for t in (k, t1, t2, t3):
        t.remove()

    x_prev = -0.6
    for ch in chs:
        ys = _years(ch)
        # a "world titles" chapter lights every title year named in its line, in gold
        gold = [int(y) for y in re.findall(r"\d{4}", ch["line"])] if ch["unit"] == "world titles" else None
        x_to = x_prev if gold else tl.pos(ys[-1])
        yr = c.text(0.5, 0.775, ch["year"].upper(), 30, color=GOLD, weight=400, track=True)
        hd = c.text(0.5, 0.715, ch["head"], 30, weight=400)
        big, unit = c.number(0.585, ch["number"], ch["unit"] or " ", size=150 if len(ch["number"]) <= 5 else 120)
        body = "\n".join(textwrap.wrap(ch["line"], 40))
        ln = c.fig.text(0.5, 0.535, body, ha="center", va="top", fontsize=24, color=TEXT, family=FONT, weight=300,
                        linespacing=1.4)
        src = c.text(0.5, 0.43, f"Source: {ch['source']}", 14, color=MUTED, weight=300)
        items = (yr, hd, big, unit, ln, src)
        frames = int(HOLD_S * FPS)
        for i in range(frames):
            a_ = ease(i / (FADE_S * FPS))
            out_a = 1 - ease((i - (frames - 0.2 * FPS)) / (0.2 * FPS)) if i > frames - 0.2 * FPS else 1
            for t in items:
                t.set_alpha(a_ * out_a)
            m = ease(i / (0.6 * FPS))
            tl.show(None if gold else x_prev + (x_to - x_prev) * m, [] if gold else ys, gold)
            r.add(c.fig)
        for t in items:
            t.remove()
        x_prev = x_to

    # outro, 2.5 s: this year, times, follow
    q, rr = times_text(p)
    tl.show(tl.pos(p.season), [p.season])
    o = [c.text(0.5, 0.78, str(p.season), 30, color=GOLD, weight=400, track=True),
         c.text(0.5, 0.715, "THE NEXT LINE", 52, weight=200, track=True),
         c.text(0.5, 0.665, "IS WRITTEN THIS WEEK", 30, color=CYAN, weight=300, track=True),
         c.text(0.5, 0.585, f"Quali {q}   |   Race {rr}", 28, weight=300),
         c.text(0.5, 0.55, "LOCAL TIME", 13, color=MUTED, weight=500, track=True),
         c.text(0.5, 0.47, f"Follow {S.HANDLE}", 24, weight=400)]
    c.logo(0.5, 0.405, 0.42, ha="center")
    for i in range(int(2.5 * FPS)):
        a_ = ease(i / (0.4 * FPS))
        for t in o:
            t.set_alpha(a_)
        r.add(c.fig)
    plt.close(c.fig)
    return r.close(), out / "cover.jpg"


def caption(p: Preview) -> str:
    chs = HISTORY[p.title]["chapters"]
    q, r = times_text(p)
    lines = [f"{p.title.title()} in numbers: F1 raced here in a hotel car park before it ever raced the Strip.", ""]
    for ch in chs:
        u = f" {ch['unit']}" if ch["unit"] else ""
        lines.append(f"{ch['year']}: {ch['number']}{u}. {ch['head']}. {ch['line']}.")
    srcs = sorted({s.strip() for ch in chs for s in ch["source"].split(";")})
    lines += ["", "Sources: " + "; ".join(srcs) + ".", "",
              f"{p.season}: Quali {q}, Race {r}, local time. Follow so you don't miss it.",
              "", FOOTER, "", " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1History", "#RaceWeek"])]
    return clean("\n".join(lines))
