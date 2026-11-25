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


# ---------------------------------------------------------------------------------------------------------------
# Lap DNA (Michel, 24 Nov): throttle, brake and gear at every part of one lap, shown in a new way.
# Top: the track is painted as the car drives it, colour = what the driver does (full throttle, part throttle,
# coasting, braking), line width = speed, and the gear at each slow corner stamped on the map.
# Bottom: the lap as a wheel. 360 degrees = one lap. The outer ring fills clockwise with the same input colours,
# the inner ring is a "gear skyline" (taller = higher gear). Centre: gear, speed, lap clock.
# End: the lap's share of full throttle, braking and coasting, from the official channels only.
# ---------------------------------------------------------------------------------------------------------------
DNA = {"FULL THROTTLE": "#10B981", "PART THROTTLE": "#F5B942", "COAST": "#566074", "BRAKING": "#EF4444"}


def _phase(th: float, br: float) -> str:
    if br > 0:
        return "BRAKING"
    if th >= 95:
        return "FULL THROTTLE"
    return "PART THROTTLE" if th >= 10 else "COAST"


def lap_dna(p, lap: dict, out: Path, hook: list[str], sub: str, official: str | None = None, target_s: float = 22.0,
            src: str = "Telemetry: OpenF1 car data (throttle, brake on or off, gear). Lap time: official timing") -> Path:
    from matplotlib.patches import Wedge
    P.set_event(p)
    L = {k: np.asarray(v, float) if isinstance(v, list) else v for k, v in lap.items()}
    T, D = L["t"], L["dist"]
    Lm, lap_s = float(D[-1]), float(L["lap_s"])
    speedup = max(2, round(lap_s / target_s))
    ph = [_phase(float(a), float(b)) for a, b in zip(L["throttle"], L["brake"])]
    gear = np.clip(np.round(L["gear"]), 0, 8)

    c = P.Card(H_REEL, story=True)
    c.header(p)
    for k, s in enumerate(hook):
        c.text(0.5, 0.83 - k * 0.042, s, 44, weight=300)
    c.text(0.5, 0.83 - len(hook) * 0.042 - 0.005, f"{sub}, {speedup}x speed".upper(), 15, color=P.CYAN, weight=600, track=True)

    # legend row
    xs = [0.16, 0.39, 0.61, 0.82]
    for x0, (lab, col) in zip(xs, DNA.items()):
        c.text(x0, 0.712, lab, 12, color=col, weight=700, track=True)

    # painted track
    ax = c.fig.add_axes([0.04, 0.47, 0.92, 0.235])
    ax.set_aspect("equal"), ax.axis("off")
    pad = 0.07 * max(np.ptp(L["x"]), np.ptp(L["y"]))
    ax.set_xlim(L["x"].min() - pad, L["x"].max() + pad), ax.set_ylim(L["y"].min() - pad, L["y"].max() + pad)
    ax.plot(L["x"], L["y"], color=P.BASE, lw=5, solid_capstyle="round", zorder=1)
    pts = np.column_stack([L["x"], L["y"]]).reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    vmin, vmax = float(np.nanmin(L["speed"])), float(np.nanmax(L["speed"]))
    widths = 2.5 + 7.5 * (L["speed"][:-1] - vmin) / max(1.0, vmax - vmin)
    seg_cols = [DNA[ph[i]] for i in range(len(segs))]
    lc = LineCollection([], linewidths=[], colors=[], capstyle="round", zorder=3)
    ax.add_collection(lc)
    dot, = ax.plot([], [], "o", ms=15, color=P.TEXT, mec="#0B0E14", mew=3, zorder=6)
    # gear at each slow corner: local speed minima under 200 km/h, at least 150 m apart
    sp = L["speed"]
    mins = []
    for i in range(3, len(sp) - 3):
        if sp[i] < 200 and sp[i] == sp[i - 3:i + 4].min() and (not mins or D[i] - D[mins[-1]] > 150):
            mins.append(i)
    tags = []
    for i in mins:
        tags.append((i, ax.text(L["x"][i], L["y"][i], f"{gear[i]:.0f}", fontsize=15, color=P.TEXT, family=P.FONT,
                                weight=700, ha="center", va="center", zorder=7, visible=False,
                                bbox=dict(boxstyle="circle,pad=0.25", fc="#141923", ec=P.GOLD, lw=1.5))))

    # the lap wheel
    wx = c.fig.add_axes([0.28, 0.212, 0.44, 0.44 * 1080 / 1920])
    wx.set_aspect("equal"), wx.axis("off"), wx.set_xlim(-1.08, 1.08), wx.set_ylim(-1.08, 1.08)
    wx.add_patch(Wedge((0, 0), 1.0, 0, 360, width=0.16, fc="#141923", ec="none"))
    wx.add_patch(Wedge((0, 0), 0.80, 0, 360, width=0.22, fc="#10141C", ec="none"))
    nb = 360
    edges = np.linspace(0, Lm, nb + 1)
    bin_i = np.clip(np.searchsorted(D, (edges[:-1] + edges[1:]) / 2), 0, len(D) - 1)
    outer, inner = [], []
    for b in range(nb):
        a1 = 90 - b * 360 / nb                                     # clockwise from 12 o'clock
        a0 = a1 - 360 / nb - 0.15
        i = bin_i[b]
        w = Wedge((0, 0), 1.0, a0, a1, width=0.16, fc=DNA[ph[i]], ec="none", visible=False)
        g = max(gear[i], 1)
        wi = Wedge((0, 0), 0.58 + 0.22 * g / 8, a0, a1, width=0.22 * g / 8, fc="#C9D1DC", alpha=0.25 + 0.6 * g / 8,
                   ec="none", visible=False)
        wx.add_patch(w), wx.add_patch(wi)
        outer.append(w), inner.append(wi)
    hand, = wx.plot([0, 0], [0.56, 1.06], color=P.TEXT, lw=2.5, zorder=5)    # a rim marker, clear of the centre text
    wx.text(0, 1.06, "START", fontsize=10, color=P.MUTED, family=P.FONT, weight=700, ha="center", va="bottom")
    g_t = wx.text(0, 0.16, "", fontsize=84, color=P.TEXT, family=P.FONT, weight=200, ha="center", va="center")
    g_lab = wx.text(0, -0.10, "GEAR", fontsize=11, color=P.MUTED, family=P.FONT, weight=700, ha="center")
    s_t = wx.text(0, -0.27, "", fontsize=24, color=P.TEXT, family=P.FONT, weight=300, ha="center", va="center")
    clk = wx.text(0, -0.43, "", fontsize=17, color=P.MUTED, family=P.FONT, weight=300, ha="center", va="center")
    c.text(0.5, 0.197, "OUTER RING: WHAT THE DRIVER DOES   INNER RING: GEAR", 11, color=P.MUTED, weight=600, track=True)
    c.text(0.5, 0.175, src, 13, color=P.MUTED, weight=300)
    c.footer()

    r = Reel(out)
    n = int(lap_s / speedup * FPS)
    for f in range(n + 1):
        t = min(lap_s, f / FPS * speedup)
        j = min(len(T) - 1, int(np.searchsorted(T, t)))
        lc.set_segments(segs[:j]), lc.set_color(seg_cols[:j]), lc.set_linewidth(widths[:j])
        dot.set_data([L["x"][j]], [L["y"][j]])
        for i, tg in tags:
            tg.set_visible(i <= j)
        frac = D[j] / Lm
        nb_on = int(frac * nb)
        for b in range(nb_on):
            outer[b].set_visible(True), inner[b].set_visible(True)
        ang = np.deg2rad(90 - frac * 360)
        hand.set_data([0.56 * np.cos(ang), 1.06 * np.cos(ang)], [0.56 * np.sin(ang), 1.06 * np.sin(ang)])
        g_t.set_text(f"{gear[j]:.0f}"), g_t.set_color(DNA[ph[j]])
        s_t.set_text(f"{L['speed'][j]:.0f} km/h")
        clk.set_text(_clock(t))
        r.add(c.fig)
    for w in outer + inner:
        w.set_visible(True)
    hand.set_visible(False), g_lab.set_visible(False)
    dt = np.diff(T, append=T[-1])                                      # time weighted, not sample counted
    share = {k: 100.0 * float(sum(d for d, q in zip(dt, ph) if q == k)) / float(dt.sum()) for k in DNA}
    clk.set_text(official or _clock(lap_s)), clk.set_color(P.GOLD), clk.set_fontsize(22)
    g_t.set_text(f"{share['FULL THROTTLE']:.0f}%"), g_t.set_color(DNA["FULL THROTTLE"]), g_t.set_fontsize(70)
    s_t.set_text("FLAT OUT"), s_t.set_fontsize(16)
    r.add(c.fig, int(1.6 * FPS))
    g_t.set_text(f"{share['BRAKING']:.0f}%"), g_t.set_color(DNA["BRAKING"])
    s_t.set_text("ON THE BRAKES")
    r.add(c.fig, int(2.4 * FPS))
    plt.close(c.fig)
    return r.close()


def _t_of_frac(lap: dict, f: np.ndarray) -> np.ndarray:
    d, t = np.asarray(lap["dist"], float), np.asarray(lap["t"], float)
    keep = np.concatenate([[True], np.diff(d) > 0])
    return np.interp(f * d[keep][-1], d[keep], t[keep])


def lap_dna_duel(p, a: dict, b: dict, out: Path, hook: list[str], sub: str, n_sec: int = 25, target_s: float = 24.0,
                 src: str = "Telemetry: OpenF1 car data. Lap times: official timing. Gap by distance along the lap") -> Path:
    """DNA duel (Michel, 24 Nov, idea 5): two laps as two Lap DNA wheels, run on one clock, so the slower wheel
    visibly trails. The map fills mini sector by mini sector in the colour of whoever was quicker there. Ends on the
    single mini sector with the biggest swing, ringed on the map."""
    from matplotlib.patches import Circle, Wedge
    P.set_event(p)
    A = {k: np.asarray(v, float) if isinstance(v, list) else v for k, v in a.items()}
    B = {k: np.asarray(v, float) if isinstance(v, list) else v for k, v in b.items()}
    ca = a.get("color") or P.TEXT
    cb = b.get("color") or P.TEXT
    if cb.lower() == ca.lower():
        cb = "#E6EAF0"                                             # same team: second car in white
    offa, offb = float(a["official_s"]), float(b["official_s"])
    T = max(offa, offb)
    speedup = max(2, round(T / target_s))

    # gap along the lap, normalised by each lap's own length
    F = np.linspace(0, 1, 2001)
    ta, tb = _t_of_frac(A, F), _t_of_frac(B, F)
    ta *= offa / ta[-1]
    tb *= offb / tb[-1]
    edges = np.linspace(0, 1, n_sec + 1)
    ia = np.searchsorted(F, edges).clip(0, len(F) - 1)
    gain = np.diff((tb - ta)[ia])                                 # > 0: A gained in this mini sector
    best = int(np.argmax(np.abs(gain)))

    c = P.Card(H_REEL, story=True)
    c.header(p)
    for k, s in enumerate(hook):
        c.text(0.5, 0.83 - k * 0.042, s, 44, weight=300)
    c.text(0.5, 0.83 - len(hook) * 0.042 - 0.005, f"{sub}, {speedup}x speed".upper(), 15, color=P.CYAN, weight=600, track=True)
    c.text(0.27, 0.712, f"{a['code']}  {a['official']}", 20, color=ca, weight=600)
    c.text(0.73, 0.712, f"{b['code']}  {b['official']}", 20, color=cb, weight=600)

    # map: each mini sector painted in the colour of whoever was quicker there, once both cars are through it
    ax = c.fig.add_axes([0.04, 0.47, 0.92, 0.23])
    ax.set_aspect("equal"), ax.axis("off")
    X, Y, Dm = A["x"], A["y"], A["dist"]
    pad = 0.07 * max(np.ptp(X), np.ptp(Y))
    ax.set_xlim(X.min() - pad, X.max() + pad), ax.set_ylim(Y.min() - pad, Y.max() + pad)
    ax.plot(X, Y, color=P.BASE, lw=7, solid_capstyle="round", zorder=1)
    fr = Dm / Dm[-1]
    sec_lines = []
    for k in range(n_sec):
        m = (fr >= edges[k]) & (fr <= edges[k + 1] + 1e-3)
        ln, = ax.plot(X[m], Y[m], color=ca if gain[k] > 0 else cb, lw=8, solid_capstyle="butt", zorder=2, visible=False)
        sec_lines.append(ln)
    da, = ax.plot([], [], "o", ms=14, color=ca, mec="#0B0E14", mew=2.5, zorder=6)
    db, = ax.plot([], [], "o", ms=14, color=cb, mec="#0B0E14", mew=2.5, zorder=5)
    mid = (fr >= edges[best]) & (fr <= edges[best + 1])
    bx, by = float(np.mean(X[mid])), float(np.mean(Y[mid]))
    ring = Circle((bx, by), 0.06 * max(np.ptp(X), np.ptp(Y)), fill=False, ec=P.GOLD, lw=3, zorder=8, visible=False)
    ax.add_patch(ring)

    gap_t = c.text(0.5, 0.452, "", 22, color=P.TEXT, weight=300)

    def wheel(rect, L, col):
        wx = c.fig.add_axes(rect)
        wx.set_aspect("equal"), wx.axis("off"), wx.set_xlim(-1.1, 1.1), wx.set_ylim(-1.1, 1.1)
        wx.add_patch(Wedge((0, 0), 1.0, 0, 360, width=0.16, fc="#141923", ec="none"))
        ph = [_phase(float(u), float(v)) for u, v in zip(L["throttle"], L["brake"])]
        g = np.clip(np.round(L["gear"]), 1, 8)
        D = L["dist"]
        nb = 240
        bi = np.clip(np.searchsorted(D, (np.arange(nb) + 0.5) / nb * D[-1]), 0, len(D) - 1)
        outer, inner = [], []
        for k in range(nb):
            a1 = 90 - k * 360 / nb
            a0 = a1 - 360 / nb - 0.2
            w = Wedge((0, 0), 1.0, a0, a1, width=0.16, fc=DNA[ph[bi[k]]], ec="none", visible=False)
            gg = g[bi[k]]
            wi = Wedge((0, 0), 0.58 + 0.22 * gg / 8, a0, a1, width=0.22 * gg / 8, fc="#C9D1DC", alpha=0.25 + 0.6 * gg / 8,
                       ec="none", visible=False)
            wx.add_patch(w), wx.add_patch(wi)
            outer.append(w), inner.append(wi)
        hand, = wx.plot([0, 0], [0.56, 1.07], color=col, lw=3, zorder=5)
        gt = wx.text(0, 0.1, "", fontsize=60, color=P.TEXT, family=P.FONT, weight=200, ha="center", va="center")
        st = wx.text(0, -0.32, "", fontsize=16, color=P.TEXT, family=P.FONT, weight=300, ha="center", va="center")
        wx.text(0, -1.1, L["code"], fontsize=15, color=col, family=P.FONT, weight=700, ha="center", va="top")
        return dict(outer=outer, inner=inner, hand=hand, gt=gt, st=st, ph=ph, g=g, nb=nb)

    W = 0.40
    wa = wheel([0.06, 0.225, W, W * 1080 / 1920], A, ca)
    wb = wheel([0.54, 0.225, W, W * 1080 / 1920], B, cb)
    c.text(0.5, 0.197, "TRACK: QUICKER CAR IN EACH MINI SECTOR   WHEELS: INPUTS AND GEAR", 11, color=P.MUTED, weight=600, track=True)
    c.text(0.5, 0.175, src, 13, color=P.MUTED, weight=300)
    c.footer()

    def pos(L, off, t):
        """Fraction of the lap and sample index at time t, with the lap clock scaled to the official time."""
        tt = np.asarray(L["t"], float)
        tt = tt * off / tt[-1]
        j = min(len(tt) - 1, int(np.searchsorted(tt, min(t, off))))
        return float(L["dist"][j] / L["dist"][-1]), j

    r = Reel(out)
    n = int(T / speedup * FPS)
    for f_ in range(n + 1):
        t = min(T, f_ / FPS * speedup)
        fa, ja = pos(A, offa, t)
        fb, jb = pos(B, offb, t)
        da.set_data([A["x"][ja]], [A["y"][ja]])
        jbx = min(len(X) - 1, int(np.searchsorted(fr, fb)))
        db.set_data([X[jbx]], [Y[jbx]])
        for k in range(n_sec):
            sec_lines[k].set_visible(min(fa, fb) >= edges[k + 1] - 1e-6)
        for wd, L, frc, j in ((wa, A, fa, ja), (wb, B, fb, jb)):
            on = int(frc * wd["nb"])
            for k in range(on):
                wd["outer"][k].set_visible(True), wd["inner"][k].set_visible(True)
            ang = np.deg2rad(90 - frc * 360)
            wd["hand"].set_data([0.56 * np.cos(ang), 1.07 * np.cos(ang)], [0.56 * np.sin(ang), 1.07 * np.sin(ang)])
            wd["gt"].set_text(f"{wd['g'][j]:.0f}"), wd["gt"].set_color(DNA[wd["ph"][j]])
            wd["st"].set_text(f"{L['speed'][j]:.0f} km/h")
        lead_f = max(fa, fb)
        if t > 0.5 and t < min(offa, offb):
            if fa >= fb:
                gap = t - float(np.interp(fb, F, ta))
                gap_t.set_text(f"{a['code']} AHEAD BY {max(0.0, gap):.3f} s"), gap_t.set_color(ca)
            else:
                gap = t - float(np.interp(fa, F, tb))
                gap_t.set_text(f"{b['code']} AHEAD BY {max(0.0, gap):.3f} s"), gap_t.set_color(cb)
        r.add(c.fig)
    for wd in (wa, wb):
        for w in wd["outer"] + wd["inner"]:
            w.set_visible(True)
        wd["hand"].set_visible(False)
    for ln in sec_lines:
        ln.set_visible(True)
    win, lose = (a, b) if offa <= offb else (b, a)
    gap_t.set_text(f"{win['code']} BY {abs(offb - offa):.3f} s"), gap_t.set_color(P.GOLD)
    r.add(c.fig, int(1.4 * FPS))
    who = a if gain[best] > 0 else b
    ring.set_visible(True)
    gap_t.set_text(f"BIGGEST SWING: {who['code']} {abs(gain[best]):.3f} s IN ONE MINI SECTOR")
    gap_t.set_fontsize(17)
    r.add(c.fig, int(2.8 * FPS))
    plt.close(c.fig)
    return r.close()
