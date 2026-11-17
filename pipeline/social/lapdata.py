"""Race week data posts from last year's fastest race lap (same lap as the preview): braking zones
decoded (carousel), the lap in data (one telemetry chart), gear map (one image). Paddock Cyan
template: flag, GP name, chequered motif, logo and website on every card.

Precision: OpenF1 car data arrives about 4 times a second, unevenly. Entry speeds on the straights
are solid; the slowest point of a corner can fall between samples, so it is shown as "about",
rounded to 5 km/h, and the source line says so.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap

from . import preview as P
from . import style as S
from .captions import FOOTER, clean, drv, event_tag, paragraphs
from .render import H_POST, lap_time

SAMPLING = "OpenF1 car data, about 4 samples per second"


def r5(v: float) -> int:
    return int(5 * round(float(v) / 5))


def lap_src(p) -> str:
    return f"fastest {p.ref_year} race lap, {p.driver} {lap_time(round(p.lap_s * 1000))}"


def Lap_src(p) -> str:
    s = lap_src(p)
    return s[0].upper() + s[1:]


def corner_at(p, i: int) -> str | None:
    """Turn label of the MultiViewer marker nearest the sample, if it is close enough to be that corner."""
    if not p.corners:
        return None
    span = max(np.ptp(p.x), np.ptp(p.y))
    d = [np.hypot(cx - p.x[i], cy - p.y[i]) for _, _, cx, cy in p.corners]
    k = int(np.argmin(d))
    if d[k] > 0.06 * span:
        return None
    n, letter, _, _ = p.corners[k]
    return f"Turn {n}{letter}"


def zones(p) -> list[dict]:
    out = []
    for a, b in P.brake_runs(p.t, p.brake):
        a0 = max(a - 3, 0)
        entry_i = a0 + int(np.argmax(p.speed[a0:a + 1]))
        hi = min(b + 4, len(p.speed) - 1)
        imin = a + int(np.argmin(p.speed[a:hi + 1]))
        out.append({"a": a, "b": b, "imin": imin, "entry": int(round(p.speed[entry_i])), "min": r5(p.speed[imin]),
                    "shed": r5(p.speed[entry_i] - p.speed[imin]), "gear": int(p.gear[imin]),
                    "km": p.dist[a] / 1000, "turn": corner_at(p, imin)})
    return out


# ---------------------------------------------------------------- braking zones carousel

def zone_trace(ax, p, z: dict):
    """Speed against distance around one braking zone, the braking stretch in the GP colour."""
    i0, i1 = max(z["a"] - 8, 0), min(z["imin"] + 8, len(p.speed) - 1)
    d = (p.dist[i0:i1 + 1] - p.dist[z["a"]])
    v = p.speed[i0:i1 + 1]
    ax.plot(d, v, color=P.MUTED, lw=2.2, zorder=2)
    j0, j1 = z["a"] - i0, z["imin"] - i0
    ax.plot(d[j0:j1 + 1], v[j0:j1 + 1], color=P.EV, lw=4, zorder=3, solid_capstyle="round")
    ax.plot(d[j1], v[j1], "o", ms=9, color=P.TEXT, mec=P.EV, mew=2.5, zorder=4)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#3A4458")
    ax.tick_params(colors=P.MUTED, labelsize=12)
    ax.set_facecolor("none")
    ax.set_xlabel("metres from the brake point", color=P.MUTED, fontsize=12, family=P.FONT)
    ax.set_ylabel("km/h", color=P.MUTED, fontsize=12, family=P.FONT)
    ax.grid(axis="y", color="#232D3F", lw=0.6)


def zone_map(ax, p, z: dict, n: int):
    P.base_line(ax, p)
    m = np.zeros(len(p.x), bool)
    m[z["a"]:z["imin"] + 1] = True
    P.highlight(ax, p, m, lw=7)
    P.dot(ax, p.x[z["imin"]], p.y[z["imin"]], ms=12)


def braking_carousel(p, out: Path) -> list[Path]:
    P.set_event(p)
    zs = zones(p)
    paths = []

    c = P.Card(H_POST)
    c.header(p)
    t = c.top
    c.kicker(t - 0.07, "Braking zones decoded")
    c.number(t - 0.235, str(len(zs)), "per lap", size=170)
    c.text(0.5, t - 0.285, "Every stop on the lap, from full speed to the apex", 24, weight=300)
    P.brake_map(P.track_ax(c, [0.10, 0.16, 0.80, 0.42], p), p)
    c.text(0.5, 0.115, f"Measured on the {lap_src(p)}", 14, color=P.MUTED, weight=300)
    c.footer("SWIPE  →")
    paths.append(c.save(out / "slide_01.jpg"))

    for n, z in enumerate(zs, 1):
        c = P.Card(H_POST)
        c.header(p)
        t = c.top
        c.kicker(t - 0.07, f"Zone {n}" + (f"  |  {z['turn']}" if z["turn"] else ""), n, len(zs))
        c.number(t - 0.225, str(z["shed"]), "km/h shed", size=160)
        c.text(0.5, t - 0.275, f"{z['entry']} km/h in, about {z['min']} km/h at the slowest point, gear {z['gear']}", 23, weight=300)
        c.text(0.5, t - 0.31, f"Brakes on at {z['km']:.1f} km into the lap", 18, color=P.MUTED, weight=400)
        zone_map(P.track_ax(c, [0.06, 0.20, 0.42, 0.34], p), p, z, n)
        tax = c.fig.add_axes([0.58, 0.24, 0.36, 0.26])
        zone_trace(tax, p, z)
        c.text(0.5, 0.135, f"{Lap_src(p)}. {SAMPLING}: slowest point within about 10 km/h", 13, color=P.MUTED, weight=300)
        c.footer("SWIPE  →")
        paths.append(c.save(out / f"slide_{n + 1:02d}.jpg"))

    # summary table
    c = P.Card(H_POST)
    c.header(p)
    t = c.top
    c.kicker(t - 0.07, "All zones, one lap")
    cols = [0.10, 0.30, 0.55, 0.78, 0.92]
    heads = ["ZONE", "WHERE", "IN", "SLOWEST", "GEAR"]
    y = t - 0.15
    for x, h in zip(cols, heads):
        c.text(x, y, h, 13, color=P.CYAN, weight=600, ha="left" if x < 0.5 else "right", track=True)
    c.rule(0.08, 0.94, y - 0.025, color="#3A4458", lw=0.8)
    row = 0.075
    for n, z in enumerate(zs, 1):
        yy = y - 0.065 - (n - 1) * row
        vals = [f"{n}", z["turn"] or f"{z['km']:.1f} km", f"{z['entry']} km/h", f"about {z['min']} km/h", str(z["gear"])]
        for x, v in zip(cols, vals):
            c.text(x, yy, v, 24, weight=300 if x != cols[0] else 200, ha="left" if x < 0.5 else "right")
        c.rule(0.08, 0.94, yy - 0.033, color="#1A2030", lw=0.6)
    big = max(zs, key=lambda z: z["shed"])
    yb = y - 0.065 - len(zs) * row - 0.03
    c.text(0.5, yb, f"Biggest stop: zone {zs.index(big) + 1}, {big['shed']} km/h shed", 22, color=P.EV, weight=500)
    c.text(0.5, 0.115, f"{Lap_src(p)}. {SAMPLING}", 14, color=P.MUTED, weight=300)
    c.footer()
    paths.append(c.save(out / f"slide_{len(zs) + 2:02d}.jpg"))
    return paths


def braking_caption(p) -> str:
    zs = zones(p)
    q, r = P.times_text(p)
    big = max(zs, key=lambda z: z["shed"])
    rows = []
    for n, z in enumerate(zs, 1):
        where = z["turn"] or f"{z['km']:.1f} km"
        rows.append(f"Zone {n}, {where}: {z['entry']} → about {z['min']} km/h, gear {z['gear']}")
    return clean(paragraphs(
        f"🛑 {p.title.title()} has {len(zs)} braking zones. Here is every one.",
        f"📊 Measured on the {lap_src(p).replace(p.driver, drv(p.driver, p.colors))}",
        rows,
        f"🔥 Biggest stop: zone {zs.index(big) + 1}, about {big['shed']} km/h shed",
        f"ℹ️ {SAMPLING}, so the slowest point is within about 10 km/h.",
        f"⏰ Quali {q}\n🏁 Race {r}\n(local time)",
        "💾 Save this for race week.\n💬 Which stop is the hardest? Tell us below.",
        FOOTER, " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Telemetry", "#RaceWeek"])))


# ---------------------------------------------------------------- the lap in data

def _panel(ax, ylabel: str):
    ax.set_facecolor("none")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#3A4458")
    ax.tick_params(colors=P.MUTED, labelsize=11)
    ax.set_ylabel(ylabel, color=P.MUTED, fontsize=12, family=P.FONT, weight=500)
    ax.grid(axis="y", color="#1E2533", lw=0.6)


def lap_in_data(p, out: Path) -> Path:
    P.set_event(p)
    st = p.stats
    zs = zones(p)
    km = p.dist / 1000
    c = P.Card(H_POST)
    c.header(p)
    t = c.top
    c.kicker(t - 0.065, "The lap in data")
    c.text(0.5, t - 0.112, f"{p.driver} {lap_time(round(p.lap_s * 1000))}, fastest lap of the {p.ref_year} race", 24, weight=300)
    share = gear_share(p)
    g8 = max(share, key=share.get)
    kpis = [(f"{st['top_speed']}", "KM/H TOP"), (f"{share[g8]:.0f}", f"% IN {P.ordinal(g8).upper()}"), (f"{st['flat_pct']}", "% FLAT OUT"),
            (f"{len(zs)}", "BRAKING ZONES")]
    for k, (v, u) in enumerate(kpis):
        x = 0.14 + k * 0.24
        c.text(x, t - 0.185, v, 46, weight=200)
        c.text(x, t - 0.225, u, 11, color=P.CYAN, weight=600, track=True)
    c.rule(0.08, 0.92, t - 0.25, color="#232D3F", lw=0.8)

    x0, w = 0.13, 0.80
    axs = c.fig.add_axes([x0, 0.385, w, 0.29]), c.fig.add_axes([x0, 0.285, w, 0.085]), \
        c.fig.add_axes([x0, 0.225, w, 0.045]), c.fig.add_axes([x0, 0.13, w, 0.08])
    sp, th, br, gr = axs
    pts = np.column_stack([km, p.speed])
    seg = np.stack([pts[:-1], pts[1:]], axis=1)
    lc = LineCollection(seg, cmap=P.SPEED_CMAP, linewidths=2.6, capstyle="round")
    lc.set_array(p.speed[:-1])
    lc.set_clim(80, max(p.speed))
    sp.add_collection(lc)
    sp.set_xlim(0, km[-1])
    sp.set_ylim(50, max(p.speed) * 1.08)
    _panel(sp, "Speed  km/h")
    imax = int(np.argmax(p.speed))
    sp.annotate(f"{st['top_speed']} km/h", (km[imax], p.speed[imax]), xytext=(0, 10), textcoords="offset points",
                ha="center", color=P.TEXT, fontsize=12, family=P.FONT, weight=500)
    slow = min(zs, key=lambda z: z["min"]) if zs else None
    if slow:
        i = slow["imin"]
        sp.annotate(f"about {slow['min']}", (km[i], p.speed[i]), xytext=(0, -18), textcoords="offset points",
                    ha="center", color=P.TEXT, fontsize=12, family=P.FONT, weight=500)
    for z in zs:
        sp.axvspan(km[z["a"]], km[z["imin"]], color=P.GOLD, alpha=0.10, lw=0)
    th.fill_between(km, p.throttle, color=P.CYAN, alpha=0.35, lw=0, step="mid")
    th.plot(km, p.throttle, color=P.CYAN, lw=1.2, drawstyle="steps-mid")
    th.set_ylim(0, 105)
    th.set_xlim(0, km[-1])
    _panel(th, "Throttle %")
    br.fill_between(km, (p.brake > 0).astype(float), color=P.GOLD, alpha=0.9, lw=0, step="mid")
    br.set_ylim(0, 1)
    br.set_yticks([])
    br.set_xlim(0, km[-1])
    _panel(br, "Brake")
    gr.plot(km, p.gear, color=P.TEXT, lw=1.4, drawstyle="steps-mid")
    gr.set_ylim(0.5, 8.5)
    gr.set_yticks([2, 4, 6, 8])
    gr.set_xlim(0, km[-1])
    _panel(gr, "Gear")
    for a in (sp, th, br):
        a.tick_params(labelbottom=False)
    c.text(0.5, 0.085, f"km into the lap. Shaded: braking zones. {SAMPLING}", 13, color=P.MUTED, weight=300)
    c.footer()
    path = out / "lap_in_data.jpg"
    c.save(path)
    return path


def lap_caption(p) -> str:
    st = p.stats
    share = gear_share(p)
    g8 = max(share, key=share.get)
    q, r = P.times_text(p)
    return clean(paragraphs(
        f"📈 One lap of {p.title.title()}, in data",
        f"🏎️ The {lap_src(p).replace(p.driver, drv(p.driver, p.colors))}",
        [f"🚀 Top speed: {st['top_speed']} km/h",
         f"⚙️ {share[g8]:.0f}% of the lap in {P.ordinal(g8)} gear",
         f"🟢 {st['flat_pct']}% flat out, longest run {P.km(st['longest_flat_m'])} km without lifting",
         f"🛑 {st['braking_zones']} braking zones (shaded)"],
        "👀 Speed on top, then throttle, brake and gear, all against distance.",
        f"ℹ️ Data: {SAMPLING}.",
        f"⏰ Quali {q}\n🏁 Race {r}\n(local time)",
        "💾 Save this one.\n💬 What surprises you most? Tell us below.",
        FOOTER, " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Telemetry", "#RaceWeek"])))


# ---------------------------------------------------------------- gear map

def gear_share(p) -> dict[int, float]:
    dt = np.diff(p.t, append=p.t[-1])
    g = p.gear.astype(int)
    tot = dt.sum()
    return {k: float(dt[g == k].sum() / tot * 100) for k in range(1, 9) if (g == k).any()}


def gear_map(p, out: Path) -> Path:
    P.set_event(p)
    share = gear_share(p)
    top = max(share, key=share.get)
    cmap = LinearSegmentedColormap.from_list("g", ["#3A4458", P.CYAN, P.EV])
    c = P.Card(H_POST)
    c.header(p)
    t = c.top
    c.kicker(t - 0.07, "Gear map")
    c.number(t - 0.225, f"{share[top]:.0f}", f"% of the lap in {P.ordinal(top)}", size=160)
    c.text(0.5, t - 0.275, "Every metre coloured by the gear in use", 23, weight=300)
    ax = P.track_ax(c, [0.04, 0.18, 0.60, 0.44], p)
    P.base_line(ax, p, lw=6)
    pts = np.column_stack([p.x, p.y])
    seg = np.stack([pts[:-1], pts[1:]], axis=1)
    lc = LineCollection(seg, cmap=cmap, linewidths=4.5, capstyle="round")
    lc.set_array(p.gear[:-1])
    lc.set_clim(1, 8)
    ax.add_collection(lc)
    # time share bars
    bx = c.fig.add_axes([0.68, 0.22, 0.26, 0.36])
    gears = sorted(share)
    bx.barh(gears, [share[g] for g in gears], color=[cmap((g - 1) / 7) for g in gears], height=0.62)
    for g in gears:
        bx.text(share[g] + 1.5, g, f"{share[g]:.0f}%", va="center", color=P.TEXT, fontsize=13, family=P.FONT, weight=400)
    bx.set_yticks(gears)
    bx.set_yticklabels([P.ordinal(g) for g in gears], color=P.MUTED, fontsize=13, family=P.FONT)
    bx.set_xlim(0, max(share.values()) * 1.35)
    bx.set_xticks([])
    bx.set_facecolor("none")
    for side in ("top", "right", "bottom", "left"):
        bx.spines[side].set_visible(False)
    bx.tick_params(length=0)
    c.text(0.81, 0.60, "TIME IN EACH GEAR", 12, color=P.CYAN, weight=600, track=True)
    c.text(0.5, 0.115, f"Measured on the {lap_src(p)}. {SAMPLING}", 14, color=P.MUTED, weight=300)
    c.footer()
    path = out / "gear_map.jpg"
    c.save(path)
    return path


def gear_caption(p) -> str:
    share = gear_share(p)
    top = max(share, key=share.get)
    q, r = P.times_text(p)
    return clean(paragraphs(
        f"⚙️ Gear map of {p.title.title()}: {share[top]:.0f}% of the lap in {P.ordinal(top)} gear",
        ["⏱️ Time in each gear"] + [f"{P.ordinal(g)}: {share[g]:.0f}%" for g in sorted(share)],
        f"📊 Measured on the {lap_src(p).replace(p.driver, drv(p.driver, p.colors))}. Data: {SAMPLING}.",
        f"⏰ Quali {q}\n🏁 Race {r}\n(local time)",
        "💾 Save this for race week.\n💬 Guess the lowest gear used? Tell us below.",
        FOOTER, " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Telemetry", "#RaceWeek"])))
