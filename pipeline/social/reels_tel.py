"""Telemetry Reels (brief: claude/f1th_reels_build_prompt_20261117_v01.md). Original artwork from official timing
and OpenF1 telemetry only, in the house card style (flag header, logo footer, site, big numbers with units).

Kinds:
  pedal       inside one lap: moving dot on the map, throttle and brake bars, gear, speed, clock ending on the
              official lap time (shown at N x speed)
  braker      who brakes latest into the fastest braking zone; error bar = half the sample spacing; rows with
              samples more than 20 m apart are grey (low confidence); verdict computed from the numbers
  guess       anonymous speed trace of a notable lap, reveal at about 70 %
  teammates   season qualifying head to head per team, final classification only, running tally
  pointsrace  championship points race between the drivers fighting for P2, round by round
  ghost       two laps on one map, clock replay, the official times decide the verdict
  longruns    FP2 long run pace race (live template)

Data is gathered in GitHub Actions (OpenF1, Jolpica); renderers take plain dicts, so the same code renders
locally from a JSON dump for review.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import preview as P
from .render import FPS, H_REEL, Reel, lap_time

log = logging.getLogger(__name__)

LOW_CONF_M = 20.0
SRC_TEL = "Telemetry: OpenF1. Times: official timing"
NOTICE = "Unofficial project, not associated with Formula 1 companies"
NICK = {"LAS VEGAS": "at the end of the Strip"}
COMP_COLOR = {"SOFT": "#FF3333", "MEDIUM": "#FFF200", "HARD": "#F2F4F7", "INTERMEDIATE": "#39B54A", "WET": "#00AEEF"}


# ---------------------------------------------------------------- data (Actions)

def _lap_tel(oc, sk: int, lap: pd.Series, rot: float) -> dict:
    t0 = pd.Timestamp(lap["date_start"])
    t1 = t0 + pd.Timedelta(seconds=float(lap["lap_duration"]))
    win = [f"date>={(t0 - pd.Timedelta(seconds=1)).isoformat()}", f"date<={(t1 + pd.Timedelta(seconds=1)).isoformat()}"]
    drv = int(lap["driver_number"])
    car = oc.frame("car_data", win, session_key=sk, driver_number=drv)
    loc = oc.frame("location", win, session_key=sk, driver_number=drv)
    ct = (pd.to_datetime(car["date"], format="ISO8601", utc=True) - t0).dt.total_seconds().to_numpy()
    lt = (pd.to_datetime(loc["date"], format="ISO8601", utc=True) - t0).dt.total_seconds().to_numpy()
    keep = (ct >= 0) & (ct <= float(lap["lap_duration"]))
    car, ct = car[keep], ct[keep]
    sp = car["speed"].to_numpy(float)
    dist = np.concatenate([[0.0], np.cumsum(np.diff(ct) * (sp[1:] + sp[:-1]) / 2 / 3.6)])
    x, y = np.interp(ct, lt, loc["x"].to_numpy(float)), np.interp(ct, lt, loc["y"].to_numpy(float))
    a = math.radians(rot)
    xr, yr = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
    r = lambda v: [round(float(q), 2) for q in v]
    return {"t": r(ct), "dist": r(dist), "speed": r(sp), "throttle": r(car["throttle"]), "brake": r(car["brake"]),
            "gear": r(car["n_gear"]), "x": r(xr), "y": r(yr), "lap_s": float(lap["lap_duration"]), "lap": int(lap["lap_number"])}


def _session(oc, year: int, ck: int, name: str):
    s = oc.frame("sessions", year=year, circuit_key=ck, session_name=name)
    return int(s.iloc[0]["session_key"]) if len(s) else None


def _codes(oc, sk):
    d = oc.frame("drivers", session_key=sk)
    return ({int(r["driver_number"]): r["name_acronym"] for _, r in d.iterrows()},
            {r["name_acronym"]: "#" + str(r.get("team_colour") or "888888").lstrip("#") for _, r in d.iterrows()})


def _compound(oc, sk, drv: int, lap_no: int) -> str | None:
    st = oc.frame("stints", session_key=sk, driver_number=drv)
    for _, s in st.iterrows():
        if pd.notna(s["lap_start"]) and pd.notna(s["lap_end"]) and s["lap_start"] <= lap_no <= s["lap_end"]:
            return str(s["compound"]).upper()
    return None


def lap_of(oc, year: int, ck: int, session_name: str, rot: float, code: str | None = None, official_ms: float | None = None) -> dict:
    """Fastest lap of a session (or of one driver), with telemetry, compound and team colour."""
    sk = _session(oc, year, ck, session_name)
    laps = oc.frame("laps", session_key=sk)
    codes, cols = _codes(oc, sk)
    laps = laps[laps["lap_duration"].notna()].copy()
    laps["code"] = laps["driver_number"].map(lambda n: codes.get(int(n)))
    if code:
        laps = laps[laps["code"] == code]
    if official_ms:                                            # match the official time (within 5 ms)
        m = laps[(laps["lap_duration"] * 1000 - official_ms).abs() < 5]
        if len(m):
            laps = m
    lap = laps.sort_values("lap_duration").iloc[0]
    tel = _lap_tel(oc, sk, lap, rot)
    tel |= {"code": lap["code"], "color": cols.get(lap["code"]), "year": year, "session": session_name,
            "compound": _compound(oc, sk, int(lap["driver_number"]), int(lap["lap_number"]))}
    return tel


def brake_rows(oc, year: int, ck: int, rot: float, ref_xy: tuple[float, float], session_name: str = "Race") -> list[dict]:
    """Brake point into one corner on each driver's fastest lap: metres before the apex, with the error bar."""
    sk = _session(oc, year, ck, session_name)
    laps = oc.frame("laps", session_key=sk)
    codes, cols = _codes(oc, sk)
    laps = laps[laps["lap_duration"].notna() & (laps["lap_number"] > 1) & ~laps["is_pit_out_lap"].fillna(False).astype(bool)]
    out = []
    for num, g in laps.groupby("driver_number"):
        lap = g.sort_values("lap_duration").iloc[0]
        try:
            tel = _lap_tel(oc, sk, lap, rot)
        except Exception as e:
            log.warning("no telemetry for %s: %s", num, e)
            continue
        x, y, dist, br = (np.array(tel[k]) for k in ("x", "y", "dist", "brake"))
        if len(x) < 50:
            continue
        apex = int(np.argmin(np.hypot(x - ref_xy[0], y - ref_xy[1])))
        on = None
        for i in range(apex, max(apex - 60, 1), -1):            # walk back from the apex to the first brake sample
            if br[i] > 0 and br[i - 1] == 0:
                on = i
                break
            if dist[apex] - dist[i] > 450:
                break
        if on is None:
            continue
        onset = (dist[on] + dist[on - 1]) / 2
        out.append({"code": codes.get(int(num)), "color": cols.get(codes.get(int(num))), "m": round(float(dist[apex] - onset), 1),
                    "err": round(float(dist[on] - dist[on - 1]) / 2, 1), "lap": int(lap["lap_number"])})
    return sorted(out, key=lambda r: r["m"])


def brake_rows_race(oc, year: int, ck: int, rot: float, ref_xy: tuple[float, float], session_name: str = "Race",
                    min_laps: int = 8, ref_frac: float | None = None) -> list[dict]:
    """Brake point into one corner on every green lap: metres from brake onset to the slowest point of the corner,
    median per driver with the standard error. Car data only (speed, brake), one request per driver: the corner is
    found by its share of the lap distance (ref_frac) and the slowest point within 350 m of it.
    One lap at about 4 samples a second is too coarse; 20+ laps per driver are not, because the sample timing
    falls at a different place on every lap."""
    sk = _session(oc, year, ck, session_name)
    laps = oc.frame("laps", session_key=sk)
    codes, cols = _codes(oc, sk)
    laps = laps[laps["lap_duration"].notna() & (laps["lap_number"] > 1) & ~laps["is_pit_out_lap"].fillna(False).astype(bool)]
    out = []
    for num, g in laps.groupby("driver_number"):
        med = g["lap_duration"].median()
        g = g[g["lap_duration"] <= med * 1.03]                    # green laps only (no SC, VSC, in laps)
        if len(g) < min_laps:
            continue
        car = oc.frame("car_data", session_key=sk, driver_number=int(num))
        if car.empty:
            continue
        ct = pd.to_datetime(car["date"], format="ISO8601", utc=True)
        c0 = ct.iloc[0]
        cs = (ct - c0).dt.total_seconds().to_numpy()
        sp, br = car["speed"].to_numpy(float), car["brake"].to_numpy(float)
        vals = []
        for _, lap in g.iterrows():
            t0 = (pd.Timestamp(lap["date_start"]) - c0).total_seconds()
            idx = np.where((cs >= t0) & (cs <= t0 + float(lap["lap_duration"])))[0]
            if len(idx) < 50:
                continue
            d = np.concatenate([[0.0], np.cumsum(np.diff(cs[idx]) * (sp[idx][1:] + sp[idx][:-1]) / 2 / 3.6)])
            target = ref_frac * d[-1]
            win = np.where(np.abs(d - target) < 350)[0]
            if len(win) < 5:
                continue
            ap = int(win[np.argmin(sp[idx][win])])
            b = br[idx]
            for i in range(ap, max(ap - 60, 1), -1):
                if b[i] > 0 and b[i - 1] == 0:
                    vals.append(float(d[ap] - (d[i] + d[i - 1]) / 2))
                    break
                if d[ap] - d[i] > 450:
                    break
        if len(vals) >= min_laps:
            v = np.array(vals)
            out.append({"code": codes.get(int(num)), "color": cols.get(codes.get(int(num))), "m": round(float(np.median(v)), 1),
                        "err": round(float(v.std(ddof=1) / math.sqrt(len(v))), 1), "n": len(v)})
    return sorted(out, key=lambda r: r["m"])


def season_quali(season: int, upto: int) -> list[dict]:
    from .. import jolpica
    rows = []
    for rnd in range(1, upto + 1):
        q = jolpica._get(f"{season}/{rnd}/qualifying.json?limit=100")["RaceTable"]["Races"]
        if not q:
            continue
        for x in q[0].get("QualifyingResults", []):
            rows.append({"round": rnd, "code": x["Driver"].get("code"), "team": x["Constructor"]["name"], "pos": int(x["position"]),
                         "race": q[0]["raceName"].replace(" Grand Prix", "")})
    return rows


def season_points(season: int, upto: int) -> list[dict]:
    from .. import jolpica
    out = []
    for rnd in range(1, upto + 1):
        ds = jolpica._get(f"{season}/{rnd}/driverStandings.json?limit=10")["StandingsTable"]["StandingsLists"]
        if not ds:
            continue
        out.append({"round": rnd, "pts": {x["Driver"].get("code"): float(x["points"]) for x in ds[0]["DriverStandings"]}})
    return out


def gather(p) -> dict:
    """Everything the week's Reels need, as plain JSON."""
    from .. import jolpica
    from ..__main__ import schedule
    from ..ingest import corner_markers
    from ..openf1 import OpenF1
    from .lapdata import zones
    oc = OpenF1()
    sess = [s for s in schedule(oc, p.season) if s["round"] == p.round]
    ck = int(sess[0]["circuit_key"])
    mk = corner_markers(p.season - 1, ck)
    rot = mk.attrs.get("rotation", 0.0) if len(mk) else 0.0
    d: dict = {"ck": ck, "rot": rot}
    d["record"] = {"t": p.t.tolist(), "dist": p.dist.tolist(), "speed": p.speed.tolist(), "throttle": p.throttle.tolist(),
                   "brake": p.brake.tolist(), "gear": p.gear.tolist(), "x": p.x.tolist(), "y": p.y.tolist(), "lap_s": p.lap_s,
                   "code": p.driver, "color": p.colors.get(p.driver), "year": p.ref_year, "session": "Race"}
    cid = next(e["circuit_id"] for e in jolpica.events(p.season) if e["round"] == p.round)
    poles = {}
    for y in range(p.season - 3, p.season):
        ev = next((e for e in jolpica.events(y) if e["circuit_id"] == cid), None)
        if not ev:
            continue
        q = jolpica._get(f"{y}/{ev['round']}/qualifying.json?limit=3")["RaceTable"]["Races"]
        if q:
            x = q[0]["QualifyingResults"][0]
            t = x.get("Q3") or x.get("Q2") or x.get("Q1")
            m, _, sec = t.rpartition(":")
            poles[y] = {"code": x["Driver"].get("code"), "time": t, "ms": (int(m or 0) * 60 + float(sec)) * 1000}
    d["poles"] = poles
    for y in sorted(poles)[:2]:                                   # two dry poles for the ghost duel
        try:
            d[f"pole{y}"] = lap_of(oc, y, ck, "Qualifying", rot, poles[y]["code"], poles[y]["ms"])
        except Exception as e:
            log.warning("pole lap %s: %s", y, e)
    try:                                                          # guess the driver: fastest race lap two years ago
        d["guess"] = lap_of(oc, p.season - 2, ck, "Race", rot)
    except Exception as e:
        log.warning("guess lap: %s", e)
    try:
        zs = zones(p)
        z = max(zs, key=lambda z: z["entry"])
        d["zone"] = {"turn": z["turn"], "entry": z["entry"], "xy": [float(p.x[z["imin"]]), float(p.y[z["imin"]])]}
        d["braker"] = brake_rows_race(oc, p.ref_year, ck, rot, tuple(d["zone"]["xy"]), ref_frac=float(p.dist[z["imin"]] / p.dist[-1]))
    except Exception as e:
        log.warning("braker: %s", e)
    done = int(jolpica._get(f"{p.season}/driverStandings.json?limit=1")["StandingsTable"]["StandingsLists"][0]["round"])
    d["after_round"] = done
    d["quali"] = season_quali(p.season, done)
    d["points"] = season_points(p.season, done)
    return d


# ---------------------------------------------------------------- drawing helpers

def _card(p):
    c = P.Card(H_REEL, story=True)
    c.header(p)
    return c


def _hook(c, lines: list[str], sub: str | None = None, y0: float = 0.80):
    out = []
    for k, s in enumerate(lines):
        out.append(c.text(0.5, y0 - k * 0.042, s, 44, weight=300))
    if sub:
        out.append(c.text(0.5, y0 - len(lines) * 0.042 - 0.005, sub.upper(), 15, color=P.CYAN, weight=600, track=True))
    return out


def _foot(c, src: str):
    c.text(0.5, 0.175, src, 13, color=P.MUTED, weight=300)
    c.text(0.5, 0.158, NOTICE, 11, color="#5D6573", weight=300)
    c.footer()


def _clock(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:06.3f}"


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _track(c, rect, xs, ys, lw=7):
    ax = c.fig.add_axes(rect)
    ax.set_aspect("equal")
    ax.axis("off")
    pad = 0.06 * max(np.ptp(xs), np.ptp(ys))
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.plot(xs, ys, color=P.BASE, lw=lw, solid_capstyle="round", zorder=1)
    return ax


def _tyre_chip(c, x, y, compound: str | None):
    """A small tyre glyph in the compound colour with its name, centred at (x, y) in figure units."""
    if not compound:
        return
    cp = "INTER" if compound.startswith("INTER") else compound
    code = {"SOFT": "S", "MEDIUM": "M", "HARD": "H", "INTER": "I", "WET": "W"}.get(cp, "?")
    h = 0.03
    w = h * H_REEL / 1080
    ax = c.fig.add_axes([x - w / 2, y - h / 2, w, h])
    ax.set_xlim(-1.1, 1.1), ax.set_ylim(-1.1, 1.1), ax.set_aspect("equal"), ax.axis("off")
    if cp in P.COMPOUND_COLOR:
        P.tyre(ax, 0, 0, 1.0, cp, code, label=False)
    c.text(x + w / 2 + 0.01, y, cp.lower() + "s", 16, color=P.COMPOUND_COLOR.get(cp, P.TEXT), weight=600, ha="left")


# ---------------------------------------------------------------- renderers

def pedal(p, lap: dict, out: Path, hook: list[str], sub: str, src: str = SRC_TEL, target_s: float = 15.0) -> Path:
    """Inside one lap. Clock ends on the official lap time."""
    P.set_event(p)
    L = {k: np.array(v, float) if isinstance(v, list) else v for k, v in lap.items()}
    factor = max(1, round(L["lap_s"] / target_s))
    c = _card(p)
    _hook(c, hook, f"{sub}, shown at {factor}x speed")
    ax = _track(c, [0.14, 0.50, 0.72, 0.21], L["x"], L["y"])
    trail, = ax.plot([], [], color=P.EV, lw=4, zorder=2)
    dot, = ax.plot([], [], "o", ms=16, color=P.TEXT, mec=P.EV, mew=4, zorder=3)
    bars = []
    for k, (lbl, col) in enumerate((("THROTTLE", "#10B981"), ("BRAKE", "#EF4444"))):
        x0 = 0.12 + k * 0.17
        c.fig.add_artist(plt.Rectangle((x0, 0.24), 0.11, 0.22, transform=c.fig.transFigure, fc="#141923", ec="#232D3F", lw=2))
        r = plt.Rectangle((x0, 0.24), 0.11, 0.0, transform=c.fig.transFigure, fc=col)
        c.fig.add_artist(r)
        bars.append(r)
        c.text(x0 + 0.055, 0.225, lbl, 13, color=P.MUTED, weight=600, track=True)
    thr_v = c.text(0.175, 0.475, "", 22, weight=300)
    gear = c.text(0.73, 0.40, "", 130, weight=200)
    c.text(0.73, 0.335, "GEAR", 14, color=P.MUTED, weight=600, track=True)
    spd = c.text(0.73, 0.285, "", 46, color=P.CYAN, weight=300)
    c.text(0.73, 0.255, "KM/H", 13, color=P.MUTED, weight=600, track=True)
    clock = c.text(0.73, 0.225, "", 24, weight=300)
    _tyre_chip(c, 0.66, 0.475, L.get("compound"))
    _foot(c, src)
    r = Reel(out)
    T = L["t"]
    n = int(L["lap_s"] / factor * FPS)
    for i in range(n + 1):
        t = min(L["lap_s"], i / FPS * factor)
        j = min(len(T) - 1, int(np.searchsorted(T, t)))
        trail.set_data(L["x"][:j + 1], L["y"][:j + 1])
        dot.set_data([L["x"][j]], [L["y"][j]])
        th = float(np.clip(L["throttle"][j], 0, 100))
        bars[0].set_height(0.22 * th / 100)
        bars[1].set_height(0.22 if L["brake"][j] > 0 else 0)
        thr_v.set_text(f"{th:.0f}%")
        gear.set_text(f"{L['gear'][j]:.0f}")
        spd.set_text(f"{L['speed'][j]:.0f}")
        clock.set_text(_clock(t))
        r.add(c.fig)
    clock.set_text(_clock(L["lap_s"]))
    clock.set_color(P.GOLD)
    r.add(c.fig, int(2.5 * FPS))
    plt.close(c.fig)
    return r.close()


def braker(p, rows: list[dict], zone: dict, out: Path, year: int, label: str = "race") -> Path:
    P.set_event(p)
    rows = sorted(rows, key=lambda r: r["m"])[:20]
    multi = "n" in rows[0] if rows else False
    low = [(r.get("n", 99) < 10 or r["err"] > 10) if multi else r["err"] * 2 > LOW_CONF_M for r in rows]
    lead = next((r for r, l in zip(rows, low) if not l), None)
    c = _card(p)
    where = NICK.get(p.title) or f"into {zone.get('turn') or 'the fastest braking zone'}"
    _hook(c, ["Who brakes latest", f"{where}?"], f"{year} {label}, {zone['entry']} km/h on entry" + (", every green lap" if multi else ", fastest lap"))
    ax = c.fig.add_axes([0.20, 0.25, 0.72, 0.44])
    ax.set_facecolor("none")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=P.MUTED, labelsize=13, length=0)
    ax.invert_yaxis()
    names = [r["code"] for r in rows]
    vals = np.array([r["m"] for r in rows])
    errs = np.array([r["err"] for r in rows])
    ax.set_yticks(range(len(rows)), names, fontsize=14 if len(rows) > 14 else 16, color=P.TEXT)
    ax.set_xlim(0, vals.max() * 1.35)
    ax.set_xlabel("metres from the brake going on to the slowest point of the corner (shorter = later)", color=P.MUTED, fontsize=12)
    cols = ["#3A4252" if l else (r.get("color") or P.CYAN) for r, l in zip(rows, low)]   # team colours (Michel, 17 Nov)
    bars = ax.barh(range(len(rows)), np.zeros(len(rows)), color=cols, height=0.62,
                   edgecolor=[P.GOLD if r is lead else "none" for r in rows], linewidth=2.5)
    for k, r in enumerate(rows):
        ax.get_yticklabels()[k].set_color(P.GOLD if r is lead else P.TEXT)
    labels = [ax.text(0, k, "", va="center", fontsize=13, color=P.GOLD if rows[k] is lead else P.TEXT, family=P.FONT)
              for k in range(len(rows))]
    verdict = c.text(0.5, 0.215, "", 22, color=P.GOLD, weight=500)
    c.text(0.5, 0.195, ("Median of each driver's green laps, ± standard error. Grey: fewer than 10 laps or ±10 m or more" if multi
                         else "Grey: telemetry samples more than 20 m apart, low confidence"), 12, color=P.MUTED, weight=300)
    _foot(c, f"{year} {label}. Brake onset taken between two telemetry samples. OpenF1")
    if lead is not None:
        n_tie = sum(1 for r, l in zip(rows, low) if not l and r is not lead and r["m"] - r["err"] <= lead["m"] + lead["err"])
        vtxt = (f"{lead['code']} leads, but {n_tie} others are within the data's error" if n_tie
                else f"{lead['code']} brakes latest, clear of the error band")
    else:
        vtxt = "Too close to call: every row is inside the data's error"
    r = Reel(out)
    run, hold = int(6 * FPS), int(4 * FPS)
    for i in range(run + hold):
        g = _ease(i / run)
        for k, b in enumerate(bars):
            b.set_width(vals[k] * g)
            if g >= 1:
                labels[k].set_position((vals[k] + 3, k))
                labels[k].set_text(f"{vals[k]:.0f} m  ±{errs[k]:.0f}")
        if i == run:
            verdict.set_text(vtxt)
        r.add(c.fig)
    plt.close(c.fig)
    return r.close()


def guess(p, lap: dict, out: Path, what: str | None = None) -> Path:
    P.set_event(p)
    L = {k: np.array(v, float) if isinstance(v, list) else v for k, v in lap.items()}
    c = _card(p)
    hook = _hook(c, ["Who is it?", "Comment your guess"], what or f"fastest lap of the {L['year']} race here")
    ax = c.fig.add_axes([0.12, 0.38, 0.80, 0.28])
    ax.set_facecolor("none")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=P.MUTED, labelsize=12, length=0)
    ax.set_xlim(0, L["dist"][-1] / 1000)
    ax.set_ylim(min(L["speed"]) - 20, max(L["speed"]) + 25)
    ax.set_xlabel("km into the lap", color=P.MUTED, fontsize=12)
    ax.set_ylabel("km/h", color=P.MUTED, fontsize=12)
    ax.grid(axis="y", color="#1E2533", lw=0.6)
    line, = ax.plot([], [], color=P.CYAN, lw=3)
    hints = c.text(0.5, 0.31, "", 20, weight=300)
    reveal = c.text(0.5, 0.26, "", 60, weight=200)
    sub = c.text(0.5, 0.215, "", 18, color=P.CYAN, weight=600, track=True)
    _foot(c, f"Lap time: official timing. Telemetry: OpenF1")
    r = Reel(out)
    n = int(9 * FPS)
    for i in range(n):
        k = int((len(L["dist"]) - 1) * _ease(i / n))
        line.set_data(L["dist"][:k + 1] / 1000, L["speed"][:k + 1])
        if i == int(0.4 * n):
            hints.set_text(f"top speed {max(L['speed']):.0f} km/h, {L['compound'].lower() if L.get('compound') else 'tyre unknown'}s")
        r.add(c.fig)
    for i in range(int(1.5 * FPS)):                              # countdown pause
        r.add(c.fig)
    reveal.set_text(L["code"])
    reveal.set_color(L.get("color") or P.TEXT)
    sub.set_text(f"{_clock(L['lap_s'])}  |  LAP {L['lap']}")
    line.set_color(L.get("color") or P.CYAN)
    r.add(c.fig, int(3.5 * FPS))
    plt.close(c.fig)
    return r.close()


def teammates(p, rows: list[dict], after_round: int, out: Path, colors: dict, order: list[str] | None = None) -> Path:
    P.set_event(p)
    df = pd.DataFrame(rows)
    teams = []
    for t, g in df.groupby("team"):
        drivers = g["code"].value_counts()
        if len(drivers) < 2:
            continue
        a, b = drivers.index[:2]
        tally = []
        ta = tb = 0
        for rnd in sorted(g["round"].unique()):
            rr = g[g["round"] == rnd].set_index("code")["pos"]
            if a in rr and b in rr:
                if rr[a] < rr[b]:
                    ta += 1
                else:
                    tb += 1
            tally.append((rnd, ta, tb))
        teams.append((t, a, b, tally))
    if order:                                                       # constructors standings order
        rank = {t: i for i, t in enumerate(order)}
        teams.sort(key=lambda x: rank.get(x[0], 99))
    teams = teams[:11]
    c = _card(p)
    _hook(c, ["Teammate wars", f"{p.season} qualifying"], f"head to head, after round {after_round}")
    rows_t = []
    for i, (t, a, b, tally) in enumerate(teams):
        y = 0.68 - i * 0.041
        c.text(0.08, y, t, 13, color=P.MUTED, weight=400, ha="left")
        la = c.text(0.44, y, "", 18, weight=600, ha="right")
        lb = c.text(0.92, y, "", 18, weight=600, ha="right")
        bar_a = plt.Rectangle((0.46, y - 0.008), 0, 0.016, transform=c.fig.transFigure, color=colors.get(a, P.CYAN))
        bar_b = plt.Rectangle((0.46, y - 0.008), 0, 0.016, transform=c.fig.transFigure, color="#2A3242")
        c.fig.add_artist(bar_b)
        c.fig.add_artist(bar_a)
        rows_t.append((a, b, tally, la, lb, bar_a, bar_b))
    rnd_lbl = c.text(0.5, 0.20, "", 18, color=P.CYAN, weight=600, track=True)
    _foot(c, "Final qualifying classification each round (Jolpica, official)")
    r = Reel(out)
    n_rounds = max(len(x[2]) for x in rows_t)
    per = int(0.45 * FPS)
    for k in range(n_rounds):
        for a, b, tally, la, lb, ba, bb in rows_t:
            rnd, ta, tb = tally[min(k, len(tally) - 1)]
            tot = max(ta + tb, 1)
            ba.set_width(0.34 * ta / tot)
            bb.set_width(0.34)
            la.set_text(f"{a} {ta}")
            lb.set_text(f"{tb} {b}")
        rnd_lbl.set_text(f"ROUND {tally[min(k, len(tally) - 1)][0]}")
        r.add(c.fig, per)
    rnd_lbl.set_text(f"AFTER ROUND {after_round}")
    r.add(c.fig, int(3 * FPS))
    plt.close(c.fig)
    return r.close()


def pointsrace(p, points: list[dict], codes: list[str], colors: dict, out: Path) -> Path:
    P.set_event(p)
    c = _card(p)
    _hook(c, ["The fight for P2", "round by round"], f"{p.season} drivers championship, after round {points[-1]['round']}")
    ax = c.fig.add_axes([0.12, 0.25, 0.70, 0.42])
    ax.set_facecolor("none")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=P.MUTED, labelsize=12, length=0)
    ax.grid(axis="y", color="#1E2533", lw=0.6)
    rounds = [x["round"] for x in points]
    series = {cd: [x["pts"].get(cd, 0) for x in points] for cd in codes}
    ax.set_xlim(1, rounds[-1] + 0.5)
    ax.set_ylim(0, max(max(v) for v in series.values()) * 1.1)
    ax.set_xlabel("round", color=P.MUTED, fontsize=12)
    ax.set_xticks([1, 5, 10, 15, 20][: len([t for t in (1, 5, 10, 15, 20) if t <= rounds[-1]])])
    lines = {cd: ax.plot([], [], color=colors.get(cd, P.CYAN), lw=3.4)[0] for cd in codes}
    tags = {cd: ax.text(0, 0, "", color=colors.get(cd, P.CYAN), fontsize=15, family=P.FONT, weight=700, va="center") for cd in codes}
    gap = c.text(0.5, 0.21, "", 24, color=P.GOLD, weight=500)
    _foot(c, "Official standings after each round (Jolpica)")
    r = Reel(out)
    n = int(10 * FPS)
    for i in range(n + 1):
        u = 1 + (len(rounds) - 1) * _ease(i / n)
        k = int(u)
        ends = {}
        for cd in codes:
            xs = rounds[:k] + ([u] if k < len(rounds) else [])
            ys = series[cd][:k] + ([np.interp(u, rounds, series[cd])] if k < len(rounds) else [])
            lines[cd].set_data(xs, ys)
            ends[cd] = (xs[-1], ys[-1])
        span = ax.get_ylim()[1] * 0.045                              # keep the labels apart
        placed = []
        for cd in sorted(codes, key=lambda q: -ends[q][1]):
            yv = ends[cd][1]
            for py in placed:
                if abs(yv - py) < span:
                    yv = py - span
            placed.append(yv)
            tags[cd].set_position((ends[cd][0] + 0.3, yv))
            tags[cd].set_text(f"{cd} {ends[cd][1]:.0f}")
        r.add(c.fig)
    last = {cd: series[cd][-1] for cd in codes}
    order = sorted(codes, key=lambda cd: -last[cd])
    gap.set_text(f"{order[0]} leads {order[1]} by {last[order[0]] - last[order[1]]:.0f}, {order[2]} {last[order[1]] - last[order[2]]:.0f} further back")
    r.add(c.fig, int(3.5 * FPS))
    plt.close(c.fig)
    return r.close()


def ghost(p, a: dict, b: dict, out: Path, hook: list[str]) -> Path:
    """Two laps replayed on one map. The verdict uses the official lap times only."""
    P.set_event(p)
    A = {k: np.array(v, float) if isinstance(v, list) else v for k, v in a.items()}
    B = {k: np.array(v, float) if isinstance(v, list) else v for k, v in b.items()}
    c = _card(p)
    _hook(c, hook, f"{A['code']} {A['year']} vs {B['code']} {B['year']}, official pole times")
    ax = _track(c, [0.08, 0.40, 0.84, 0.30], A["x"], A["y"], lw=9)
    ca, cb = A.get("color") or P.CYAN, B.get("color") or P.GOLD
    if ca == cb:
        cb = P.GOLD
    da, = ax.plot([], [], "o", ms=18, color=ca, mec=P.TEXT, mew=2, zorder=3)
    db, = ax.plot([], [], "o", ms=18, color=cb, mec=P.TEXT, mew=2, zorder=3)
    c.text(0.30, 0.355, f"{A['code']} {A['year']}", 24, color=ca, weight=600)
    c.text(0.70, 0.355, f"{B['code']} {B['year']}", 24, color=cb, weight=600)
    ta = c.text(0.30, 0.31, "", 34, weight=200)
    tb = c.text(0.70, 0.31, "", 34, weight=200)
    _tyre_chip(c, 0.22, 0.275, A.get("compound"))
    _tyre_chip(c, 0.62, 0.275, B.get("compound"))
    verdict = c.text(0.5, 0.215, "", 26, color=P.GOLD, weight=500)
    _foot(c, "Lap times: official classification (Jolpica). Positions: OpenF1 telemetry")
    r = Reel(out)
    lap = max(A["lap_s"], B["lap_s"])
    n = int(14 * FPS)
    for i in range(n + 1):
        t = lap * i / n
        for L, d, tt in ((A, da, ta), (B, db, tb)):
            tl = min(t, L["lap_s"])
            d.set_data([np.interp(tl, L["t"], L["x"])], [np.interp(tl, L["t"], L["y"])])
            tt.set_text(_clock(tl))
        r.add(c.fig)
    g = B["lap_s"] - A["lap_s"]
    faster = A if g > 0 else B
    verdict.set_text(f"{faster['code']} {faster['year']} quicker by {abs(g):.3f} s")
    r.add(c.fig, int(3.5 * FPS))
    plt.close(c.fig)
    return r.close()


# ---------------------------------------------------------------- production (Michel, 17 Nov: approved, post at half past)

# day offset from qualifying day -> {hour PT: kind}; posted at HH:30, between the hourly stories
REEL_SLOTS = {
    -2: {12: "pedal_record", 15: "braker", 21: "guess"},
    -1: {12: "teammates", 15: "points"},
    0: {11: "guess_fp2", 12: "ghost", 15: "pedal_pole"},
    1: {12: "pedal_q", 15: "braker_fp2"},
}
TAGS = "#F1 #Formula1 {ev} #F1Telemetry #RaceWeek"


def _ctx(p):
    from ..__main__ import schedule
    from ..ingest import corner_markers
    from ..openf1 import OpenF1
    oc = OpenF1()
    sess = [s for s in schedule(oc, p.season) if s["round"] == p.round]
    ck = int(sess[0]["circuit_key"])
    mk = corner_markers(p.season - 1, ck)
    return oc, ck, (mk.attrs.get("rotation", 0.0) if len(mk) else 0.0)


def _poles(p) -> dict:
    from .. import jolpica
    cid = next(e["circuit_id"] for e in jolpica.events(p.season) if e["round"] == p.round)
    out = {}
    for y in range(p.season - 3, p.season):
        ev = next((e for e in jolpica.events(y) if e["circuit_id"] == cid), None)
        if not ev:
            continue
        q = jolpica._get(f"{y}/{ev['round']}/qualifying.json?limit=3")["RaceTable"]["Races"]
        if q and q[0].get("QualifyingResults"):
            x = q[0]["QualifyingResults"][0]
            t = x.get("Q3") or x.get("Q2") or x.get("Q1")
            m_, _, sec = t.rpartition(":")
            out[y] = {"code": x["Driver"].get("code"), "time": t, "ms": (int(m_ or 0) * 60 + float(sec)) * 1000}
    return out


def _dry_poles(p, oc, ck, rot) -> list[dict]:
    laps = []
    for y, v in sorted(_poles(p).items(), reverse=True):
        try:
            lap = lap_of(oc, y, ck, "Qualifying", rot, v["code"], v["ms"])
        except Exception as e:
            log.warning("pole lap %s: %s", y, e)
            continue
        if (lap.get("compound") or "").upper() in ("SOFT", "MEDIUM", "HARD"):
            lap["official"] = v["time"]
            laps.append(lap)
    return laps


def _colors_now(oc, season: int, fallback: dict) -> dict:
    """Team colours of this season's latest race (so new drivers and teams get theirs)."""
    try:
        rs = oc.frame("sessions", year=season, session_name="Race")
        sk = int(rs.sort_values("date_start").iloc[-1]["session_key"])
        return {**fallback, **_codes(oc, sk)[1]}
    except Exception:
        return dict(fallback)


def _cap(p, *blocks) -> str:
    from .captions import FOOTER, clean, event_tag, paragraphs
    return clean(paragraphs(*blocks, FOOTER, TAGS.format(ev=event_tag(p.event))))


def build(p, kind: str, out: Path) -> tuple[Path, str] | None:
    """Render one Reel for the hourly pipeline: (video, caption), or None when its data is not in."""
    import subprocess
    from .captions import drv
    from .extras import circuit_history
    out.mkdir(parents=True, exist_ok=True)
    video = out / f"reel_{kind}.mp4"
    oc, ck, rot = _ctx(p)
    name = p.title.title()
    if kind == "pedal_record":
        h = [x for x in circuit_history(p.season, p.round) if x["year"] == p.ref_year]
        if not h or h[0]["fl_code"] != p.driver:
            return None
        from .insights import gather as ig
        plan = ig(p.season, p.round, p.title).get("plan", {}).get(p.driver, [])
        cpd = next((c_ for c_, a_, b_ in plan if a_ <= h[0]["fl_lap"] <= b_), None)
        lap = {"t": p.t.tolist(), "dist": p.dist.tolist(), "speed": p.speed.tolist(), "throttle": p.throttle.tolist(),
               "brake": p.brake.tolist(), "gear": p.gear.tolist(), "x": p.x.tolist(), "y": p.y.tolist(), "lap_s": p.lap_s,
               "compound": cpd, "lap": h[0]["fl_lap"]}
        pedal(p, lap, video, ["Inside the", "race lap record"], f"{p.driver}, {p.ref_year}, lap {h[0]['fl_lap']}, {h[0]['fl_time']}")
        cap = _cap(p, f"🎥 Inside the {name} race lap record: {drv(p.driver, p.colors)}, {p.ref_year}, {h[0]['fl_time']} on lap {h[0]['fl_lap']}",
                   "👀 Throttle, brake, gear and speed, live on the map, shown faster than real time.",
                   f"🏁 Top speed {p.stats['top_speed']} km/h, {p.stats['flat_pct']}% of the lap flat out.",
                   "💾 Save it.\n💬 Where would you lift? Tell us below.")
    elif kind in ("braker", "braker_fp2"):
        from .lapdata import zones
        z = max(zones(p), key=lambda z: z["entry"])
        zone = {"turn": z["turn"], "entry": z["entry"], "xy": [float(p.x[z["imin"]]), float(p.y[z["imin"]])]}
        frac = float(p.dist[z["imin"]] / p.dist[-1])
        if kind == "braker":
            rows, year, label = brake_rows_race(oc, p.ref_year, ck, rot, tuple(zone["xy"]), ref_frac=frac), p.ref_year, "race"
        else:
            rows, year, label = brake_rows_race(oc, p.season, ck, rot, tuple(zone["xy"]), "Practice 2", 5, frac), p.season, "FP2"
        if len(rows) < 8:
            return None
        braker(p, rows, zone, video, year, label)
        good = [r for r in rows if r.get("n", 0) >= 10 and r["err"] <= 10] or rows
        lead = good[0]
        cap = _cap(p, f"🛑 Who brakes latest {NICK.get(p.title, 'into the fastest braking zone')}? {year} {label}, every green lap.",
                   f"🥇 {drv(lead['code'], p.colors)} leads: brakes {lead['m']:.0f} m before the slowest point of the corner (±{lead['err']:.0f} m).",
                   "ℹ️ Median of each driver's green laps; the ± is the standard error. Telemetry: OpenF1.",
                   "💬 Who did you expect at the top? Tell us below.")
    elif kind in ("guess", "guess_fp2"):
        if kind == "guess":
            lap = lap_of(oc, p.season - 2, ck, "Race", rot)
            what = f"fastest lap of the {lap['year']} race here"
        else:
            try:
                lap = lap_of(oc, p.season, ck, "Practice 2", rot)
            except Exception:
                return None
            what = f"fastest lap of FP2, {name} {p.season}"
        guess(p, lap, video, what)
        cap = _cap(p, f"🕵️ Who is it? The {what}.", "👀 One speed trace, no names. Watch to the end for the answer.",
                   "💬 Comment your guess before the reveal!", "ℹ️ Lap time: official timing. Telemetry: OpenF1.")
    elif kind == "teammates":
        from . import news
        st = news.standings(p.season)
        rows = season_quali(p.season, st["after_round"])
        cols = _colors_now(oc, p.season, p.colors)
        teammates(p, rows, st["after_round"], video, cols, [t["name"] for t in st["teams"]])
        cap = _cap(p, f"⚔️ Teammate wars: {p.season} qualifying head to head, after round {st['after_round']}.",
                   "📊 Final qualifying classification each round, the rounds both drivers took part in.",
                   "💬 Which duel surprises you most? Tell us below.")
    elif kind == "points":
        from . import news
        st = news.standings(p.season)
        pts = season_points(p.season, st["after_round"])
        codes = [r["code"] for r in st["drivers"][1:5]]
        pointsrace(p, pts, codes, _colors_now(oc, p.season, p.colors), video)
        a, b = st["drivers"][1], st["drivers"][2]
        cap = _cap(p, f"📈 The fight for P2 in {p.season}, round by round.",
                   f"{drv(a['code'], p.colors)} {a['pts']:.0f} pts\n{drv(b['code'], p.colors)} {b['pts']:.0f} pts",
                   f"ℹ️ Official standings after round {st['after_round']}.", "💬 Who finishes second? Tell us below.")
    elif kind in ("ghost", "pedal_pole"):
        laps = _dry_poles(p, oc, ck, rot)
        if kind == "ghost":
            if len(laps) < 2:
                return None
            a, b = sorted(laps[:2], key=lambda l: l["year"])
            ghost(p, a, b, video, ["Two poles,", "one Strip" if p.title == "LAS VEGAS" else "one track"])
            fast = a if a["lap_s"] < b["lap_s"] else b
            cap = _cap(p, f"👻 Two {name} poles on one map: {drv(a['code'], p.colors)} {a['year']} {a['official']} vs {drv(b['code'], p.colors)} {b['year']} {b['official']}.",
                       f"⏱️ {fast['code']} {fast['year']} quicker by {abs(a['lap_s'] - b['lap_s']):.3f} s (official pole times).",
                       "💬 Which year would you take? Tell us below.")
        else:
            if not laps:
                return None
            lap = laps[0]
            pedal(p, lap, video, ["Inside the", f"{lap['year']} pole lap"], f"{lap['code']}, {lap['year']} qualifying, {lap['official']}")
            cap = _cap(p, f"🎥 Inside the {lap['year']} {name} pole lap: {drv(lap['code'], p.colors)}, {lap['official']}.",
                       "👀 Throttle, brake, gear and speed on the map, shown faster than real time.",
                       "💾 Save it.\n💬 Where is the lap won? Tell us below.")
    elif kind == "pedal_q":
        from .live import _q_results
        res = _q_results(p)
        pole = res[0] if res else None
        try:
            ms = None
            if pole:
                t = pole["q3"] or pole["q2"] or pole["q1"]
                m_, _, sec = t.rpartition(":")
                ms = (int(m_ or 0) * 60 + float(sec)) * 1000
            lap = lap_of(oc, p.season, ck, "Qualifying", rot, pole["code"] if pole else None, ms)
        except Exception:
            return None
        official = (pole["q3"] or pole["q2"]) if pole else _clock(lap["lap_s"])
        pedal(p, lap, video, ["Inside the", "pole lap"], f"{lap['code']}, {name} {p.season}, {official}")
        cap = _cap(p, f"🎥 Inside the {name} pole lap: {drv(lap['code'], p.colors)}, {official}.",
                   "👀 Every input on the lap, live on the map, shown faster than real time.",
                   "💾 Save it.\n💬 Who beats it in the race? Tell us below.")
    else:
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-1", "-i", str(video), "-frames:v", "1", str(out / "cover.jpg")], check=True)
    return video, cap
