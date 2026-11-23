"""Chase cam Reel (Michel, 22 Nov; reference: formulytics "The optimal lap").

The camera follows one car along a wide track band, heading up, with kerbs on the corners. The trail behind the
car is coloured by what the driver is doing: full throttle, braking or lifting, from the official throttle and
brake channels only (never called battery deployment). A big speed readout, the phase, the lap clock and a mini map
with the car dot sit on top. Positions are the car's own x and y, smoothed; speed and time are its own channels.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from scipy.interpolate import splev, splprep

from . import preview as P
from .render import FPS, H_REEL, Reel

PHASE = {"FULL THROTTLE": "#2EE6A6", "BRAKING": "#FF3B3B", "LIFT": "#F5C542"}


def _clock(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:06.3f}"


def _path(lap: dict, step: float = 1.0):
    x, y, d = (np.asarray(lap[k], float) for k in ("x", "y", "dist"))
    keep = np.concatenate([[True], np.diff(d) > 0.05])
    x, y, d = x[keep], y[keep], d[keep]
    tck, _ = splprep([x, y], u=d / d[-1], s=len(x) * 40.0, per=0)
    D = np.arange(0.0, d[-1], step)
    X, Y = splev(D / d[-1], tck)
    return D, np.asarray(X), np.asarray(Y)


def onboard(p, lap: dict, out: Path, title: str, sub: str, speedup: float = 3.5, window: float = 170.0,
            src: str = "Data: OpenF1 car data. Phases from throttle and brake") -> Path:
    P.set_event(p)
    D, X, Y = _path(lap)
    d, t = np.asarray(lap["dist"], float), np.asarray(lap["t"], float)
    T = np.interp(D, d, t)
    V = np.interp(D, d, np.asarray(lap["speed"], float))
    thr = np.interp(D, d, np.asarray(lap["throttle"], float))
    brk = np.interp(D, d, np.asarray(lap["brake"], float))
    phase = np.where(brk > 0.5, "BRAKING", np.where(thr >= 95, "FULL THROTTLE", "LIFT"))
    hd = np.unwrap(np.arctan2(np.gradient(Y), np.gradient(X)))
    hd = np.convolve(np.pad(hd, 40, mode="edge"), np.ones(81) / 81, mode="valid")       # calm camera, 80 m
    k_ = np.abs(np.gradient(np.convolve(np.pad(np.unwrap(np.arctan2(np.gradient(Y), np.gradient(X))), 10, mode="edge"),
                                        np.ones(21) / 21, mode="valid")))                 # curvature per metre
    kerb = k_ > 0.012                                                                     # radius under about 80 m
    nx, ny = -np.sin(np.arctan2(np.gradient(Y), np.gradient(X))), np.cos(np.arctan2(np.gradient(Y), np.gradient(X)))
    half = 16.0                     # drawn about twice the real width so the track reads on a phone (stylised)
    turn = np.sign(np.gradient(np.unwrap(np.arctan2(np.gradient(Y), np.gradient(X)))))
    c = P.Card(H_REEL, story=True)
    ax = c.fig.add_axes([0, 0.20, 1, 0.62], zorder=1)
    ax.set_facecolor("#05070A")
    ax.set_aspect("equal")
    ax.set_xticks([]), ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    hw, hh = window / 2, window / 2 * 0.62 * H_REEL / 1080
    ax.set_xlim(-hw, hw), ax.set_ylim(-hh * 0.85, hh * 1.15)                            # car a little low, sees ahead
    px_per_m = 1080 / window
    band, = ax.plot([], [], color="#2A2F3A", lw=2 * half * px_per_m * 72 / P.DPI, solid_capstyle="butt", zorder=1)
    eL, = ax.plot([], [], color="#E8EDF5", lw=1.6, zorder=2)
    eR, = ax.plot([], [], color="#E8EDF5", lw=1.6, zorder=2)
    kerbs = LineCollection([], linewidths=12, zorder=3)
    ax.add_collection(kerbs)
    ghost, = ax.plot([], [], color="#5D6573", lw=1.2, zorder=4)
    trail = LineCollection([], linewidths=9, capstyle="round", zorder=5)
    ax.add_collection(trail)
    car, = ax.plot([0], [0], "o", ms=26, color="#E8EDF5", mec="#05070A", mew=2, zorder=6)
    c.text(0.5, 0.875, title.upper(), 34, weight=800, zorder=10)
    c.text(0.5, 0.848, sub.upper(), 15, color=P.MUTED, weight=600, track=True, zorder=10)
    c.fig.add_artist(plt.Rectangle((0.30, 0.205), 0.40, 0.165, transform=c.fig.transFigure, fc="#05070A", ec="#232D3F",
                                   lw=1.2, alpha=0.82, zorder=9))                    # readout panel over the trail
    ph = c.text(0.5, 0.345, "", 20, weight=800, track=True, zorder=10)
    sp_ = c.text(0.5, 0.295, "", 84, weight=800, zorder=10)
    c.text(0.5, 0.252, "KM/H", 15, color=P.MUTED, weight=600, track=True, zorder=10)
    ck = c.text(0.5, 0.222, "", 19, color=P.TEXT, weight=500, zorder=10)
    mm = c.fig.add_axes([0.74, 0.70, 0.20, 0.10], zorder=11)
    mm.set_aspect("equal"), mm.axis("off")
    mm.plot(X, Y, color="#E8EDF5", lw=1.4)
    md, = mm.plot([], [], "o", ms=6, color=PHASE["FULL THROTTLE"])
    c.text(0.5, 0.175, src, 12, color=P.MUTED, weight=300, zorder=10)
    c.footer()
    kidx = np.flatnonzero(kerb)

    def view(i):
        a = np.pi / 2 - hd[i]
        ca, sa = np.cos(a), np.sin(a)
        lo, hi = max(0, i - int(window * 1.2)), min(len(D), i + int(window * 2.0))
        sl = slice(lo, hi)
        def rot(xx, yy):
            dx, dy = xx - X[i], yy - Y[i]
            return dx * ca - dy * sa, dx * sa + dy * ca
        return sl, rot

    r = Reel(out)
    lap_s = float(T[-1])
    n = int(lap_s / speedup * FPS)
    for f in range(n + 1):
        tt = lap_s * f / n
        i = int(min(np.searchsorted(T, tt), len(D) - 1))
        sl, rot = view(i)
        bx, by = rot(X[sl], Y[sl])
        band.set_data(bx, by)
        eL.set_data(*rot(X[sl] + nx[sl] * half, Y[sl] + ny[sl] * half))
        eR.set_data(*rot(X[sl] - nx[sl] * half, Y[sl] - ny[sl] * half))
        ks = kidx[(kidx >= sl.start) & (kidx < sl.stop)]
        segs, cols = [], []
        for j in ks[::4]:
            s_ = -turn[j]                                                     # kerb on the outside of the turn
            x0, y0 = rot(X[j] + nx[j] * half * s_, Y[j] + ny[j] * half * s_)
            x1, y1 = rot(X[min(j + 4, len(D) - 1)] + nx[j] * half * s_, Y[min(j + 4, len(D) - 1)] + ny[j] * half * s_)
            segs.append([(x0, y0), (x1, y1)])
            cols.append("#FF3B3B" if (j // 4) % 2 else "#F2F2F2")
        kerbs.set_segments(segs), kerbs.set_color(cols)
        ghost.set_data(bx, by)
        a0 = max(0, i - int(window * 1.2))
        tx, ty = rot(X[a0:i + 1], Y[a0:i + 1])
        pts = np.column_stack([tx, ty])
        trail.set_segments(np.stack([pts[:-1], pts[1:]], axis=1) if len(pts) > 1 else [])
        trail.set_color([PHASE[q] for q in phase[a0:i]])
        car.set_color(PHASE[phase[i]])
        ph.set_text(phase[i]), ph.set_color(PHASE[phase[i]])
        sp_.set_text(f"{V[i]:.0f}")
        ck.set_text(f"LAP TIME  {_clock(tt)}")
        md.set_data([X[i]], [Y[i]]), md.set_color(PHASE[phase[i]])
        r.add(c.fig)
    ck.set_text(f"LAP TIME  {_clock(lap.get('official', lap_s) or lap_s)}")
    r.add(c.fig, int(2.5 * FPS))
    plt.close(c.fig)
    return r.close()


TYRE = {"SOFT": "#FF3333", "MEDIUM": "#FFF200", "HARD": "#FFFFFF", "INTERMEDIATE": "#39B54A", "WET": "#00AEEF"}


def lap_chart(p, D: dict, out: Path, sub: str, window: int = 12, per_lap: float = 0.42,
              src: str = "Positions at the end of each lap: official timing via OpenF1") -> Path:
    """Race position by lap (reference flabo.jp): every driver's line in team colour, team mate dashed, a dot in
    the new tyre's colour at each stop, safety car laps shaded. A 12 lap window scrolls with the race and the
    driver codes on the right re-sort live."""
    P.set_event(p)
    rows, n = D["rows"], D["n"]
    N = len(rows)
    c = P.Card(H_REEL, story=True)
    c.header(p)
    c.text(0.5, 0.815, "RACE POSITION BY LAP", 40, weight=800)
    c.text(0.5, 0.790, sub.upper(), 15, color=P.MUTED, weight=600, track=True)
    lap_t = c.text(0.5, 0.762, "", 26, color="#FF5A4F", weight=800, track=True)
    ax = c.fig.add_axes([0.10, 0.215, 0.70, 0.525])
    ax.set_ylim(N + 0.7, 0.3), ax.axis("off")
    for k in range(1, N + 1):
        ax.text(-0.02, k, f"{k}", transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=13,
                color=P.MUTED, family=P.FONT)
    neutral = D.get("neutral", [])
    bands = []
    if neutral:
        runs, s0 = [], neutral[0]
        for a, b in zip(neutral, neutral[1:] + [None]):
            if b != a + 1:
                runs.append((s0, a))
                s0 = b
        for a, b in runs:
            bands.append(ax.axvspan(a - 1, b, color="#5A4A12", alpha=0.45, lw=0, zorder=0))
            ax.text((a - 1 + b) / 2, 0.55, "SC", color="#F5C542", fontsize=14, family=P.FONT, weight=800, ha="center", zorder=1,
                    clip_on=True)
    lines, tags, dots = {}, {}, []
    for r in rows:
        col = r["color"] or P.TEXT
        lines[r["code"]] = ax.plot([], [], color=col, lw=3.2, ls=(0, (5, 3)) if r["dashed"] else "-", zorder=3,
                                   solid_capstyle="round")[0]
        tags[r["code"]] = c.text(0.86, 0.5, r["code"], 15, color=col, weight=800, ha="left")
        for L, comp in r["stops"]:
            if 0 <= L <= n and r["pos"][L] is not None:
                d_ = ax.plot([L], [r["pos"][L]], "o", ms=9, color=TYRE.get(comp, "#888888"), mec="#05070A", mew=1.5,
                             zorder=5, alpha=0)[0]
                dots.append((L, d_))
    head = {r["code"]: ax.plot([], [], "o", ms=8, color=r["color"] or P.TEXT, zorder=4)[0] for r in rows}
    ticks = []
    for L in range(5, n + 1, 5):
        ticks.append(ax.text(L, N + 0.6, f"L{L}", ha="center", va="top", fontsize=13, color=P.MUTED, family=P.FONT, clip_on=True))
    c.text(0.5, 0.175, src, 12, color=P.MUTED, weight=300)
    c.footer()
    y_ax = lambda q: 0.215 + 0.525 * (1 - (q - 0.3) / (N + 0.4))
    r_ = Reel(out)
    frames = int(n * per_lap * FPS)
    for f in range(frames + int(2.5 * FPS)):
        xl = min(n, n * f / frames)
        lo = max(0.0, xl - window + 1)
        ax.set_xlim(lo - 0.3, lo + window + 0.3)
        live = []
        for r in rows:
            ps = r["pos"]
            xs = [L for L in range(0, int(np.floor(xl)) + 1) if ps[L] is not None]
            ys = [ps[L] for L in xs]
            if not xs:
                continue
            nx_ = int(np.floor(xl)) + 1
            if nx_ <= n and ps[nx_] is not None and xl > xs[-1]:                      # draw into the next lap smoothly
                fr = xl - xs[-1]
                xs.append(xl), ys.append(ys[-1] + (ps[nx_] - ys[-1]) * fr)
            lines[r["code"]].set_data(xs, ys)
            head[r["code"]].set_data([xs[-1]], [ys[-1]])
            live.append((ys[-1] if xs[-1] >= xl - 1e-6 or xs[-1] == n else 99 + ys[-1], r["code"]))
        for k, (_, code) in enumerate(sorted(live)):
            tags[code].set_y(y_ax(k + 1))
        for L, d_ in dots:
            d_.set_alpha(1.0 if L <= xl else 0.0)
        lap_t.set_text(f"LAP {int(np.floor(xl))} / {n}" if xl < n else f"FLAG  ·  LAP {n} / {n}")
        r_.add(c.fig)
    plt.close(c.fig)
    return r_.close()
