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
    s = max(0.0, s)                                        # a replay window can open a few seconds before lights out
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
    c.text(0.5, 0.815, "Race position by lap", 44, weight=300)                         # brand: Inter Light title
    c.text(0.5, 0.784, sub.upper(), 15, color=P.MUTED, weight=600, track=True)
    lap_t = c.text(0.5, 0.757, "", 22, color=P.CYAN, weight=600, track=True)
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
            bands.append(ax.axvspan(a - 1, b, color=P.GOLD, alpha=0.13, lw=0, zorder=0))      # champagne, brand
            ax.text((a - 1 + b) / 2, 0.55, "SC", color=P.GOLD, fontsize=14, family=P.FONT, weight=600, ha="center", zorder=1,
                    clip_on=True)
    lines, tags, dots = {}, {}, []
    for r in rows:
        col = r["color"] or P.TEXT
        lines[r["code"]] = ax.plot([], [], color=col, lw=3.2, ls=(0, (5, 3)) if r["dashed"] else "-", zorder=3,
                                   solid_capstyle="round")[0]
        tags[r["code"]] = c.text(0.86, 0.5, r["code"], 15, color=col, weight=600, ha="left", track=True)
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
        lap_t.set_text(f"LAP {int(np.floor(xl))} OF {n}" if xl < n else f"FLAG, LAP {n} OF {n}")
        r_.add(c.fig)
    plt.close(c.fig)
    return r_.close()


def _ref_path(ref: dict):
    d, x, y = (np.asarray(ref[k], float) for k in ("dist", "x", "y"))
    keep = np.concatenate([[True], np.diff(d) > 0.05])
    return d[keep], x[keep], y[keep]


def _map(c, rect, x, y, lw=10):
    ax = c.fig.add_axes(rect)
    ax.set_aspect("equal"), ax.axis("off")
    pad = 0.05 * max(np.ptp(x), np.ptp(y))
    ax.set_xlim(x.min() - pad, x.max() + pad), ax.set_ylim(y.min() - pad, y.max() + pad)
    ax.plot(x, y, color="#2A3242", lw=lw, solid_capstyle="round", zorder=1)
    ax.plot(x, y, color="#3A4458", lw=1.2, zorder=2)
    return ax


def ghost_years(p, laps: list[dict], out: Path, hook: list[str], sub: str, speedup: float = 2.6,
                src: str = "Lap times: official timing. Positions: OpenF1 car data") -> Path:
    """Fastest laps from different years on one track (Michel, 23 Nov: animated history with cars and timers).
    Every car runs on its own clock: its position is its own distance along the lap mapped onto one reference
    line, so years with slightly different coordinates still share one track. A timer per car runs and stops on
    the official lap time; the tower re-sorts live by who is ahead on the road."""
    P.set_event(p)
    ref = max(laps, key=lambda L: L["year"])
    D, X, Y = _ref_path(ref)
    Lr = D[-1]
    c = P.Card(H_REEL, story=True)
    c.header(p)
    c.text(0.5, 0.835, hook[0], 46, weight=300)
    if len(hook) > 1:
        c.text(0.5, 0.800, hook[1], 46, color=P.GOLD, weight=300)
    c.text(0.5, 0.772, sub.upper(), 14, color=P.CYAN, weight=600, track=True)
    ax = _map(c, [0.05, 0.40, 0.90, 0.35], X, Y)
    dots, tags, rows = [], [], []
    for k, L in enumerate(laps):
        col = L["color"]
        dots.append(ax.plot([], [], "o", ms=20, color=col, mec="#05070A", mew=2.5, zorder=5 + k)[0])
        tags.append(ax.text(0, 0, f"{L['year']}", fontsize=15, color=col, family=P.FONT, weight=600, zorder=9,
                            ha="left", va="center"))
    c.text(0.08, 0.360, "LAP TIMER", 12, color=P.MUTED, weight=600, ha="left", track=True)
    big = c.text(0.92, 0.360, "", 22, color=P.TEXT, weight=200, ha="right")
    c.text(0.5, 0.360, f"{speedup:g}X SPEED", 11, color=P.MUTED, weight=600, track=True)
    for k, L in enumerate(laps):
        y = 0.320 - k * 0.042
        rows.append((c.text(0.08, y, f"{L['year']}", 26, color=L["color"], weight=300, ha="left"),
                     c.text(0.25, y, f"{L['code']}", 24, color=L["color"], weight=600, ha="left", track=True),
                     c.text(0.60, y, "", 30, weight=200, ha="right"),
                     c.text(0.92, y, "", 20, color=P.MUTED, weight=300, ha="right")))
    c.text(0.5, 0.175, src, 12, color=P.MUTED, weight=300)
    c.footer()
    tl = [np.asarray(L["t"], float) for L in laps]
    dl = [np.asarray(L["dist"], float) for L in laps]
    offi = [float(L.get("official") or L["lap_s"]) for L in laps]
    best = min(offi)
    T = max(offi)
    r_ = Reel(out)
    n = int(T / speedup * FPS)
    for f in range(n + int(3.0 * FPS)):
        tt = min(T, T * f / n)
        prog, frac = [], []
        for k, L in enumerate(laps):
            s = float(np.interp(min(tt, offi[k]), tl[k], dl[k])) / dl[k][-1] * Lr if tt < offi[k] else Lr
            xx, yy = np.interp(s, D, X), np.interp(s, D, Y)
            dots[k].set_data([xx], [yy])
            # stagger the year tags so cars running close together stay readable
            tags[k].set_position((xx + Lr * 0.012, yy + Lr * (0.012 - 0.012 * k)))
            prog.append((-(s if tt < offi[k] else Lr + (T - offi[k])), k))
            frac.append(s / Lr if tt < offi[k] else 1.0)
        lead = max(range(len(laps)), key=lambda k: (frac[k], -offi[k]))
        big.set_text(_clock(min(tt, T)))
        for k, L in enumerate(laps):
            yr, cd, clk, gap = rows[k]
            done = tt >= offi[k]
            if done:
                clk.set_text(_clock(offi[k])), clk.set_color(L["color"])
                gap.set_text("FASTEST" if offi[k] == best else f"+{offi[k] - best:.3f}")
            else:
                clk.set_text(""), gap.set_text("")
                if k != lead and frac[k] > 0.002:
                    # live gap on the road: time since the leading lap passed this car's point of the lap
                    tl_at = float(np.interp(frac[k], dl[lead] / dl[lead][-1], tl[lead]))
                    clk.set_text(f"+{max(0.0, tt - tl_at):.3f}"), clk.set_color(P.MUTED)
                elif k == lead:
                    clk.set_text("LEADS"), clk.set_color(L["color"])
        for j, (_, k) in enumerate(sorted(prog)):              # tower re-sorts by who is ahead on the road
            y = 0.320 - j * 0.042
            for a in rows[k]:
                a.set_y(y)
        r_.add(c.fig)
    plt.close(c.fig)
    return r_.close()


def race_replay(p, ref: dict, D: dict, out: Path, hook: list[str], sub: str, speedup: float = 3.0, label: list[str] | None = None,
                src: str = "Positions: OpenF1 location and timing data") -> Path:
    """Race replay (Michel, 23 Nov): every car as a dot in team colour on the track map, a race clock, the lap
    counter, a live P1 to P10 tower from official timing positions, PIT tags from pit timing and a SAFETY CAR
    banner from race control. Shown faster than real time; the speed is on screen."""
    P.set_event(p)
    _, X, Y = _ref_path(ref)
    t = np.asarray(D["t"], float)
    cars = D["cars"]
    c = P.Card(H_REEL, story=True)
    c.header(p)
    c.text(0.5, 0.835, hook[0], 46, weight=300)
    if len(hook) > 1:
        c.text(0.5, 0.800, hook[1], 46, color=P.GOLD, weight=300)
    c.text(0.5, 0.772, sub.upper(), 14, color=P.CYAN, weight=600, track=True)
    ax = c.fig.add_axes([0.04, 0.395, 0.92, 0.36])
    ax.set_aspect("equal"), ax.axis("off")
    allx = np.concatenate([np.asarray(v["x"], float) for v in cars.values()] + [X])
    ally = np.concatenate([np.asarray(v["y"], float) for v in cars.values()] + [Y])
    pad = 0.04 * max(np.ptp(X), np.ptp(Y))
    ax.set_xlim(X.min() - pad, X.max() + pad), ax.set_ylim(Y.min() - pad, Y.max() + pad)
    ax.plot(X, Y, color="#2A3242", lw=12, solid_capstyle="round", zorder=1)
    label = set(label or [])
    dots, tags = {}, {}
    for k, (code, v) in enumerate(cars.items()):
        dots[code] = ax.plot([], [], "o", ms=13 if code in label else 10, color=v["color"], mec="#05070A", mew=1.5, zorder=5)[0]
        if code in label:
            tags[code] = ax.text(0, 0, code, fontsize=13, color=v["color"], family=P.FONT, weight=600, zorder=9)
    lap_t = c.text(0.08, 0.372, "", 22, color=P.TEXT, weight=300, ha="left")
    clk = c.text(0.92, 0.372, "", 22, color=P.TEXT, weight=200, ha="right")
    c.text(0.5, 0.372, f"{speedup:g}X SPEED", 11, color=P.MUTED, weight=600, track=True)
    sc = c.text(0.5, 0.745, "", 16, color=P.GOLD, weight=600, track=True)
    tower = []
    for j in range(10):
        col, row = j // 5, j % 5
        x0, y0 = 0.08 + col * 0.44, 0.335 - row * 0.030
        tower.append((c.text(x0, y0, f"P{j + 1}", 15, color=P.MUTED, weight=600, ha="left"),
                      c.text(x0 + 0.07, y0, "", 18, weight=600, ha="left", track=True),
                      c.text(x0 + 0.38, y0, "", 13, color=P.GOLD, weight=600, ha="right", track=True)))
    c.text(0.5, 0.175, src, 12, color=P.MUTED, weight=300)
    c.footer()
    order = sorted(D["order"], key=lambda e: e["t"])
    pits = D.get("pits", [])
    scw = D.get("sc", [])
    laps_at = sorted(D.get("laps", []), key=lambda e: e["t"])
    xs = {k: np.asarray(v["x"], float) for k, v in cars.items()}
    ys = {k: np.asarray(v["y"], float) for k, v in cars.items()}
    r_ = Reel(out)
    T = t[-1]
    n = int(T / speedup * FPS)
    pos = {}
    oi = 0
    for f in range(n + int(2.5 * FPS)):
        tt = min(T, T * f / n)
        i = int(min(np.searchsorted(t, tt), len(t) - 1))
        for code in cars:
            if np.isnan(xs[code][i]):
                dots[code].set_data([], [])
                continue
            dots[code].set_data([xs[code][i]], [ys[code][i]])
            if code in tags:
                tags[code].set_position((xs[code][i] + pad * 0.25, ys[code][i] + pad * 0.25))
        while oi < len(order) and order[oi]["t"] <= tt:
            pos[order[oi]["code"]] = order[oi]["pos"]
            oi += 1
        ranked = sorted(pos, key=lambda c_: pos[c_])[:10]
        inpit = {e["code"] for e in pits if e["t"] <= tt <= e["t"] + e.get("dur", 25)}
        for j, (pl, cd, tg) in enumerate(tower):
            if j < len(ranked):
                code = ranked[j]
                cd.set_text(code), cd.set_color(cars.get(code, {}).get("color", P.TEXT))
                tg.set_text("PIT" if code in inpit else "")
        lap_now = max([e["lap"] for e in laps_at if e["t"] <= tt] or [D.get("lap_from", 1)])
        lap_t.set_text(f"LAP {lap_now} / {D['n_laps']}")
        clk.set_text(_clock(D.get("clock0", 0.0) + tt))
        sc.set_text("SAFETY CAR" if any(a <= tt <= b for a, b in scw) else "")
        r_.add(c.fig)
    plt.close(c.fig)
    return r_.close()
