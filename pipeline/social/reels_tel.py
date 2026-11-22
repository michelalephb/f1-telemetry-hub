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


def overtake_data(oc, year: int, ck: int, rot: float) -> dict:
    """On track passes of a race from OpenF1 (Michel, 21 Nov: a template for every race). OpenF1's overtakes are
    every position swap, pit stops and penalties included, and may be incomplete; we keep on track passes only:
    neither driver pitting on that lap or the one either side, no safety car, VSC or red flag laps, and no swap that
    the same pair reverses within 3 s (timing noise). Returns passes with lap and the share of that lap (time)."""
    sk = _session(oc, year, ck, "Race")
    codes, cols = _codes(oc, sk)
    ov = oc.get("overtakes", session_key=sk)
    laps = oc.frame("laps", session_key=sk)
    laps = laps[laps["date_start"].notna()].copy()
    laps["t0"] = pd.to_datetime(laps["date_start"], utc=True, format="ISO8601")
    laps["dur"] = laps["lap_duration"].fillna(laps["lap_duration"].median())
    pits = oc.get("pit", session_key=sk)
    pit_laps = {}
    for r in pits:
        pit_laps.setdefault(int(r["driver_number"]), set()).add(int(r["lap_number"]))
    rc = oc.get("race_control", session_key=sk)
    neutral, on = set(), None
    for r in sorted(rc, key=lambda r: r["date"]):
        msg, ln = (r.get("message") or "").upper(), r.get("lap_number")
        if ln is None:
            continue
        if "SAFETY CAR DEPLOYED" in msg or "RED FLAG" in msg:
            on = int(ln)
        elif on is not None and ("IN THIS LAP" in msg or "ENDING" in msg or "GREEN" in msg or "RESUME" in msg):
            neutral.update(range(on, int(ln) + 2))
            on = None
    n_laps = int(laps["lap_number"].max())
    raw, keep = len(ov), []
    evs = sorted(ov, key=lambda r: r["date"])
    for k, r in enumerate(evs):
        a, b = int(r["overtaking_driver_number"]), int(r["overtaken_driver_number"])
        t = pd.Timestamp(r["date"]).tz_convert("UTC") if pd.Timestamp(r["date"]).tzinfo else pd.Timestamp(r["date"], tz="UTC")
        g = laps[(laps["driver_number"] == a) & (laps["t0"] <= t)]
        if g.empty:
            continue
        L = g.sort_values("t0").iloc[-1]
        lap = int(L["lap_number"])
        frac = float(min(max((t - L["t0"]).total_seconds() / float(L["dur"]), 0.0), 0.999))
        if lap in neutral:
            continue
        if any(lap + d in pit_laps.get(n, set()) for n in (a, b) for d in (-1, 0, 1)):
            continue
        rev = any(int(s["overtaking_driver_number"]) == b and int(s["overtaken_driver_number"]) == a
                  and abs((pd.Timestamp(s["date"]) - pd.Timestamp(r["date"])).total_seconds()) < 3 for s in evs[max(0, k - 6):k + 7])
        if rev:
            continue
        keep.append({"lap": lap, "tfrac": frac, "who": codes.get(a), "whom": codes.get(b)})
    return {"passes": [q for q in keep if q["who"] and q["whom"]], "raw": raw, "laps": n_laps, "colors": cols,
            "neutral": sorted(neutral)}


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


def season_points_teams(season: int, upto: int) -> list[dict]:
    from .. import jolpica
    out = []
    for rnd in range(1, upto + 1):
        cs = jolpica._get(f"{season}/{rnd}/constructorStandings.json?limit=12")["StandingsTable"]["StandingsLists"]
        if not cs:
            continue
        out.append({"round": rnd, "pts": {x["Constructor"]["name"]: float(x["points"]) for x in cs[0]["ConstructorStandings"]}})
    return out


def season_race_h2h(season: int, upto: int) -> list[dict]:
    """Race classification per round (finishing order, retirements count as behind), for teammate race duels."""
    from .. import jolpica
    rows = []
    for rnd in range(1, upto + 1):
        rr = jolpica._get(f"{season}/{rnd}/results.json?limit=100")["RaceTable"]["Races"]
        if not rr:
            continue
        for x in rr[0]["Results"]:
            rows.append({"round": rnd, "code": x["Driver"].get("code"), "team": x["Constructor"]["name"], "pos": int(x["position"])})
    return rows


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


def teammates(p, rows: list[dict], after_round: int, out: Path, colors: dict, order: list[str] | None = None,
              what: str = "qualifying") -> Path:
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
    _hook(c, ["Teammate wars", f"{p.season} {what}"], f"head to head, after round {after_round}")
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
    _foot(c, f"Final {what} classification each round (Jolpica, official)")
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


def pointsrace(p, points: list[dict], codes: list[str], colors: dict, out: Path, teams: bool = False) -> Path:
    P.set_event(p)
    c = _card(p)
    _hook(c, ["The fight for P2", "round by round"],
          f"{p.season} {'constructors' if teams else 'drivers'} championship, after round {points[-1]['round']}")
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
    short = (lambda q: q.replace(" F1 Team", "").replace(" Racing", "")) if teams else (lambda q: q)
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
            tags[cd].set_text(f"{short(cd)} {ends[cd][1]:.0f}")
        r.add(c.fig)
    last = {cd: series[cd][-1] for cd in codes}
    order = sorted(codes, key=lambda cd: -last[cd])
    gap.set_text(f"{short(order[0])} leads {short(order[1])} by {last[order[0]] - last[order[1]]:.0f}, "
                 f"{short(order[2])} {last[order[1]] - last[order[2]]:.0f} further back")
    r.add(c.fig, int(3.5 * FPS))
    plt.close(c.fig)
    return r.close()


def ghost(p, a: dict, b: dict, out: Path, hook: list[str], sub: str | None = None, foot: str | None = None) -> Path:
    """Two laps replayed on one map. The verdict uses the official lap times only."""
    P.set_event(p)
    A = {k: np.array(v, float) if isinstance(v, list) else v for k, v in a.items()}
    B = {k: np.array(v, float) if isinstance(v, list) else v for k, v in b.items()}
    c = _card(p)
    _hook(c, hook, sub or f"{A['code']} {A['year']} vs {B['code']} {B['year']}, official pole times")
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
    _foot(c, foot or "Lap times: official classification (Jolpica). Positions: OpenF1 telemetry")
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



# ---------------------------------------------------------------- new animated formats (Michel, 20 Nov: fewer look alike
# ghost laps; simple, mesmerizing loops from the telemetry)

SPEED_CMAP = ["#1E3A8A", "#2563EB", "#00E5FF", "#10B981", "#F5C542", "#FF3D8B"]   # slow to fast


def _speed_colors(v: np.ndarray, lo: float = 60.0, hi: float = 345.0) -> np.ndarray:
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list("spd", SPEED_CMAP)
    return cm(np.clip((v - lo) / (hi - lo), 0, 1))


def _fine(L: dict, n: int = 1400) -> dict:
    """Resample a lap on an even time grid so the head moves smoothly between 240 ms car samples."""
    t = np.linspace(0, L["t"][-1], n)
    return {k: np.interp(t, L["t"], L[k]) for k in ("x", "y", "speed", "dist")} | {"t": t}


def speed_ribbon(p, lap: dict, out: Path, hook: list[str], sub: str, src: str = SRC_TEL, target_s: float = 12.0) -> Path:
    """The track draws itself as one glowing ribbon coloured by speed. One number moves: the speed.
    Ends on the full ribbon with the top and lowest speed pinned where they happen."""
    from matplotlib.collections import LineCollection
    P.set_event(p)
    L = {k: np.array(v, float) if isinstance(v, list) else v for k, v in lap.items()}
    F = _fine(L)
    c = _card(p)
    _hook(c, hook, sub)
    ax = _track(c, [0.06, 0.30, 0.88, 0.40], L["x"], L["y"], lw=10)
    pts = np.column_stack([F["x"], F["y"]])
    seg = np.stack([pts[:-1], pts[1:]], axis=1)
    col = _speed_colors((F["speed"][:-1] + F["speed"][1:]) / 2)
    glow = LineCollection([], linewidths=22, colors=[], alpha=0.18, capstyle="round", zorder=2)
    core = LineCollection([], linewidths=8, colors=[], capstyle="round", zorder=3)
    ax.add_collection(glow), ax.add_collection(core)
    head, = ax.plot([], [], "o", ms=20, color=P.TEXT, mec=P.EV, mew=4, zorder=5)
    spd = c.text(0.5, 0.262, "", 96, weight=200)
    unit = c.text(0.5, 0.218, "KM/H", 14, color=P.MUTED, weight=600, track=True)
    clock = c.text(0.5, 0.195, "", 22, color=P.MUTED, weight=300)
    _foot(c, src)
    r = Reel(out)
    n = int(target_s * FPS)
    for i in range(n + 1):
        j = max(1, int(round((len(seg)) * i / n)))
        glow.set_segments(seg[:j]), glow.set_color(col[:j])
        core.set_segments(seg[:j]), core.set_color(col[:j])
        k = min(j, len(F["t"]) - 1)
        head.set_data([F["x"][k]], [F["y"][k]])
        head.set_markeredgecolor(col[min(k, len(col) - 1)])
        spd.set_text(f"{F['speed'][k]:.0f}")
        spd.set_color(col[min(k, len(col) - 1)])
        clock.set_text(_clock(min(L["lap_s"], F["t"][k])))
        r.add(c.fig)
    head.set_data([], [])
    hi, lo = int(np.argmax(L["speed"])), int(np.argmin(L["speed"][5:-5])) + 5
    for q, lbl in ((hi, "TOP"), (lo, "LOWEST")):
        ax.plot([L["x"][q]], [L["y"][q]], "o", ms=14, color=P.TEXT, zorder=6)
        ax.annotate(f"{lbl} {L['speed'][q]:.0f}", (L["x"][q], L["y"][q]), xytext=(0, 26), textcoords="offset points",
                    ha="center", fontsize=17, color=P.TEXT, family=P.FONT, weight=600, zorder=7)
    spd.set_text(L.get("official") or _clock(L["lap_s"]))
    spd.set_color(P.GOLD)
    unit.set_text("")
    clock.set_text(f"{L['code']}  {L.get('label', '')}".strip())
    r.add(c.fig, int(3.0 * FPS))
    plt.close(c.fig)
    return r.close()


def delta_map(p, a: dict, b: dict, out: Path, hook: list[str] | None, sub: str, official: tuple[float, float],
              n_sec: int = 25, src: str = "Lap times: official timing. Mini sectors: OpenF1 telemetry") -> Path:
    """Two laps, one map, no dots racing: a single runner paints each of n_sec mini sectors in the colour of the
    driver who was quicker there. The gap counter runs underneath; it ends on the official gap and the tally."""
    from matplotlib.collections import LineCollection
    P.set_event(p)
    A = {k: np.array(v, float) if isinstance(v, list) else v for k, v in a.items()}
    B = {k: np.array(v, float) if isinstance(v, list) else v for k, v in b.items()}
    ca, cb = A.get("color") or P.CYAN, B.get("color") or P.GOLD
    if ca.lower() == cb.lower():
        cb = P.GOLD
    # both laps on A's racing line (windowed nearest point projection, as in q_board), 1200 points
    tf = np.linspace(0, A["t"][-1], 2000)
    rx_f, ry_f = np.interp(tf, A["t"], A["x"]), np.interp(tf, A["t"], A["y"])
    grid = np.linspace(0, 1, 1200)
    TT = []
    for L in (A, B):
        s_, Ltot = _along(rx_f, ry_f, L["x"], L["y"], L["t"] / L["t"][-1])
        u, keep = np.unique(s_, return_index=True)
        TT.append(np.interp(grid * Ltot, u, L["t"][keep]))
    from numpy.lib.stride_tricks import sliding_window_view
    g = TT[1] - TT[0]
    g = np.median(sliding_window_view(np.pad(g, 60, mode="edge"), 121), axis=1)
    g = np.convolve(np.pad(g, 10, mode="edge"), np.ones(21) / 21, mode="valid")
    s0 = int(0.04 * len(g))
    g[:s0] = np.linspace(0, g[s0], s0)
    g = g + ((official[1] - official[0]) - g[-1]) * np.clip((grid - 0.9) / 0.1, 0, 1)
    gap = g                                                                 # > 0: A ahead
    fin = np.linspace(0, len(rx_f) - 1, len(grid)).astype(int)
    x, y = rx_f[fin], ry_f[fin]
    d = grid
    edges = np.linspace(0, len(d) - 1, n_sec + 1).astype(int)
    win = [ca if gap[e1] - gap[e0] > 0 else cb for e0, e1 in zip(edges[:-1], edges[1:])]
    pts = np.column_stack([x, y])
    seg = np.stack([pts[:-1], pts[1:]], axis=1)
    segcol = np.empty(len(seg), dtype=object)
    for k, (e0, e1) in enumerate(zip(edges[:-1], edges[1:])):
        segcol[e0:e1] = win[k]
    if hook is None:                                       # anticipation (Michel, 21 Nov): the biggest lead, then the question
        k = int(np.argmax(np.abs(gap[: int(0.9 * len(gap))])))
        who = A["code"] if gap[k] >= 0 else B["code"]
        hook = [f"{who} {abs(gap[k]):.2f} s up", "Can he hold it?"]
    c = _card(p)
    _hook(c, hook, sub)
    ax = _track(c, [0.06, 0.33, 0.88, 0.37], A["x"], A["y"], lw=10)
    core = LineCollection([], linewidths=10, colors=[], capstyle="butt", zorder=3)
    ax.add_collection(core)
    head, = ax.plot([], [], "o", ms=16, color=P.TEXT, zorder=5)
    # each driver's own lap clock at this point of the lap (Michel, 21 Nov: the timers are the lap times; the track
    # highlight alone shows who is quicker where, no mini sector counter)
    c.text(0.30, 0.315, A["code"], 30, color=ca, weight=600)
    c.text(0.70, 0.315, B["code"], 30, color=cb, weight=600)
    na, nb = c.text(0.30, 0.272, "", 44, weight=200), c.text(0.70, 0.272, "", 44, weight=200)
    lead = c.text(0.5, 0.215, "", 30, weight=300)
    clk_a = TT[0] * official[0] / TT[0][-1]
    _foot(c, src)
    r = Reel(out)
    n = int(12 * FPS)
    for i in range(n + 1):
        j = max(1, int(round(len(seg) * i / n)))
        core.set_segments(seg[:j]), core.set_color(list(segcol[:j]))
        head.set_data([x[min(j, len(x) - 1)]], [y[min(j, len(y) - 1)]])
        q = min(j, len(gap) - 1)
        na.set_text(_clock(clk_a[q]))
        nb.set_text(_clock(clk_a[q] + gap[q]))
        r.add(c.fig)
    head.set_data([], [])
    g = official[1] - official[0]
    na.set_text(_clock(official[0])), nb.set_text(_clock(official[1]))
    (na if g >= 0 else nb).set_color(P.GOLD)
    lead.set_text(f"{A['code'] if g >= 0 else B['code']} by {abs(g):.3f} s, official")
    lead.set_color(P.GOLD)
    r.add(c.fig, int(3.0 * FPS))
    plt.close(c.fig)
    return r.close()


def _lap_stats(L: dict) -> dict:
    """Share of lap time at full throttle (98% or more) and on the brake, and the top speed (OpenF1 car data)."""
    dt = np.diff(L["t"], append=L["t"][-1])
    tot = max(float(dt.sum()), 1e-6)
    return {"full": float(dt[L["throttle"] >= 98].sum() / tot * 100), "brake": float(dt[L["brake"] > 0].sum() / tot * 100),
            "top": float(L["speed"].max())}


def _along(ref_x, ref_y, x, y, frac=None, win: float = 0.08) -> tuple[np.ndarray, float]:
    """Distance along the reference racing line of each point, by nearest point projection inside a window around
    where the car should be (its share of lap time), so parts of the circuit that run close to each other cannot
    capture it. Robust to the drift of speed integrated distance between cars. Monotonic."""
    s_ref = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(ref_x), np.diff(ref_y)))])
    N, L = len(ref_x), s_ref[-1]
    frac = np.linspace(0, 1, len(x)) if frac is None else frac
    out = np.empty(len(x))
    w = int(win * N)
    for q in range(len(x)):
        c0 = int(frac[q] * (N - 1))
        a, b = max(0, c0 - w), min(N, c0 + w + 1)
        out[q] = s_ref[a + int(np.argmin((ref_x[a:b] - x[q]) ** 2 + (ref_y[a:b] - y[q]) ** 2))]
    out[0] = 0.0
    out[-1] = L
    return np.maximum.accumulate(out), L


def q_board(p, laps: list[dict], official: list[float], out: Path, hook: list[str], sub: str,
            src: str = "Lap times: official timing. Throttle, brake, speed, mini sectors: OpenF1 telemetry", n_sec: int = 25) -> Path:
    """Top laps of a session on one board (Michel's favourite format, 20 Nov). The gap to the fastest lap draws
    itself across the lap, the map paints each mini sector in the colour of the quickest driver through it, and each
    driver's row fills in: full throttle share, braking share, top speed. Laps are aligned on the fastest lap's line
    (nearest point projection), so the gap is real, and the board ends on the official gaps."""
    P.set_event(p)
    Ls = [{k: np.array(v, float) if isinstance(v, list) else v for k, v in l.items()} for l in laps]
    used, cols = set(), []
    for L in Ls:                                                  # teammates share a colour: second one goes white
        cc = (L.get("color") or P.CYAN).lower()
        cols.append(P.TEXT if cc in used else cc)
        used.add(cc)
    ref = Ls[0]
    tf = np.linspace(0, ref["t"][-1], 2000)                       # reference line, finely resampled
    rx_f, ry_f = np.interp(tf, ref["t"], ref["x"]), np.interp(tf, ref["t"], ref["y"])
    grid = np.linspace(0, 1, 900)
    T = []
    for L in Ls:                                                  # time at each point of the fastest lap's line
        s_, Ltot = _along(rx_f, ry_f, L["x"], L["y"], L["t"] / L["t"][-1])
        u, keep = np.unique(s_, return_index=True)
        T.append(np.interp(grid * Ltot, u, L["t"][keep]))
    from numpy.lib.stride_tricks import sliding_window_view
    gaps = []
    for t in T:
        g = t - T[0]
        # median over 10% of the lap removes short location glitches (one car's position stream can lag its car
        # data for a few seconds), then a light mean smooths the 240 ms sampling
        g = np.median(sliding_window_view(np.pad(g, 45, mode="edge"), 91), axis=1)
        g = np.convolve(np.pad(g, 7, mode="edge"), np.ones(15) / 15, mode="valid")
        s0 = int(0.04 * len(g))                                   # lap start: timing offsets, not driving
        g[:s0] = np.linspace(0, g[s0], s0)
        g[-1] = 0.0
        gaps.append(g)
    for k in range(1, len(gaps)):                                 # finish on the official gap
        gaps[k] = gaps[k] + (official[k] - official[0] - gaps[k][-2]) * np.clip((grid - 0.9) / 0.1, 0, 1)
        gaps[k][-1] = official[k] - official[0]
    hi = max(0.1, max(float(g.max()) for g in gaps)) * 1.18
    lo = min(-0.05, min(float(g.min()) for g in gaps)) * 1.25
    fin = np.linspace(0, len(rx_f) - 1, len(grid)).astype(int)
    rx, ry = rx_f[fin], ry_f[fin]
    c = _card(p)
    _hook(c, hook, sub, y0=0.83)
    # map, one stroke per mini sector in the quickest driver's colour
    mp = _track(c, [0.14, 0.60, 0.72, 0.125], ref["x"], ref["y"], lw=11)
    edges = np.linspace(0, len(grid) - 1, n_sec + 1).astype(int)
    best = [int(np.argmin([t[e1] - t[e0] for t in T])) for e0, e1 in zip(edges[:-1], edges[1:])]
    strokes = [mp.plot([], [], color=cols[b], lw=9, solid_capstyle="round", zorder=3)[0] for b in best]
    dot, = mp.plot([], [], "o", ms=14, color=P.TEXT, mec=P.EV, mew=3, zorder=5)
    c.text(0.5, 0.588, f"MAP: QUICKEST THROUGH EACH OF {n_sec} MINI SECTORS", 11, color=P.MUTED, weight=600, track=True)
    # gap chart
    c.text(0.08, 0.555, f"GAP TO {Ls[0]['code']} ACROSS THE LAP, SECONDS  (UP = AHEAD)", 12, color=P.MUTED, weight=600, ha="left", track=True)
    ax = c.fig.add_axes([0.08, 0.375, 0.76, 0.17])
    ax.set_xlim(0, 1), ax.set_ylim(hi, lo)                        # behind = down
    ax.axis("off")
    step = 0.1 if hi < 0.6 else 0.25 if hi < 1.5 else 0.5
    for gl in np.arange(step, hi, step):
        ax.axhline(gl, color="#1A2130", lw=1, zorder=0)
    ax.axhline(0, color=cols[0], lw=3, alpha=0.9, zorder=1)
    lines = [ax.plot([], [], color=cc, lw=3.5, solid_capstyle="round", zorder=2)[0] for cc in cols[1:]]
    tags = [c.text(0.86, 0.5, "", 16, color=cc, weight=600, ha="left") for cc in cols]
    tags[0].set_text(Ls[0]["code"])

    def _tag_y(vals):                                             # data -> figure y, then push apart (min 0.016)
        ys = [0.375 + 0.17 * (hi - v) / (hi - lo) for v in vals]
        order = sorted(range(len(ys)), key=lambda q: -ys[q])
        for a, b in zip(order, order[1:]):
            if ys[a] - ys[b] < 0.016:
                ys[b] = ys[a] - 0.016
        return ys
    st = [_lap_stats(L) for L in Ls]
    rows = []
    y0 = 0.335
    for h, xh in (("LAP", 0.25), ("FULL THROTTLE", 0.47), ("BRAKING", 0.67), ("TOP KM/H", 0.86)):
        c.text(xh, y0, h, 11, color=P.MUTED, weight=600, track=True)
    for k, (L, cc) in enumerate(zip(Ls, cols)):
        y = y0 - 0.032 - k * 0.033
        c.text(0.10, y, L["code"], 24, color=cc, weight=600, ha="left")
        g = official[k] - official[0]
        c.text(0.25, y, _clock(official[k]) if k == 0 else f"+{g:.3f}", 20, weight=300)
        rows.append([c.text(x_, y, "", 20, weight=300) for x_ in (0.47, 0.67, 0.86)])
    _foot(c, src)
    r = Reel(out)
    n = int(13 * FPS)
    for i in range(n + 1):
        j = max(2, int(len(grid) * i / n))
        for ln, g in zip(lines, gaps[1:]):
            ln.set_data(grid[:j], g[:j])
        ys = _tag_y([0.0] + [g[j - 1] for g in gaps[1:]])
        for k, tg in enumerate(tags):
            tg.set_y(ys[k])
            if k:
                tg.set_text(f"{L_code(Ls, k)} {gaps[k][j - 1]:+.2f}")
        for q, (e0, e1) in enumerate(zip(edges[:-1], edges[1:])):
            hi_ = min(j, e1 + 1)
            strokes[q].set_data(rx[e0:hi_], ry[e0:hi_]) if hi_ > e0 + 1 else strokes[q].set_data([], [])
        dot.set_data([rx[j - 1]], [ry[j - 1]])
        for k, L in enumerate(Ls):                                # stats so far on this lap
            m = L["t"] <= T[k][j - 1]
            if m.sum() > 2:
                s_ = _lap_stats({kk: L[kk][m] for kk in ("t", "throttle", "brake", "speed")})
                for tx, v in zip(rows[k], (f"{s_['full']:.0f}%", f"{s_['brake']:.0f}%", f"{s_['top']:.0f}")):
                    tx.set_text(v)
        r.add(c.fig)
    dot.set_data([], [])
    ys = _tag_y([0.0] + [official[k] - official[0] for k in range(1, len(Ls))])
    for k, tg in enumerate(tags):
        tg.set_y(ys[k])
        if k:
            tg.set_text(f"{L_code(Ls, k)} +{official[k] - official[0]:.3f}")
    for k in range(len(Ls)):
        for tx, v in zip(rows[k], (f"{st[k]['full']:.1f}%", f"{st[k]['brake']:.1f}%", f"{st[k]['top']:.0f}")):
            tx.set_text(v)
    r.add(c.fig, int(3.5 * FPS))
    plt.close(c.fig)
    return r.close()


def strength_data(laps: list[dict], skip: tuple[float, float] = (2.0, 2.0)) -> dict:
    """Where each car is strong, from each car's own car data clock only (no cross car position matching, whose
    per car latency can reach 0.5 s). Corners: speed minima under 150 km/h after a braking zone, one per 4% of the
    lap, matched within 1.2% of the lap; corner complexes with two minima (skip window) are left out because cars
    bottom out at different points there. Apex time and speed by a parabola through 3 samples, brake onset between
    samples. Returns per driver: segment times between corners, apex speeds, brake onset metres before the apex,
    top speed; plus corner lap fractions on the reference (first) lap."""
    Ls = [{k: np.array(v, float) if isinstance(v, list) else v for k, v in l.items()} for l in laps]
    ref = Ls[0]
    fr = lambda L, i: L["dist"][i] / L["dist"][-1]
    v = ref["speed"]
    mins = [i for i in range(2, len(v) - 2) if v[i] <= v[i - 1] and v[i] <= v[i + 1] and v[i] < 150
            and not skip[0] < fr(ref, i) < skip[1]]
    keep = []
    for i in sorted(mins, key=lambda i: v[i]):
        if all(abs(fr(ref, i) - fr(ref, j)) > 0.04 for j in keep):
            keep.append(i)
    keep = sorted(keep, key=lambda i: fr(ref, i))
    # complexes after the skip window that are still ambiguous: keep only corners whose minimum is unique
    fa = [fr(ref, i) for i in keep]

    def vmin(L, i):
        t, sp = L["t"][i - 1:i + 2], L["speed"][i - 1:i + 2]
        a, b, c = np.polyfit(t, sp, 2)
        tm = float(np.clip(-b / (2 * a), t[0], t[-1])) if a > 0 else float(L["t"][i])
        return tm, float(np.polyval([a, b, c], tm)), float(np.interp(tm, L["t"], L["dist"]))
    out = {}
    for L in Ls:
        f = L["dist"] / L["dist"][-1]
        idx = []
        for x in fa:
            w = np.where(np.abs(f - x) < 0.012)[0]
            idx.append(int(w[np.argmin(L["speed"][w])]))
        ap = [vmin(L, i) for i in idx]
        brk = []
        for i, (_, _, dm) in zip(idx, ap):
            j = i
            while j > 1 and not (L["brake"][j] > 0 and L["brake"][j - 1] == 0):
                j -= 1
            brk.append(dm - (L["dist"][j] + L["dist"][j - 1]) / 2)
        t = [0.0] + [a[0] for a in ap] + [float(L["lap_s"])]
        out[L["code"]] = {"seg": np.diff(t).tolist(), "apex": [a[1] for a in ap], "brk": brk, "top": float(L["speed"].max())}
    # clean corners: no other minimum under 150 km/h within 3% of the lap at a similar speed (complexes such as
    # Las Vegas T7 to T9 and T14 to T16, where cars bottom out at different points)
    allmins = [i for i in range(2, len(v) - 2) if v[i] <= v[i - 1] and v[i] <= v[i + 1] and v[i] < 150]
    clean = [k for k, i in enumerate(keep)
             if not any(j != i and abs(fr(ref, j) - fr(ref, i)) < 0.03 and abs(v[j] - v[i]) < 12 for j in allmins)]
    return {"fa": fa, "out": out, "codes": [L["code"] for L in Ls], "clean": clean}


# turn names of the corner minima strength_data finds, keyed by (GP title, number of minima found)
CORNER_NAMES = {("LAS VEGAS", 5): ["T1", "T5", "T7", "T12", "T14"]}


STRENGTH_HOOKS = {"strengths_q_ant_rus_lec_ham": ["Ferrari: 346 km/h.", "Still 0.7 s down on the Strip"]}
STRENGTH_ROWS = {"strengths_q_ant_rus_lec_ham": ("strip", "top", "apex")}
Q_EXTRA_SESSION = {("LAS VEGAS", 2026): {"LEC": "Q1", "HAM": "Q2"}}   # which part of qualifying Q_EXTRA's laps came from


def strength_caption(p, D: dict, cn: list[str], what: str | None = None, strip: bool = False,
                     sessions: dict | None = None) -> list[str]:
    """Caption blocks built from the same numbers as the Reel."""
    from .captions import drv
    O, codes, ck = D["out"], D["codes"], D["clean"]
    top = sorted(codes, key=lambda c_: -O[c_]["top"])
    apex = {c_: float(np.mean([O[c_]["apex"][k] for k in ck])) for c_ in codes}
    brk = {c_: float(np.mean([O[c_]["brk"][k] for k in ck])) for c_ in codes}
    fastc, latest, early = max(apex, key=apex.get), min(brk, key=brk.get), max(brk, key=brk.get)
    where = ", ".join(cn[k] for k in ck)
    extra = []
    if strip:
        last = [0.0] + D["fa"]
        cut = D["fa"][ck[-1]]
        st = {c_: sum(s_ for s_, lo in zip(O[c_]["seg"], last) if lo >= cut - 1e-9) for c_ in codes}
        b_ = min(st, key=st.get)
        extra.append(f"⏱️ {cn[ck[-1]]} to the line: {drv(b_, p.colors)} quickest; " + ", ".join(
            f"{drv(c_, p.colors)} +{st[c_] - st[b_]:.2f} s" for c_ in sorted(codes, key=st.get) if c_ != b_) + ".")
    if sessions:
        extra.append("🕒 Best laps from different parts of qualifying (" + ", ".join(f"{c_} {s_}" for c_, s_ in sessions.items())
                     + "): the track gets quicker through a session, so part of the gap is track, not car.")
    return [f"🧭 Where each car is strong, {p.title.title()} " + (f"qualifying, {what}:" if what else f"Q3, the top {len(codes)} laps:"),
            *extra,
            "🚀 Straight line: " + ", ".join(f"{drv(c_, p.colors)} {O[c_]['top']:.0f}" for c_ in top) + " km/h top speed.",
            f"🌀 Slow corners ({where}): {drv(fastc, p.colors)} carries {apex[fastc]:.0f} km/h on average at the apex, "
            f"{drv(codes[0], p.colors)} {apex[codes[0]]:.0f}.",
            f"🛑 Braking: {drv(latest, p.colors)} starts braking {brk[latest]:.0f} m before the apex, {drv(early, p.colors)} {brk[early]:.0f} m. "
            "Arrive faster, brake earlier.",
            "📐 Telemetry: OpenF1, each car on its own clock. Corner complexes left out where cars bottom out at different points.",
            "💬 Straight line speed or corners: which wins the race? Tell us below."]


def strengths(p, laps: list[dict], official: list[float], out: Path, hook: list[str], sub: str, corners: list[str],
              keep_corners: list[int] | None = None, rows_spec: tuple = ("top", "apex", "brake"), src: str = "Speeds, braking: OpenF1 telemetry. Section times: each car's own clock") -> Path:
    """Where each car is strong, displayed simply: the lap splits into sections between the clean corners, each
    painted in the colour of the quickest car there, with its margin over the next car underneath; then three rows
    fill in (straight line, slow corners, braking), best in gold."""
    P.set_event(p)
    D = strength_data(laps)
    Ls = [{k: np.array(v, float) if isinstance(v, list) else v for k, v in l.items()} for l in laps]
    used, cols = set(), {}
    for L in Ls:                                                  # team mate: a lighter shade of the team colour
        cc = (L.get("color") or P.CYAN).lower()
        if cc in used:
            rgb = [int(cc[k:k + 2], 16) for k in (1, 3, 5)]
            cc = "#" + "".join(f"{int(v + (255 - v) * 0.55):02x}" for v in rgb)
        cols[L["code"]] = cc
        used.add((L.get("color") or P.CYAN).lower())
    O, codes = D["out"], D["codes"]
    keep_corners = D["clean"] if keep_corners is None else keep_corners
    # sections between the kept corners only (merge across dropped ones)
    bounds = [0.0] + [D["fa"][k] for k in keep_corners] + [1.0]
    secs = []
    for a_, b_ in zip(bounds[:-1], bounds[1:]):
        tt = {c: sum(s for s, lo in zip(O[c]["seg"], [0.0] + D["fa"]) if a_ - 1e-9 <= lo < b_ - 1e-9) for c in codes}
        best = min(tt, key=tt.get)
        second = sorted(tt.values())[1]
        secs.append((a_, b_, best, second - tt[best]))
    ref = Ls[0]
    fr = ref["dist"] / ref["dist"][-1]
    c = _card(p)
    _hook(c, hook, sub, y0=0.83)
    mp = _track(c, [0.16, 0.605, 0.68, 0.13], ref["x"], ref["y"], lw=11)
    strokes = []
    for a_, b_, best, mg in secs:
        strokes.append(mp.plot([], [], color=cols[best], lw=10, solid_capstyle="round", zorder=3)[0])
    names = ["START"] + [corners[k] for k in keep_corners] + ["LINE"]
    chips = []
    w = 0.84 / len(secs)
    for k, (a_, b_, best, mg) in enumerate(secs):
        x = 0.08 + w * (k + 0.5)
        c.text(x, 0.585, f"{names[k]} TO {names[k + 1]}", 11, color=P.MUTED, weight=600, track=True)
        chips.append(c.text(x, 0.563, "", 17, color=cols[best], weight=700))
    ck = list(keep_corners)
    last = [0.0] + D["fa"]
    k_last = D["fa"].index(D["fa"][ck[-1]])
    strip = {cc: sum(s_ for s_, lo in zip(O[cc]["seg"], last) if lo >= D["fa"][ck[-1]] - 1e-9) for cc in codes}
    sbest = min(strip.values())
    lib = {"top": ("STRAIGHT LINE", "top speed, km/h", {cc: O[cc]["top"] for cc in codes}, "{:.0f}", True),
           "strip": (f"{corners[ck[-1]]} TO THE LINE", "time lost to the quickest here, seconds",
                     {cc: strip[cc] - sbest for cc in codes}, "+{:.2f}", False),
           "apex": ("SLOW CORNERS", "minimum speed at " + ", ".join(corners[k] for k in ck) + ", km/h",
                    {cc: float(np.mean([O[cc]["apex"][k] for k in ck])) for cc in codes}, "{:.0f}", True),
           "brake": ("BRAKING", "starts braking, metres before the apex (less = later)",
                     {cc: float(np.mean([O[cc]["brk"][k] for k in ck])) for cc in codes}, "{:.0f} m", False)}
    rows = [lib[r] for r in rows_spec]
    y = 0.525
    bars = []
    for title, subt, vals, fmt, hi_good in rows:
        c.text(0.08, y, title, 17, color=P.TEXT, weight=700, ha="left", track=True)
        c.text(0.08, y - 0.016, subt, 12, color=P.MUTED, weight=400, ha="left")
        best = (max if hi_good else min)(vals, key=vals.get)
        lo_, hi_ = min(vals.values()), max(vals.values())
        for k, cc in enumerate(codes):
            yy = y - 0.036 - k * 0.018
            c.text(0.08, yy, cc, 15, color=cols[cc], weight=700, ha="left")
            nrm = (vals[cc] - lo_) / (hi_ - lo_ + 1e-9) if hi_good else (hi_ - vals[cc]) / (hi_ - lo_ + 1e-9)
            frac = 0.55 + 0.45 * nrm
            r = plt.Rectangle((0.18, yy - 0.005), 0.0, 0.010, transform=c.fig.transFigure, fc=cols[cc], alpha=0.9)
            c.fig.add_artist(r)
            tx = c.text(0.90, yy, "", 15, color=P.GOLD if cc == best else P.TEXT, weight=700 if cc == best else 300, ha="right")
            bars.append((r, frac, tx, fmt.format(vals[cc]), len(bars) // len(codes)))
        y -= 0.036 + len(codes) * 0.018 + 0.016
    _foot(c, src)
    r_ = Reel(out)
    n1 = int(6 * FPS)
    for i in range(n1 + 1):                                       # sections paint one after another
        pos = i / n1
        for (a_, b_, best, mg), st, lb in zip(secs, strokes, chips):
            m = (fr >= a_) & (fr <= min(b_, max(a_, pos)))
            st.set_data(ref["x"][m], ref["y"][m])
            lb.set_text(f"{best} {mg:.2f} s" if pos >= b_ else "")
        r_.add(c.fig)
    for lb, (a_, b_, best, mg) in zip(chips, secs):
        lb.set_text(f"{best} {mg:.2f} s")
    n2 = int(4.5 * FPS)
    for i in range(n2 + 1):                                       # rows fill in, one after another
        for rect, frac, tx, val, row in bars:
            e = _ease((i / n2) * 3 - row)
            rect.set_width(0.60 * frac * e)
            tx.set_text(val if e >= 1 else "")
        r_.add(c.fig)
    r_.add(c.fig, int(4 * FPS))
    plt.close(c.fig)
    return r_.close()


def _spread(tags, top, gap_frac: float = 0.045):
    """Push line end labels apart vertically (data units) so they never overlap."""
    order = sorted(range(len(tags)), key=lambda q: tags[q].get_position()[1])
    min_d = top * gap_frac
    last = None
    for q in order:
        x, y = tags[q].get_position()
        if last is not None and y - last < min_d:
            y = last + min_d
            tags[q].set_position((x, y))
        last = y


def race_trace(p, rows: list[dict], laps: int, out: Path, hook: list[str], sub: str, final: dict[str, str],
               src: str = "Gaps: official lap timing. Pit stops: official timing", mark: str | None = None) -> Path:
    """The race in one chart (Michel, 21 Nov): each driver's gap to the leader draws itself lap by lap, pit stops
    pop as dots, a big lap counter ticks, and it ends on the official finishing gaps. rows: [{code, color,
    gaps: seconds behind the leader at the end of each lap (len laps), pits: [lap numbers]}], leader first."""
    P.set_event(p)
    used, cols = set(), []
    for r in rows:                                                # team mate: a lighter shade of the team colour
        cc = (r.get("color") or P.CYAN).lower()
        if cc in used:
            rgb = [int(cc[k:k + 2], 16) for k in (1, 3, 5)]
            cc = "#" + "".join(f"{int(v + (255 - v) * 0.55):02x}" for v in rgb)
        cols.append(cc)
        used.add((r.get("color") or P.CYAN).lower())
    G = [np.array(r["gaps"], float) for r in rows]
    racing = [np.delete(g, [pp - 1 for pp in r.get("pits", [])] + [pp for pp in r.get("pits", []) if pp < len(g)]) for r, g in zip(rows, G)]
    top = max(5.0, float(np.nanmax([g.max() for g in racing])) * 1.15)   # scale on racing gaps; pit dips run off the bottom
    c = _card(p)
    _hook(c, hook, sub, y0=0.83)
    if mark:
        c.text(0.5, 0.712, mark, 13, color=P.GOLD, weight=700, track=True)
    ax = c.fig.add_axes([0.10, 0.30, 0.72, 0.39])
    ax.set_xlim(1, laps), ax.set_ylim(top, -top * 0.04)          # leader on top, further back = lower
    ax.axis("off")
    for gl in np.arange(0, top, 5 if top < 40 else 10):
        ax.axhline(gl, color="#1A2130", lw=1, zorder=0)
        ax.text(0.6, gl, f"{gl:.0f}s" if gl else "LEADER", fontsize=11, color=P.MUTED, family=P.FONT, va="center", ha="right")
    lines = [ax.plot([], [], color=cc, lw=3.5, solid_capstyle="round", zorder=3)[0] for cc in cols]
    tags = [ax.text(0, 0, "", fontsize=15, color=cc, family=P.FONT, weight=700, va="center") for cc in cols]
    dots = [ax.plot([], [], "o", ms=9, color=cc, mec=P.BG if hasattr(P, "BG") else "#0B0E14", mew=2, zorder=4)[0] for cc in cols]
    lap_t = c.text(0.5, 0.255, "", 48, weight=200)
    c.text(0.5, 0.222, "LAP", 13, color=P.MUTED, weight=600, track=True)
    _foot(c, src)
    r_ = Reel(out)
    n = int(13 * FPS)
    for i in range(n + 1):
        x = 1 + (laps - 1) * i / n
        k = int(np.floor(x))
        for r, g, ln, tg, dt in zip(rows, G, lines, tags, dots):
            xs = np.arange(1, k + 1)
            ys = g[:k]
            if k < laps:                                          # smooth head between laps
                xs = np.append(xs, x)
                ys = np.append(ys, g[k - 1] + (g[k] - g[k - 1]) * (x - k))
            ln.set_data(xs, ys)
            tg.set_position((xs[-1] + laps * 0.012, min(ys[-1], top))), tg.set_text(r["code"])
            pl = [pp for pp in r.get("pits", []) if pp <= x]
            dt.set_data(pl, [g[pp - 1] for pp in pl])
        _spread(tags, top)
        lap_t.set_text(f"{min(k, laps)}/{laps}")
        r_.add(c.fig)
    for r, tg, g in zip(rows, tags, G):
        tg.set_position((laps * 1.012, min(g[-1], top)))
        tg.set_text(f"{r['code']} {final.get(r['code'], '')}".strip())
    _spread(tags, top)
    lap_t.set_text("FLAG")
    lap_t.set_color(P.GOLD)
    r_.add(c.fig, int(3.5 * FPS))
    plt.close(c.fig)
    return r_.close()


def tyre_stints(p, rows: list[dict], laps: int, out: Path, hook: list[str], sub: str,
                src: str = "Stints and compounds: official timing", mark: str | None = None) -> Path:
    """Every driver's race as one bar that grows lap by lap in the colour of the tyre on the car; pit stops are the
    joins. Ends on the count of one and two stoppers. rows: [{code, color, stints: [(compound, first lap, last lap)]}]."""
    from .gp_facts import COMPOUND_COLOR
    P.set_event(p)
    c = _card(p)
    _hook(c, hook, sub, y0=0.83)
    if mark:
        c.text(0.5, 0.712, mark, 13, color=P.GOLD, weight=700, track=True)
    n_r = len(rows)
    y_top, y_bot = 0.69, 0.31
    step = (y_top - y_bot) / max(n_r, 1)
    x0, x1 = 0.20, 0.90
    bars = []
    for k, r in enumerate(rows):
        y = y_top - (k + 0.5) * step
        c.text(0.08, y, r["code"], 15, color=r.get("color") or P.TEXT, weight=700, ha="left")
        segs = []
        for cp, a, b in r["stints"]:
            rect = plt.Rectangle((x0 + (x1 - x0) * (a - 1) / laps, y - step * 0.32), 0.0, step * 0.64,
                                 transform=c.fig.transFigure, fc=COMPOUND_COLOR.get(cp.upper(), P.TEXT), ec="#0B0E14", lw=1.5)
            c.fig.add_artist(rect)
            segs.append((rect, a, b))
        bars.append(segs)
    for xl, lab in ((x0, "LAP 1"), (x1, f"LAP {laps}")):
        c.text(xl, y_bot - 0.012, lab, 11, color=P.MUTED, weight=600, track=True)
    used_c = [cp for cp in ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET") if any(s[0].upper() == cp for r in rows for s in r["stints"])]
    for k, cp in enumerate(used_c):                                 # legend
        xl = 0.5 + (k - (len(used_c) - 1) / 2) * 0.18
        c.fig.add_artist(plt.Rectangle((xl - 0.07, y_bot - 0.034), 0.022, 0.010, transform=c.fig.transFigure, fc=COMPOUND_COLOR[cp]))
        c.text(xl - 0.042, y_bot - 0.029, cp, 12, color=P.TEXT, weight=600, ha="left", track=True)
    lap_t = c.text(0.5, 0.245, "", 44, weight=200)
    stops = [len(r["stints"]) - 1 for r in rows]
    _foot(c, src)
    r_ = Reel(out)
    n = int(11 * FPS)
    for i in range(n + 1):
        x = laps * i / n
        for segs in bars:
            for rect, a, b in segs:
                done = min(max(x - (a - 1), 0), b - a + 1)
                rect.set_width((x1 - x0) * done / laps)
        lap_t.set_text(f"LAP {max(1, int(x))}")
        r_.add(c.fig)
    one, two = stops.count(1), sum(1 for s in stops if s >= 2)
    lap_t.set_text(f"{one} one stop, {two} two stop")
    lap_t.set_color(P.GOLD)
    r_.add(c.fig, int(3.5 * FPS))
    plt.close(c.fig)
    return r_.close()


def overtakes_map(p, ref: dict, passes: list[dict], laps: int, out: Path, hook: list[str], sub: str,
                  colors: dict[str, str], corner_fracs: dict[str, float] | None = None,
                  src: str = "On track passes: OpenF1 position swaps, pit stop swaps and safety car laps removed",
                  mark: str | None = None) -> Path:
    """Every on track pass of the race (Michel, 21 Nov): a big counter ticks up lap by lap and each pass pops onto
    the map where it happened, in the overtaking driver's colour, so the overtaking hot spots build up on their own.
    Ends on the total, the hot spot and the top overtaker. passes: [{lap, frac (share of the lap), who, whom}]."""
    P.set_event(p)
    R_ = {k: np.array(v, float) if isinstance(v, list) else v for k, v in ref.items()}
    fr = R_["dist"] / R_["dist"][-1]
    c = _card(p)
    _hook(c, hook, sub, y0=0.83)
    if mark:
        c.text(0.5, 0.712, mark, 13, color=P.GOLD, weight=700, track=True)
    mp = _track(c, [0.08, 0.37, 0.84, 0.33], R_["x"], R_["y"], lw=12)
    xs = np.interp([q["frac"] for q in passes], fr, R_["x"])
    ys = np.interp([q["frac"] for q in passes], fr, R_["y"])
    ring = mp.scatter([], [], s=[], facecolors="none", edgecolors=[], linewidths=2, zorder=6)
    cnt = c.text(0.5, 0.30, "0", 96, weight=200)
    c.text(0.5, 0.258, "ON TRACK PASSES", 13, color=P.MUTED, weight=600, track=True)
    lap_t = c.text(0.5, 0.228, "", 18, color=P.MUTED, weight=300)
    _foot(c, src)
    order = sorted(range(len(passes)), key=lambda k: passes[k]["lap"] + passes[k]["frac"])
    when = np.array([passes[k]["lap"] - 1 + passes[k]["frac"] for k in order])
    cols = [colors.get(passes[k]["who"], P.TEXT) for k in order]
    px, py = xs[order], ys[order]
    r_ = Reel(out)
    n = int(12 * FPS)
    added = 0
    for i in range(n + 1):
        x = laps * i / n
        m = int(np.searchsorted(when, x, side="right"))
        while added < m:                                            # one marker per pass, added as it happens
            mp.plot([px[added]], [py[added]], "o", ms=12, color=cols[added], alpha=0.9, mec="#0B0E14", mew=1, zorder=5)
            added += 1
        if m:
            age = x - when[:m]
            fresh = age < laps * 0.03                             # a short pulse on new passes
            ring.set_offsets(np.column_stack([px[:m][fresh], py[:m][fresh]]) if fresh.any() else np.empty((0, 2)))
            ring.set_sizes(300 + 1600 * (1 - age[fresh] / (laps * 0.03)))
            ring.set_edgecolors([cols[k] for k in np.where(fresh)[0]])
        cnt.set_text(str(m))
        lap_t.set_text(f"LAP {max(1, min(laps, int(np.ceil(x))))} OF {laps}")
        r_.add(c.fig)
    ring.set_offsets(np.empty((0, 2)))
    # hot spot: the busiest 6% of the lap; named after the nearest corner when known
    fracs = np.array([q["frac"] for q in passes])
    centers = np.linspace(0, 1, 101)
    dens = [np.sum(np.abs(((fracs - c0 + 0.5) % 1) - 0.5) < 0.03) for c0 in centers]
    hot = float(centers[int(np.argmax(dens))])
    name = None
    if corner_fracs:
        name = min(corner_fracs, key=lambda k: abs(corner_fracs[k] - hot))
    hx, hy = np.interp(hot, fr, R_["x"]), np.interp(hot, fr, R_["y"])
    mp.scatter([hx], [hy], s=2600, facecolors="none", edgecolors=P.GOLD, linewidths=3, zorder=7)
    x_lo, x_hi = mp.get_xlim()
    side = "right" if hx > (x_lo + x_hi) / 2 else "left"           # keep the label inside the card
    mp.annotate(f"HOT SPOT{': ' + name if name else ''}\n{max(dens)} passes", (hx, hy), xytext=(-40 if side == "right" else 40, 46),
                textcoords="offset points", ha=side, fontsize=17, color=P.GOLD, family=P.FONT, weight=700, zorder=8)
    tops = {}
    for q in passes:
        tops[q["who"]] = tops.get(q["who"], 0) + 1
    best = max(tops, key=tops.get)
    cnt.set_color(P.GOLD)
    lap_t.set_text(f"MOST PASSES: {best}, {tops[best]}")
    lap_t.set_color(colors.get(best, P.TEXT))
    r_.add(c.fig, int(3.5 * FPS))
    plt.close(c.fig)
    return r_.close()


def L_code(Ls, k):
    return Ls[k]["code"]

# ---------------------------------------------------------------- production (Michel, 17 Nov: approved, post at half past)

# day offset from qualifying day -> {hour PT: kind}; posted at HH:30, between the hourly stories
REEL_SLOTS = {
    # Michel, 20 Nov growth plan: Reels reach about 35x more accounts than stories, and braking and pedal Reels
    # lead (braker_z2 2,213, pedal_record 1,853, pedal_wet 1,646 accounts reached at Las Vegas 2026). So 2 to 4
    # Reels every race week day, braking and pedal first. hourly.SLOTS adds Reels at HH:04 on days -3 to 0.
    -5: {12: "guess", 18: "teammates_race"},                   # Monday (Saturday qualifying)
    -4: {12: "guess2023", 18: "points_teams"},
    -3: {12: "braker", 21: "pedal_record"},                    # + History Reel at 18:04
    -2: {12: "braker_z2", 15: "pedal_pole", 21: "teammates"},
    -1: {12: "braker_z3", 15: "ghost"},                        # + pedal_wet 9:04, braker_fp2 18:04
    0: {12: "board_q", 15: "ghost_q", 19: "pedal_fp3", 21: "points"},   # board_q: the standard first quali Reel (Michel, 20 Nov)
    1: {8: "ribbon_q", 10: "strengths_q", 12: "delta_q_ver_rus", 14: "strengths_q_ant_rus_lec_ham", 22: "overtakes_race"},   # Las Vegas 2026: all approved
    # Reels before 4 PM, then race news only (Michel, 21 Nov); braker_fp2 off (not previewed)   # night qualifying; delta_q_ver_rus is the
    # Las Vegas 2026 front row (elsewhere it finds no such pair and falls back); board_q went out Friday night there   # night qualifying (Las Vegas style);
    # Michel, 20 Nov: one ghost a day at most, new formats around it. ghost_fp3_* stay buildable for other circuits.
}
# A slot whose data is not in (live session not run yet, no wet pole here) takes the next of these not yet
# posted this GP, best reach first (hourly.build_reel)
FALLBACK = ["braker_z3", "braker_z2", "braker", "pedal_pole", "pedal_record", "ghost", "teammates", "points",
            "guess2023", "guess", "points_teams", "teammates_race"]
# Last line of every Reel caption and the end card: a reason to send it (sends per reach is the signal
# Instagram leans on for reach to non followers). Keyed by the start of the kind.
SEND = {
    "braker": "Send it to the friend who thinks he knows who brakes latest.",
    "pedal": "Send it to someone who has never ridden a lap from the inside.",
    "ghost": "Send it to the friend you argue F1 with.",
    "guess": "Send it to a friend and see who gets it first.",
    "teammates": "Send it to a fan of the driver on the wrong side of this.",
    "points": "Send it to the friend who already called P2.",
    "ribbon": "Send it to someone who thinks a lap is just flat out.",
    "board": "Send it to the friend who still thinks it was the car.",
    "strengths": "Send it to the friend who says it is all about the engine.",
    "delta": "Send it to the friend who argues about who was really faster.",
}


def send_line(kind: str) -> str:
    return next((v for k, v in SEND.items() if kind.startswith(k)), "Send it to the friend who needs to see this.")


TAGS = "#F1 #Formula1 {ev} #F1Telemetry #RaceWeek"


END_S = 2.5                      # seconds of end card after every Reel


def end_card(p, kind: str, out: Path) -> Path:
    """Closing frame of a Reel: the reason to send it, the site and the handle (Michel, 20 Nov growth plan)."""
    import textwrap
    from . import style as S
    P.set_event(p)
    c = _card(p)
    body = send_line(kind).removeprefix("Send it to ").rstrip(".")
    c.text(0.5, 0.64, "SEND IT TO", 18, color=P.CYAN, weight=600, track=True)
    for k, ln in enumerate(textwrap.wrap(body, 24)):
        c.text(0.5, 0.585 - k * 0.042, ln, 44, weight=300)
    c.rule(0.45, 0.55, 0.43)
    c.text(0.5, 0.38, S.SITE, 34, color=P.CYAN, weight=300)
    c.text(0.5, 0.345, "Every session, decoded in telemetry", 20, color=P.MUTED, weight=300)
    c.text(0.5, 0.29, f"Follow {S.HANDLE}", 26, weight=300)
    _foot(c, SRC_TEL)
    return c.save(out)


def append_end(video: Path, card: Path, seconds: float = END_S) -> Path:
    """Re-encode the Reel with the end card held for `seconds`, same settings as render.Reel."""
    import subprocess
    from .render import W
    tmp = video.with_name(video.stem + "_end.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-loop", "1", "-framerate", str(FPS), "-t", f"{seconds}",
        "-i", str(card), "-filter_complex",
        f"[0:v]setsar=1,fps={FPS}[a];[1:v]scale={W}:{H_REEL},setsar=1,format=yuv420p[b];[a][b]concat=n=2:v=1:a=0[o]",
        "-map", "[o]", "-an", "-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast", "-crf", "21",
        "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p", "-g", str(FPS * 2), "-movflags", "+faststart",
        str(tmp)], check=True)
    tmp.replace(video)
    return video


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


def _q_official(p) -> list[dict]:
    """Official qualifying order and times: Jolpica, or while Jolpica has not published yet, the session report
    in SESSION_NEWS (times checked in two outlets by the report task). Same shape as live._q_results."""
    from .live import _q_results
    res = _q_results(p)
    if res:
        return res
    from .gp_facts import SESSION_NEWS
    try:
        rows = SESSION_NEWS[p.title][p.season]["Q"][0]["standings"]
    except (KeyError, IndexError, TypeError):
        return []
    m_, _, sec = rows[0][1].rpartition(":")
    base = int(m_ or 0) * 60 + float(sec)
    out = []
    for k, r in enumerate(rows):
        s_ = base if k == 0 else base + float(r[1].lstrip("+"))
        t = f"{int(s_ // 60)}:{s_ % 60:06.3f}"
        out.append({"code": r[0], "pos": k + 1, "team": None, "q1": None, "q2": None, "q3": t})
    log.info("qualifying times from the session report (Jolpica not published yet)")
    return out


def _cap(p, kind: str, *blocks) -> str:
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
        cap = _cap(p, kind, f"🎥 Inside the {name} race lap record: {drv(p.driver, p.colors)}, {p.ref_year}, {h[0]['fl_time']} on lap {h[0]['fl_lap']}",
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
        cap = _cap(p, kind, f"🛑 Who brakes latest {NICK.get(p.title, 'into the fastest braking zone')}? {year} {label}, every green lap.",
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
        cap = _cap(p, kind, f"🕵️ Who is it? The {what}.", "👀 One speed trace, no names. Watch to the end for the answer.",
                   "💬 Comment your guess before the reveal!", "ℹ️ Lap time: official timing. Telemetry: OpenF1.")
    elif kind == "teammates":
        from . import news
        st = news.standings(p.season)
        rows = season_quali(p.season, st["after_round"])
        cols = _colors_now(oc, p.season, p.colors)
        teammates(p, rows, st["after_round"], video, cols, [t["name"] for t in st["teams"]])
        cap = _cap(p, kind, f"⚔️ Teammate wars: {p.season} qualifying head to head, after round {st['after_round']}.",
                   "📊 Final qualifying classification each round, the rounds both drivers took part in.",
                   "💬 Which duel surprises you most? Tell us below.")
    elif kind == "points":
        from . import news
        st = news.standings(p.season)
        pts = season_points(p.season, st["after_round"])
        codes = [r["code"] for r in st["drivers"][1:5]]
        pointsrace(p, pts, codes, _colors_now(oc, p.season, p.colors), video)
        a, b = st["drivers"][1], st["drivers"][2]
        cap = _cap(p, kind, f"📈 The fight for P2 in {p.season}, round by round.",
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
            cap = _cap(p, kind, f"👻 Two {name} poles on one map: {drv(a['code'], p.colors)} {a['year']} {a['official']} vs {drv(b['code'], p.colors)} {b['year']} {b['official']}.",
                       f"⏱️ {fast['code']} {fast['year']} quicker by {abs(a['lap_s'] - b['lap_s']):.3f} s (official pole times).",
                       "💬 Which year would you take? Tell us below.")
        else:
            if not laps:
                return None
            lap = laps[0]
            pedal(p, lap, video, ["Inside the", f"{lap['year']} pole lap"], f"{lap['code']}, {lap['year']} qualifying, {lap['official']}")
            cap = _cap(p, kind, f"🎥 Inside the {lap['year']} {name} pole lap: {drv(lap['code'], p.colors)}, {lap['official']}.",
                       "👀 Throttle, brake, gear and speed on the map, shown faster than real time.",
                       "💾 Save it.\n💬 Where is the lap won? Tell us below.")
    elif kind == "pedal_q":
        res = _q_official(p)
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
        from .gp_facts import grid_pole
        gp = grid_pole(p.season, p.round, lap["code"])
        pedal(p, lap, video, ["Inside the", "fastest quali lap" if gp else "pole lap"], f"{lap['code']}, {name} {p.season}, {official}")
        cap = _cap(p, kind, (f"🎥 Inside the fastest qualifying lap in {name}: {drv(lap['code'], p.colors)}, {official}. {gp} starts from pole after grid penalties."
                             if gp else f"🎥 Inside the {name} pole lap: {drv(lap['code'], p.colors)}, {official}."),
                   "👀 Every input on the lap, live on the map, shown faster than real time.",
                   "💾 Save it.\n💬 Who beats it in the race? Tell us below.")
    elif kind == "ghost_q":                      # this year's pole lap vs P2, official qualifying times
        res = _q_official(p)
        if len(res) < 2:
            return None

        def _ms(r):
            t = r["q3"] or r["q2"] or r["q1"]
            m_, _, sec = t.rpartition(":")
            return (int(m_ or 0) * 60 + float(sec)) * 1000, t
        try:
            (ma, ta), (mb, tb) = _ms(res[0]), _ms(res[1])
            a = lap_of(oc, p.season, ck, "Qualifying", rot, res[0]["code"], ma) | {"year": p.season, "official": ta}
            b = lap_of(oc, p.season, ck, "Qualifying", rot, res[1]["code"], mb) | {"year": p.season, "official": tb}
        except Exception:
            return None
        from .gp_facts import grid_pole
        gp = grid_pole(p.season, p.round, a["code"])
        ghost(p, a, b, video, ["Fastest vs P2," if gp else "Pole vs P2,", "one map"], f"{a['code']} vs {b['code']}, {name} {p.season} qualifying, official times")
        cap = _cap(p, kind, (f"👻 The two fastest qualifying laps in {name}, replayed on one map: {drv(a['code'], p.colors)} {ta} vs {drv(b['code'], p.colors)} {tb}. {gp} starts from pole after grid penalties."
                             if gp else f"👻 Pole vs P2 in {name}, replayed on one map: {drv(a['code'], p.colors)} {ta} vs {drv(b['code'], p.colors)} {tb}."),
                   f"⏱️ The gap: {abs(ma - mb) / 1000:.3f} s (official qualifying times).",
                   "💬 Where was pole won? Tell us below.")
    elif kind == "pedal_fp3":                    # this year's fastest FP3 lap
        try:
            lap = lap_of(oc, p.season, ck, "Practice 3", rot)
        except Exception:
            return None
        pedal(p, lap, video, ["Inside the", "fastest FP3 lap"], f"{lap['code']}, {name} {p.season}, FP3, {_clock(lap['lap_s'])}")
        cap = _cap(p, kind, f"🎥 Inside the fastest FP3 lap in {name}: {drv(lap['code'], p.colors)}, {_clock(lap['lap_s'])}.",
                   "👀 Throttle, brake, gear and speed on the map, shown faster than real time.",
                   "💬 Does it carry into the race? Tell us below.")
    elif kind in ("ribbon_q", "delta_q") or kind.startswith("delta_q_"):
        from .gp_facts import grid_pole
        res = _q_official(p)

        def _ms(r):
            t = r["q3"] or r["q2"] or r["q1"]
            m_, _, sec = t.rpartition(":")
            return (int(m_ or 0) * 60 + float(sec)) * 1000, t
        if kind == "ribbon_q":
            if not res:
                return None
            ms, t = _ms(res[0])
            try:
                lap = lap_of(oc, p.season, ck, "Qualifying", rot, res[0]["code"], ms)
            except Exception:
                return None
            if abs(lap["lap_s"] * 1000 - ms) > 5:
                return None
            gp = grid_pole(p.season, p.round, lap["code"])
            label = "fastest in qualifying" if gp else "pole lap"
            speed_ribbon(p, lap | {"official": t, "label": label}, video, ["Every km/h of", "the fastest lap" if gp else "the pole lap"],
                         f"{lap['code']}, {name} {p.season} qualifying, {t}")
            sp = np.array(lap["speed"], float)
            cap = _cap(p, kind, f"🌈 Every km/h of the {'fastest qualifying' if gp else 'pole'} lap in {name}: {drv(lap['code'], p.colors)}, {t}."
                                + (f" {gp} starts from pole after grid penalties." if gp else ""),
                       f"⚡ Top speed {sp.max():.0f} km/h, slowest corner {sp[5:-5].min():.0f} km/h (OpenF1 telemetry).",
                       "💬 Which corner would you take flat? Tell us below.")
        else:
            parts = kind.split("_")[2:]
            if len(parts) == 2:
                ra = next((r for r in res if r["code"] == parts[0].upper()), None)
                rb = next((r for r in res if r["code"] == parts[1].upper()), None)
            else:
                ra, rb = (res[0], res[1]) if len(res) > 1 else (None, None)
            if not ra or not rb:
                return None
            (ma, ta), (mb, tb) = _ms(ra), _ms(rb)
            try:
                a = lap_of(oc, p.season, ck, "Qualifying", rot, ra["code"], ma)
                b = lap_of(oc, p.season, ck, "Qualifying", rot, rb["code"], mb)
            except Exception:
                return None
            if abs(a["lap_s"] * 1000 - ma) > 5 or abs(b["lap_s"] * 1000 - mb) > 5:
                log.warning("delta_q: OpenF1 laps do not match the official qualifying times")
                return None
            delta_map(p, a, b, video, None, f"{a['code']} vs {b['code']}, {name} {p.season} qualifying",
                      (ma / 1000, mb / 1000))
            cap = _cap(p, kind, f"🟩 Mini sector by mini sector, {name} qualifying: {drv(a['code'], p.colors)} {ta} vs {drv(b['code'], p.colors)} {tb}.",
                       f"⏱️ The gap: {abs(mb - ma) / 1000:.3f} s (official qualifying times). The track turns the colour of whoever was quicker there.",
                       "💬 Where would you have found the time? Tell us below.")
    elif kind in ("board_q", "board_q_v2"):        # board_q_v2: the fixed board, reposted at Las Vegas 2026                      # top four qualifying laps on one animated board
        from .gp_facts import grid_pole
        res = _q_official(p)[:4]
        if len(res) < 2:
            return None
        laps, off, rows = [], [], []
        for r_ in res:
            t = r_["q3"] or r_["q2"] or r_["q1"]
            m_, _, sec = t.rpartition(":")
            ms = (int(m_ or 0) * 60 + float(sec)) * 1000
            try:
                L = lap_of(oc, p.season, ck, "Qualifying", rot, r_["code"], ms)
            except Exception:
                continue
            if abs(L["lap_s"] * 1000 - ms) > 5:
                continue
            laps.append(L), off.append(ms / 1000), rows.append((r_["code"], t))
        if len(laps) < 2 or rows[0][0] != res[0]["code"]:
            log.warning("board_q: OpenF1 laps do not match the official qualifying times")
            return None
        log.info("BOARD_LAPS_JSON " + json.dumps([{k: L[k] for k in ("code", "color", "t", "dist", "speed", "throttle", "brake", "x", "y", "lap_s")}
                                                 | {"official": o_} for L, o_ in zip(laps, off)], separators=(",", ":")))
        q_board(p, laps, off, video, ["Q3, the top four", "laps on one board"], f"{name} {p.season} qualifying, official times")
        gp = grid_pole(p.season, p.round, rows[0][0])
        st = [_lap_stats({k: np.array(L[k], float) for k in ("t", "throttle", "brake", "speed")}) for L in laps]
        lines = [f"{drv(c_, p.colors)} {t}: {s_['full']:.1f}% full throttle, top {s_['top']:.0f} km/h" for (c_, t), s_ in zip(rows, st)]
        cap = _cap(p, kind, f"📊 Q3 in {name}, the top {len(laps)} laps on one board." + (f" {gp} starts from pole after grid penalties." if gp else ""),
                   "\n".join(lines),
                   "📐 Throttle, brake and top speed: OpenF1 telemetry. Lap times: official qualifying.",
                   "💬 Who had the best lap in them? Tell us below.")
    elif kind == "strengths_q" or kind.startswith("strengths_q_"):   # where each car is strong (Michel, 20 and 21 Nov)
        from .gp_facts import Q_EXTRA
        allres = _q_official(p)
        pick = [c_.upper() for c_ in kind.split("_")[2:]]
        if pick:                                  # named drivers, best qualifying lap of each (Q1, Q2 or Q3)
            extra = Q_EXTRA.get((p.title, p.season), {})
            res = []
            for c_ in pick:
                r_ = next((r for r in allres if r["code"] == c_), None)
                if r_ is None and c_ in extra:
                    r_ = {"code": c_, "q1": None, "q2": None, "q3": extra[c_]}
                if r_ is None:
                    return None
                res.append(r_)
        else:
            res = allres[:4]
        laps, off = [], []
        for r_ in res:
            ts = [x for x in (r_["q1"], r_["q2"], r_["q3"]) if x]
            t = min(ts, key=lambda x: (int(x.rpartition(":")[0] or 0) * 60 + float(x.rpartition(":")[2]))) if ts else None
            m_, _, sec = t.rpartition(":")
            ms = (int(m_ or 0) * 60 + float(sec)) * 1000
            try:
                L = lap_of(oc, p.season, ck, "Qualifying", rot, r_["code"], ms)
            except Exception:
                continue
            if abs(L["lap_s"] * 1000 - ms) <= 5:
                laps.append(L), off.append(ms / 1000)
        if len(laps) < 3 or laps[0]["code"] != res[0]["code"]:
            return None
        log.info("STRENGTH_LAPS_JSON " + json.dumps([{k: L[k] for k in ("code", "color", "t", "dist", "speed", "throttle", "brake", "x", "y", "lap_s")}
                                                    | {"official": o_} for L, o_ in zip(laps, off)], separators=(",", ":")))
        D = strength_data(laps)
        if len(D["clean"]) < 2:
            return None
        cn = CORNER_NAMES.get((p.title, len(D["fa"]))) or [f"C{k + 1}" for k in range(len(D["fa"]))]
        if pick:
            hk = STRENGTH_HOOKS.get(kind, ["Where each car", "is strong"])
            sb_ = f"{name} {p.season} qualifying, best laps: " + ", ".join(L["code"] for L in laps)
        else:
            hk, sb_ = ["Where each car", "is strong"], f"{name} {p.season} Q3, the top {len(laps)} laps"
        strengths(p, laps, off, video, hk, sb_, cn, D["clean"], STRENGTH_ROWS.get(kind, ("top", "apex", "brake")))
        sess = {}
        for r_ in res:
            ts = {q: r_[q] for q in ("q1", "q2", "q3") if r_[q]}
            if ts:
                sess[r_["code"]] = min(ts, key=lambda q: int(ts[q].rpartition(":")[0] or 0) * 60 + float(ts[q].rpartition(":")[2])).upper()
        sess.update(Q_EXTRA_SESSION.get((p.title, p.season), {}))
        cap = _cap(p, kind, *strength_caption(p, D, cn, "best qualifying laps" if pick else None,
                                              "strip" in STRENGTH_ROWS.get(kind, ()), sess if pick and len(set(sess.values())) > 1 else None))
    elif kind == "overtakes_race":              # every on track pass, every race (Michel, 21 Nov)
        try:
            O = overtake_data(oc, p.season, ck, rot)
            ref = lap_of(oc, p.season, ck, "Race", rot)
        except Exception as e:
            log.warning("overtakes_race: data not in: %s", e)
            return None
        if len(O["passes"]) < 5:
            return None
        R_ = {k: np.array(v, float) if isinstance(v, list) else v for k, v in ref.items()}
        for q in O["passes"]:                     # time share of the lap -> distance share on the reference lap
            q["frac"] = float(np.interp(q["tfrac"] * R_["t"][-1], R_["t"], R_["dist"]) / R_["dist"][-1])
        D = strength_data([ref, ref])
        cn = CORNER_NAMES.get((p.title, len(D["fa"])))
        cf = dict(zip(cn, D["fa"])) if cn else None
        log.info("PASSES_JSON " + json.dumps({"passes": O["passes"], "raw": O["raw"], "laps": O["laps"], "neutral": O["neutral"],
                                              "ref": {k: ref[k] for k in ("x", "y", "dist", "t", "speed", "code", "lap_s")}},
                                             separators=(",", ":")))
        overtakes_map(p, ref, O["passes"], O["laps"], video, [f"{len(O['passes'])} on track", "passes. Watch them"],
                      f"{name} {p.season}, every on track pass", O["colors"], cf)
        tops = {}
        for q in O["passes"]:
            tops[q["who"]] = tops.get(q["who"], 0) + 1
        best = sorted(tops, key=lambda c_: -tops[c_])[:3]
        cap = _cap(p, kind, f"🔁 {name} {p.season}: {len(O['passes'])} on track passes, every one on the map where it happened.",
                   "🏁 Most passes: " + ", ".join(f"{drv(c_, p.colors)} {tops[c_]}" for c_ in best) + ".",
                   f"📐 Our count from OpenF1 position swaps ({O['raw']} in total): pit stop swaps, safety car laps and "
                   "instant swap backs removed. Official counts can differ slightly.",
                   "💬 Who was your favourite driver today?")
    elif kind.startswith("ghost_fp3_"):          # fastest FP3 lap vs one rival, official FP3 times (Michel, 20 Nov)
        from .gp_facts import SESSION_NEWS
        code = kind.rsplit("_", 1)[1].upper()
        try:
            rows = SESSION_NEWS[p.title][p.season]["FP3"][0]["standings"]
        except (KeyError, IndexError, TypeError):
            return None
        other = next((r for r in rows if r[0] == code), None)
        if other is None or rows[0][0] == code:
            return None

        def _ms(t):
            m_, _, sec = t.rpartition(":")
            return (int(m_ or 0) * 60 + float(sec)) * 1000
        ma = _ms(rows[0][1])
        mb = ma + float(other[1].lstrip("+")) * 1000
        try:
            a = lap_of(oc, p.season, ck, "Practice 3", rot, rows[0][0], ma) | {"year": "FP3"}
            b = lap_of(oc, p.season, ck, "Practice 3", rot, code, mb) | {"year": "FP3"}
        except Exception:
            return None
        if abs(a["lap_s"] * 1000 - ma) > 5 or abs(b["lap_s"] * 1000 - mb) > 5:   # telemetry lap must be the classified one
            log.warning("ghost_fp3: OpenF1 laps do not match the official FP3 times")
            return None
        ta, tb = _clock(ma / 1000), _clock(mb / 1000)
        ghost(p, a, b, video, [f"{a['code']} vs {b['code']},", "FP3 on one map"],
              f"{name} {p.season}, third practice, official times", "Lap times: official FP3 classification. Positions: OpenF1 telemetry")
        cap = _cap(p, kind, f"👻 FP3 in {name}, replayed on one map: {drv(a['code'], p.colors)} {ta} vs {drv(b['code'], p.colors)} {tb}.",
                   f"⏱️ The gap: {(mb - ma) / 1000:.3f} s (official FP3 times).",
                   "💬 Where does the time go? Tell us below.")
    elif kind == "points_teams":
        from . import news
        st = news.standings(p.season)
        pts = season_points_teams(p.season, st["after_round"])
        names = [t["name"] for t in st["teams"][1:5]]
        cols = _colors_now(oc, p.season, {})
        drv_team = {}
        for r in news.standings(p.season)["drivers"]:
            drv_team.setdefault(r["team"], r["code"])
        tcol = {t: cols.get(drv_team.get(t), P.CYAN) for t in names}
        pointsrace(p, pts, names, tcol, video, teams=True)
        a, b = st["teams"][1], st["teams"][2]
        cap = _cap(p, kind, f"📈 The constructors fight for P2 in {p.season}, round by round.",
                   f"🏎️ {a['name']} {a['pts']:.0f} pts\n🏎️ {b['name']} {b['pts']:.0f} pts",
                   f"ℹ️ Official standings after round {st['after_round']}.", "💬 Who keeps second? Tell us below.")
    elif kind == "pedal_wet":
        pol = _poles(p)
        wet = [(y, v) for y, v in sorted(pol.items(), reverse=True)]
        lap = None
        for y, v in wet:
            try:
                l_ = lap_of(oc, y, ck, "Qualifying", rot, v["code"], v["ms"])
            except Exception:
                continue
            if (l_.get("compound") or "").upper() in ("INTERMEDIATE", "WET"):
                lap, lap["official"] = l_, v["time"]
                break
        if lap is None:
            return None
        pedal(p, lap, video, ["Inside the", "wet pole lap"], f"{lap['code']}, {lap['year']} qualifying, {lap['official']}")
        cap = _cap(p, kind, f"🌧️ Inside the wet {name} pole lap: {drv(lap['code'], p.colors)}, {lap['year']}, {lap['official']} on {lap['compound'].lower()}s.",
                   "👀 Every input on a cold, wet track, shown faster than real time.",
                   "💾 Save it.\n💬 Could it rain again this year? Tell us below.")
    elif kind in ("braker_z2", "braker_z3"):                # 2nd and 3rd fastest braking zones
        from .lapdata import zones
        k = int(kind[-1])
        zs = sorted(zones(p), key=lambda z: -z["entry"])
        if len(zs) < k:
            return None
        z = zs[k - 1]
        zone = {"turn": z["turn"], "entry": z["entry"], "xy": [float(p.x[z["imin"]]), float(p.y[z["imin"]])]}
        rows = brake_rows_race(oc, p.ref_year, ck, rot, tuple(zone["xy"]), ref_frac=float(p.dist[z["imin"]] / p.dist[-1]))
        if len(rows) < 8:
            return None
        saved = NICK.pop(p.title, None)                      # this is not the end of the Strip: use the turn name
        try:
            braker(p, rows, zone, video, p.ref_year, "race")
        finally:
            if saved:
                NICK[p.title] = saved
        good = [r for r in rows if r.get("n", 0) >= 10 and r["err"] <= 10] or rows
        cap = _cap(p, kind, f"🛑 Who brakes latest into {zone['turn']}? {p.ref_year} race, every green lap.",
                   f"🥇 {drv(good[0]['code'], p.colors)} leads: brakes {good[0]['m']:.0f} m before the slowest point (±{good[0]['err']:.0f} m).",
                   "ℹ️ Median of each driver's green laps; the ± is the standard error. Telemetry: OpenF1.",
                   "💬 Surprised? Tell us below.")
    elif kind == "teammates_race":
        from . import news
        st = news.standings(p.season)
        rows = season_race_h2h(p.season, st["after_round"])
        teammates(p, rows, st["after_round"], video, _colors_now(oc, p.season, p.colors), [t["name"] for t in st["teams"]], "races")
        cap = _cap(p, kind, f"⚔️ Teammate wars, race edition: {p.season} race head to head, after round {st['after_round']}.",
                   "📊 Official race classification each round, the rounds both drivers started.",
                   "💬 Quali pace or race craft: which matters more? Tell us below.")
    elif kind == "guess2023":
        lap = lap_of(oc, p.season - 3, ck, "Race", rot)
        what = f"fastest lap of the {lap['year']} race here"
        guess(p, lap, video, what)
        cap = _cap(p, kind, f"🕵️ Who is it? The {what}.", "👀 One speed trace, no names. Watch to the end for the answer.",
                   "💬 Comment your guess before the reveal!", "ℹ️ Lap time: official timing. Telemetry: OpenF1.")
    else:
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-1", "-i", str(video), "-frames:v", "1", str(out / "cover.jpg")], check=True)
    # Michel, 20 Nov: no "send it to a friend" end card any more (end_card and append_end kept, unused)
    return video, cap
