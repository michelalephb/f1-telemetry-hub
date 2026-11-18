"""Race intelligence: strategy, conditions and race craft cards for race week, beyond speed.

Michel, 17 Nov: "possible strategies, who had the fastest strategy last year, could it rain, what are
the forecasts, and more material like this. Not just speed."

Every number comes from data, computed here, with its source on the card:
  last year's race at this circuit   OpenF1 stints, pit, laps, race control, weather; Jolpica classification
  safety car history                 OpenF1 race control, every race at this circuit since 2023
  forecast                           Open-Meteo hourly forecast at the circuit, fetched when the card is made

Cards are 4:5 (1080x1350) for the feed carousel; stories use the same cards on the story background.
A card whose data is missing is left out rather than guessed.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from . import preview as P
from .captions import FOOTER, clean, drv, event_tag, paragraphs
from .gp_facts import COMPOUND_COLOR
from .render import H_POST, lap_time

log = logging.getLogger(__name__)

PT = ZoneInfo("America/Los_Angeles")
LONG_RUN_LAPS = 10           # a long run: at least this many green flag laps on one set
GREEN_TOL = 1.03             # laps more than 3 % slower than the stint median are traffic, SC or VSC: dropped
# circuit coordinates for the forecast (Open-Meteo); other circuits fall back to the town's geocode
COORDS = {"LAS VEGAS": (36.1147, -115.1728), "LUSAIL": (25.4900, 51.4542), "YAS MARINA": (24.4672, 54.6031),
          "YAS ISLAND": (24.4672, 54.6031)}
COMP = {"INTERMEDIATE": "INTER"}


def comp(c) -> str:
    c = str(c or "").upper()
    return COMP.get(c, c)


# ---------------------------------------------------------------- data (network: GitHub Actions)

@lru_cache(maxsize=4)
def gather(season: int, rnd: int, title: str) -> dict:
    """Everything the cards need, computed once per run. Missing parts are simply absent."""
    from .. import jolpica
    from ..__main__ import schedule
    from ..openf1 import OpenF1

    oc = OpenF1()
    d: dict = {}
    sess = [s for s in schedule(oc, season) if s["round"] == rnd]
    if not sess:
        return d
    ck = int(sess[0]["circuit_key"])
    d["starts"] = {s["session_code"]: pd.Timestamp(s["start_utc"]) for s in sess if s["session_code"] in ("Q", "R", "SQ", "S")}
    d["location"] = sess[0].get("location") or title.title()
    ref = season - 1

    try:
        d |= last_race(oc, ref, ck, season, rnd)
    except Exception as e:
        log.warning("last year's race data unavailable: %s", e)
    try:
        d["safety"] = safety_history(oc, ck, ref)
    except Exception as e:
        log.warning("safety car history unavailable: %s", e)
    try:
        d["forecast"] = forecast(title, d["location"], d["starts"])
    except Exception as e:
        log.warning("forecast unavailable: %s", e)
    log.info("insights %s: %s", title, {k: v for k, v in d.items() if k in ("stops", "pit", "longrun", "climbers", "safety", "forecast", "track")})
    return d


def last_race(oc, ref: int, ck: int, season: int, rnd: int) -> dict:
    from .. import jolpica
    rs = oc.frame("sessions", year=ref, circuit_key=ck, session_name="Race")
    if rs.empty:
        return {}
    sk = int(rs.iloc[0]["session_key"])
    out: dict = {"ref": ref}
    drivers = oc.frame("drivers", session_key=sk)
    code = {int(r["driver_number"]): r["name_acronym"] for _, r in drivers.iterrows()}
    out["colors"] = {r["name_acronym"]: "#" + str(r.get("team_colour") or "888888").lstrip("#") for _, r in drivers.iterrows()}

    # official classification (Jolpica): order, grid, disqualifications
    cid = next(e["circuit_id"] for e in jolpica.events(season) if e["round"] == rnd)
    prev = next(e for e in jolpica.events(ref) if e["circuit_id"] == cid)
    res = [r for r in jolpica.results(ref, prev["round"]) if r["session_code"] == "R"]
    dsq = {r["driver_code"] for r in res if "isqualif" in (r.get("status") or "")}
    classified = sorted([r for r in res if r["position"] and r["driver_code"] not in dsq
                         and str(r.get("position_text", "")).isdigit()], key=lambda r: r["position"])
    out["classified"] = [{"code": r["driver_code"], "pos": i + 1, "grid": r["grid"]} for i, r in enumerate(classified)]
    out["dsq"] = sorted(dsq)
    total = max((r["laps"] or 0) for r in res) if res else 0
    out["laps"] = total

    # stints per driver
    st = oc.frame("stints", session_key=sk)
    plan = {}
    if len(st):
        st = st.sort_values(["driver_number", "stint_number"])
        for num, g in st.groupby("driver_number"):
            c = code.get(int(num))
            rows = [(comp(r["compound"]), int(r["lap_start"]), int(r["lap_end"])) for _, r in g.iterrows()
                    if pd.notna(r["lap_start"]) and pd.notna(r["lap_end"])]
            if c and rows:
                plan[c] = rows
    out["plan"] = plan
    fin = [r["code"] for r in out["classified"]]
    stops = {}
    for c in fin:
        if c in plan:
            stops[c] = len(plan[c]) - 1
    out["stops"] = stops

    # pit lane time (entry to exit), median over all stops of the race
    pit = oc.frame("pit", session_key=sk)
    if len(pit):
        col = "lane_duration" if "lane_duration" in pit and pit["lane_duration"].notna().any() else "pit_duration"
        lane = pd.to_numeric(pit[col], errors="coerce")
        lane = lane[(lane > 10) & (lane < 60)]
        stat = pd.to_numeric(pit["stop_duration"], errors="coerce") if "stop_duration" in pit else pd.Series(dtype=float)
        stat = stat[(stat > 1) & (stat < 15)]
        if len(lane):
            out["pit"] = {"lane_s": round(float(lane.median()), 1), "n": int(len(lane)),
                          "fastest_lane_s": round(float(lane.min()), 1),
                          "stop_s": round(float(stat.median()), 1) if len(stat) else None}

    # long runs: median green lap on one set, at least LONG_RUN_LAPS laps
    laps = oc.frame("laps", session_key=sk)
    runs = []
    if len(laps) and plan:
        laps = laps[laps["lap_duration"].notna()]
        laps["code"] = laps["driver_number"].map(lambda n: code.get(int(n)))
        for c, rows in plan.items():
            mine = laps[laps["code"] == c]
            for cpd, a, b in rows:
                lt = mine[(mine["lap_number"] > max(a, 1)) & (mine["lap_number"] < b)]
                lt = lt[~lt["is_pit_out_lap"].fillna(False).astype(bool)]
                v = lt["lap_duration"].to_numpy(float)
                if len(v) < LONG_RUN_LAPS:
                    continue
                med = np.median(v)
                g = lt[lt["lap_duration"] <= med * GREEN_TOL]
                if len(g) < LONG_RUN_LAPS:
                    continue
                runs.append({"code": c, "compound": cpd, "from": a, "to": b, "n": int(len(g)),
                             "median_s": round(float(np.median(g["lap_duration"])), 3),
                             "laps": g["lap_number"].astype(int).tolist(),
                             "times": g["lap_duration"].astype(float).round(3).tolist()})
    runs.sort(key=lambda r: r["median_s"])
    out["longrun"] = runs[:3]

    # biggest climbers, grid to flag (official grid; 0 means pit lane start)
    cl = []
    for r in out["classified"]:
        g = r["grid"] if r["grid"] else 20
        cl.append({"code": r["code"], "grid": g, "pit_lane": not r["grid"], "pos": r["pos"], "gain": g - r["pos"],
                   "plan": "".join(x[0][0] for x in plan.get(r["code"], []))})
    out["climbers"] = sorted(cl, key=lambda x: -x["gain"])[:5]

    # track and air temperature during the race
    w = oc.frame("weather", session_key=sk)
    if len(w):
        out["track"] = {"track_c": round(float(w["track_temperature"].median()), 1),
                        "air_c": round(float(w["air_temperature"].median()), 1),
                        "track_min": round(float(w["track_temperature"].min()), 1),
                        "rain": bool((w["rainfall"].fillna(0) > 0).any())}
    return out


SC_RX = re.compile(r"^(VIRTUAL )?SAFETY CAR DEPLOYED", re.I)


def safety_history(oc, ck: int, upto: int) -> list[dict]:
    """Every race at this circuit in OpenF1 (from 2023): safety cars, virtual safety cars, red flags."""
    out = []
    for y in range(2023, upto + 1):
        rs = oc.frame("sessions", year=y, circuit_key=ck, session_name="Race")
        if rs.empty:
            continue
        rc = oc.frame("race_control", session_key=int(rs.iloc[0]["session_key"]))
        ev = []
        for _, r in rc.iterrows():
            m = str(r.get("message") or "")
            if SC_RX.match(m):
                ev.append(("VSC" if m.upper().startswith("VIRTUAL") else "SC", int(r["lap_number"]) if pd.notna(r.get("lap_number")) else None))
            elif str(r.get("flag") or "").upper() == "RED":
                ev.append(("RED", int(r["lap_number"]) if pd.notna(r.get("lap_number")) else None))
        out.append({"year": y, "events": ev})
    return out


def forecast(title: str, location: str, starts: dict) -> dict:
    """Open-Meteo hourly forecast at the circuit for qualifying and the race (first two hours of each)."""
    lat, lon = COORDS.get(title) or geocode(location)
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=30, params={
        "latitude": lat, "longitude": lon, "timezone": "UTC", "forecast_days": 16,
        "hourly": "temperature_2m,precipitation_probability,wind_speed_10m"})
    r.raise_for_status()
    h = r.json()["hourly"]
    t = pd.to_datetime(h["time"], utc=True)
    out = {"issued": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    for k in ("Q", "SQ", "S", "R"):
        if k not in starts:
            continue
        s = starts[k].tz_convert("UTC").floor("h")
        idx = [i for i, x in enumerate(t) if s <= x <= s + pd.Timedelta(hours=2)]
        if not idx:
            continue
        rain = [h["precipitation_probability"][i] for i in idx if h["precipitation_probability"][i] is not None]
        out[k] = {"temp_c": round(h["temperature_2m"][idx[0]]), "rain_pct": int(max(rain)) if rain else None,
                  "wind_kmh": round(h["wind_speed_10m"][idx[0]])}
    return out if any(k in out for k in ("Q", "R")) else {}


def geocode(name: str) -> tuple[float, float]:
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": name, "count": 1}, timeout=30)
    r.raise_for_status()
    g = r.json()["results"][0]
    return g["latitude"], g["longitude"]


# ---------------------------------------------------------------- drawing helpers

def _ax(c, rect):
    ax = c.fig.add_axes(rect)
    ax.set_facecolor("none")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=P.MUTED, labelsize=12, length=0)
    ax.grid(False)
    return ax


def _card(p, kicker: str, number: str, unit: str, line: str, source: str, n=None, total=None, swipe=True):
    c = P.Card(H_POST)
    c.header(p)
    t = c.top
    c.kicker(t - 0.07, kicker, n, total)
    c.number(t - 0.215, number, unit, size=150)
    c.text(0.5, t - 0.265, line, 23, weight=300)
    c.text(0.5, 0.105, source, 13, color=P.MUTED, weight=300)
    c.footer("SWIPE  →" if swipe else None)
    return c


def _src(d) -> str:
    return f"{d['ref']} race"


def team(d, code):
    return d.get("colors", {}).get(code, P.TEXT)


# ---------------------------------------------------------------- the cards
# each returns (Card) or None when its data is missing

def winning_plan(p, d, **kw):
    cl, plan = d.get("classified") or [], d.get("plan") or {}
    rows = [r["code"] for r in cl[:10] if r["code"] in plan]
    if len(rows) < 5:
        return None
    win = rows[0]
    n = len(plan[win]) - 1
    seq = " to ".join(f"{x[0].lower()}" for x in plan[win])
    pits = ", ".join(f"lap {plan[win][i - 1][2]}" for i in range(1, len(plan[win])))
    c = _card(p, f"{d['ref']} winning strategy", str(n), "stop" if n == 1 else "stops",
              f"{win}: {seq}" + (f", pitted {pits}" if pits else ""),
              f"Top 10 classified, tyre sets by lap. {_src(d)}: OpenF1 stints, official classification", **kw)
    ax = _ax(c, [0.15, 0.17, 0.78, 0.43])
    total = d.get("laps") or max(x[2] for r in rows for x in plan[r])
    for i, code in enumerate(rows):
        y = len(rows) - 1 - i
        for cpd, a, b in plan[code]:
            ax.barh(y, b - a + 1, left=a - 0.5, height=0.62, color=COMPOUND_COLOR.get(cpd, "#666"), edgecolor="#0B0E14", lw=2)
            if b - a >= 6:
                ax.text((a + b) / 2, y, cpd[0], ha="center", va="center", fontsize=11, color="#0B0E14", family=P.FONT, weight=700)
        ax.text(-1.0, y, f"P{i + 1}  {code}", ha="right", va="center", fontsize=15, color=team(d, code), family=P.FONT, weight=600)
    ax.set_xlim(0, total + 0.5)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_yticks([])
    ax.set_xticks([1] + list(range(10, total + 1, 10)) + ([total] if total % 10 else []))
    ax.set_xlabel("lap", color=P.MUTED, fontsize=12, family=P.FONT)
    return c


def stop_count(p, d, **kw):
    stops = d.get("stops") or {}
    if len(stops) < 8:
        return None
    cnt = pd.Series(list(stops.values())).value_counts().sort_index()
    top_n, top_k = int(cnt.max()), int(cnt.idxmax())
    win = (d.get("classified") or [{}])[0].get("code")
    c = _card(p, "How many stops?", f"{top_n}", f"of {len(stops)} drivers",
              f"{'stopped once' if top_k == 1 else f'made {top_k} stops'} in {d['ref']}. The winner, {win}, made {stops.get(win)} stop{'' if stops.get(win) == 1 else 's'}",
              f"Classified finishers. {_src(d)}: OpenF1 stints", **kw)
    ax = _ax(c, [0.18, 0.18, 0.64, 0.40])
    xs = list(range(int(cnt.index.min()), int(cnt.index.max()) + 1))
    vals = [int(cnt.get(x, 0)) for x in xs]
    bars = ax.bar(xs, vals, width=0.6, color=[P.CYAN if x == top_k else "#2A3242" for x in xs])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.3, str(v), ha="center", va="bottom", fontsize=20, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_xticks(xs, [f"{x} stop" if x == 1 else f"{x} stops" for x in xs], fontsize=15, color=P.TEXT, family=P.FONT)
    ax.set_yticks([])
    ax.set_ylim(0, max(vals) * 1.25)
    return c


def pit_cost(p, d, **kw):
    pit = d.get("pit")
    if not pit:
        return None
    stop = pit.get("stop_s")
    line = "Entry to exit" + (f", about {stop} s of it standing still" if stop else "")
    c = _card(p, "What a pit stop costs", f"{pit['lane_s']}", "s in the pit lane", line,
              f"Median of {pit['n']} stops, fastest {pit['fastest_lane_s']} s. {_src(d)}: OpenF1 pit data", **kw)
    ax = _ax(c, [0.10, 0.25, 0.80, 0.22])
    lane = pit["lane_s"]
    ax.barh(0, lane, height=0.35, color="#2A3242")
    if stop:
        ax.barh(0, stop, left=(lane - stop) / 2, height=0.35, color=P.CYAN)
        ax.text(lane / 2, -0.42, f"{stop} s stationary", ha="center", va="center", fontsize=15, color=P.CYAN, family=P.FONT, weight=600)
    ax.text(0, 0.42, "PIT ENTRY", ha="left", va="center", fontsize=13, color=P.MUTED, family=P.FONT, weight=600)
    ax.text(lane, 0.42, "PIT EXIT", ha="right", va="center", fontsize=13, color=P.MUTED, family=P.FONT, weight=600)
    ax.set_xlim(-0.5, lane + 0.5)
    ax.set_ylim(-0.7, 0.7)
    ax.set_xticks([]), ax.set_yticks([])
    return c


def long_run(p, d, **kw):
    runs = d.get("longrun") or []
    if not runs:
        return None
    b = runs[0]
    c = _card(p, f"{d['ref']} fastest long run", lap_time(round(b["median_s"] * 1000)), "per lap",
              f"{b['code']} on {b['compound'].lower()}s, laps {b['from']} to {b['to']}, median of {b['n']} green laps",
              f"Best 3 runs of {LONG_RUN_LAPS}+ laps on one set; traffic, SC and VSC laps dropped. {_src(d)}: OpenF1 laps", **kw)
    ax = _ax(c, [0.14, 0.17, 0.78, 0.42])
    for r in runs:
        col = team(d, r["code"])
        x = np.arange(1, len(r["times"]) + 1)
        ax.plot(x, r["times"], color=col, lw=2.4)
        ax.plot([x[-1]], [r["times"][-1]], "o", color=col, ms=6)
        ax.text(x[-1] + 0.6, r["times"][-1], f"{r['code']}  {r['compound'][0]}", color=col, fontsize=14, family=P.FONT,
                weight=600, va="center")
    ax.set_xlabel("green lap in the run", color=P.MUTED, fontsize=12, family=P.FONT)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: lap_time(round(v * 1000))))
    ax.grid(axis="y", color="#1E2533", lw=0.6)
    xm = max(len(r["times"]) for r in runs)
    ax.set_xlim(0.5, xm + 4)
    return c


def climbers(p, d, **kw):
    cl = [x for x in (d.get("climbers") or []) if x["gain"] > 0]
    if not cl:
        return None
    t = cl[0]
    start = "pit lane" if t["pit_lane"] else f"P{t['grid']}"
    c = _card(p, "Biggest climber", f"+{t['gain']}", "places",
              f"{t['code']}: {start} to P{t['pos']} on {plan_words(t['plan'])}",
              f"Official grid to official classification. {_src(d)}: Jolpica results, OpenF1 stints", **kw)
    ax = _ax(c, [0.20, 0.16, 0.60, 0.44])
    for x in cl:
        col = team(d, x["code"])
        ax.plot([0, 1], [x["grid"], x["pos"]], color=col, lw=2.6)
        ax.plot([0, 1], [x["grid"], x["pos"]], "o", color=col, ms=8)
        ax.text(-0.06, x["grid"], f"{'PL' if x['pit_lane'] else 'P' + str(x['grid'])}  {x['code']}", ha="right", va="center",
                fontsize=14, color=P.TEXT, family=P.FONT, weight=500)
        ax.text(1.06, x["pos"], f"P{x['pos']}  +{x['gain']}", ha="left", va="center", fontsize=14, color=col, family=P.FONT, weight=600)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(21, 0)
    ax.set_xticks([0, 1], ["GRID", "FLAG"], fontsize=13, color=P.CYAN, family=P.FONT, weight=600)
    ax.xaxis.tick_top()
    ax.set_yticks([])
    return c


def plan_words(s: str) -> str:
    w = {"S": "softs", "M": "mediums", "H": "hards", "I": "inters", "W": "wets"}
    return " then ".join(w.get(ch, ch) for ch in s) or "one set"


def safety(p, d, **kw):
    hist = d.get("safety") or []
    if len(hist) < 2:
        return None
    with_sc = sum(1 for h in hist if any(e[0] in ("SC", "VSC") for e in h["events"]))
    c = _card(p, "Safety car odds", f"{with_sc} of {len(hist)}", "races",
              "had a safety car or a virtual safety car here",
              f"Every race at this circuit since {hist[0]['year']}. OpenF1 race control messages", **kw)
    n = len(hist)
    for i, h in enumerate(hist):
        x = 0.5 + (i - (n - 1) / 2) * 0.28
        c.text(x, 0.53, str(h["year"]), 34, weight=200)
        ev = h["events"] or []
        if not ev:
            c.text(x, 0.47, "GREEN ALL RACE", 13, color=P.MUTED, weight=600, track=True)
        for j, (k, lap) in enumerate(ev[:5]):
            label = {"SC": "SAFETY CAR", "VSC": "VIRTUAL SC", "RED": "RED FLAG"}[k]
            col = {"SC": "#FFC107", "VSC": "#FFE082", "RED": "#EF4444"}[k]
            c.text(x, 0.47 - j * 0.045, f"{label}" + (f", LAP {lap}" if lap else ""), 13, color=col, weight=600, track=True)
    return c


def rain(p, d, **kw):
    f = d.get("forecast") or {}
    q, r = f.get("Q") or f.get("SQ"), f.get("R")
    if not (q and r) or q.get("rain_pct") is None or r.get("rain_pct") is None:
        return None
    issued = pd.Timestamp(f["issued"]).tz_convert(PT)
    hi = max(q["rain_pct"], r["rain_pct"])
    wet_ly = (p.last_year or {}).get("quali_wet")
    line = "Peak chance of rain in quali or the race" + (f" ({p.ref_year} quali was wet)" if wet_ly else "")
    c = _card(p, "Could it rain?", f"{hi}", "% chance", line,
              f"Open-Meteo forecast at the circuit, first 2 h of each session. Issued {issued:%a %-I:%M %p} PT and updated hourly",
              **kw)
    qt, rt = P.times_text(p)
    for x, name, when, v in ((0.30, "QUALIFYING", qt, q), (0.70, "RACE", rt, r)):
        c.text(x, 0.55, name, 14, color=P.CYAN, weight=600, track=True)
        c.text(x, 0.515, when, 15, color=P.MUTED, weight=400)
        c.text(x, 0.43, f"{v['temp_c']}°C", 54, weight=200)
        c.text(x, 0.355, f"{v['rain_pct']}% rain", 22, weight=400, color="#7CC4FF" if v["rain_pct"] >= 30 else P.TEXT)
        c.text(x, 0.315, f"wind {v['wind_kmh']} km/h", 18, color=P.MUTED, weight=300)
    c.fig.add_artist(plt.Line2D([0.5, 0.5], [0.30, 0.56], transform=c.fig.transFigure, color=P.GOLD, lw=0.6))
    c.text(0.5, 0.24, "local time", 12, color=P.MUTED, weight=500, track=True)
    return c


def track_temp(p, d, **kw):
    t = d.get("track")
    if not t:
        return None
    c = _card(p, f"{d['ref']} track temperature", f"{t['track_c']:.0f}", "°C",
              f"Median during the race, air {t['air_c']:.0f}°C. Cold tyres lose grip",
              f"Lowest reading {t['track_min']:.0f}°C. {_src(d)}: OpenF1 weather (official timing feed)", **kw)
    ax = _ax(c, [0.30, 0.18, 0.40, 0.40])
    vals = [t["air_c"], t["track_c"]]
    bars = ax.bar([0, 1], vals, width=0.55, color=["#2A3242", P.CYAN])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v:.0f}°C", ha="center", va="bottom", fontsize=22, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_xticks([0, 1], ["AIR", "TRACK"], fontsize=14, color=P.TEXT, family=P.FONT, weight=600)
    ax.set_yticks([])
    ax.set_ylim(0, max(vals) * 1.3 + 1)
    return c


# feed carousel: race craft from last year (no forecast: a feed post stays up)
CAROUSEL = [winning_plan, stop_count, long_run, pit_cost, climbers, safety]
# story groups
STRATEGY = [winning_plan, stop_count, long_run, climbers]
CONDITIONS = [rain, track_temp, pit_cost, safety]


def available(p, fns) -> list:
    d = gather(p.season, p.round, p.title)
    return [f for f in fns if _try(f, p, d) is not None]


def _try(f, p, d):
    try:
        c = f(p, d, swipe=False)
    except Exception as e:
        log.warning("insight card %s failed: %s", f.__name__, e)
        return None
    if c is not None:
        plt.close(c.fig)
    return c


def card_path(p, fns, i: int, out: Path) -> Path:
    P.set_event(p)
    d = gather(p.season, p.round, p.title)
    f = available(p, fns)[i]
    return f(p, d, swipe=False).save(out / f"insight_{f.__name__}.jpg")


def cover(p, d, n: int):
    c = P.Card(H_POST)
    c.header(p)
    t = c.top
    c.text(0.5, t - 0.075, "STRATEGY FILE", 16, color=P.CYAN, weight=600, track=True)
    c.text(0.5, t - 0.14, f"{d['ref']}", 76, weight=200, track=True)
    c.text(0.5, t - 0.205, "How last year's race was won", 26, color=P.MUTED, weight=300, style="italic")
    plan = d.get("plan") or {}
    rows = [r["code"] for r in (d.get("classified") or [])[:3] if r["code"] in plan]
    for i, code in enumerate(rows):
        y = 0.55 - i * 0.07
        c.text(0.20, y, f"P{i + 1}  {code}", 22, weight=500, ha="left")
        x = 0.38
        total = d.get("laps") or 50
        for cpd, a, b in plan[code]:
            w = 0.44 * (b - a + 1) / total
            c.fig.add_artist(plt.Rectangle((x, y - 0.012), w - 0.004, 0.024, transform=c.fig.transFigure,
                                           color=COMPOUND_COLOR.get(cpd, "#666")))
            x += w
    c.text(0.5, 0.30, f"{n} CHARTS: STOPS, PACE, PIT LOSS, SAFETY CARS", 17, color=P.CYAN, weight=600, track=True)
    c.text(0.5, 0.25, "Save it before quali", 20, color=P.MUTED, weight=300)
    c.footer("SWIPE  →")
    return c


def carousel(p, out: Path) -> list[Path]:
    P.set_event(p)
    d = gather(p.season, p.round, p.title)
    fns = available(p, CAROUSEL)
    if len(fns) < 3:
        raise ValueError(f"not enough race data for a strategy carousel: {[f.__name__ for f in fns]}")
    paths = [cover(p, d, len(fns)).save(out / "slide_01.jpg")]
    for i, f in enumerate(fns, 1):
        paths.append(f(p, d, n=i, total=len(fns)).save(out / f"slide_{i + 1:02d}.jpg"))
    return paths


def caption(p) -> str:
    d = gather(p.season, p.round, p.title)
    cl, plan, stops = d.get("classified") or [], d.get("plan") or {}, d.get("stops") or {}
    colors = d.get("colors")
    rows = []
    for r in cl[:3]:
        if r["code"] in plan:
            rows.append(f"P{r['pos']} {drv(r['code'], colors)}: {plan_words(''.join(x[0][0] for x in plan[r['code']]))}")
    facts = []
    if stops:
        cnt = pd.Series(list(stops.values())).value_counts()
        facts.append(f"🔁 {int(cnt.max())} of {len(stops)} finishers made {int(cnt.idxmax())} stop{'s' if cnt.idxmax() != 1 else ''}")
    if d.get("pit"):
        facts.append(f"⏱️ A stop costs about {d['pit']['lane_s']} s in the pit lane (median)")
    if d.get("longrun"):
        b = d["longrun"][0]
        facts.append(f"🚀 Fastest long run: {drv(b['code'], colors)}, {lap_time(round(b['median_s'] * 1000))} per lap on {b['compound'].lower()}s")
    cb = [x for x in (d.get("climbers") or []) if x["gain"] > 0]
    if cb:
        facts.append(f"📈 Biggest climber: {drv(cb[0]['code'], colors)}, +{cb[0]['gain']} places")
    hist = d.get("safety") or []
    if hist:
        n = sum(1 for h in hist if any(e[0] in ("SC", "VSC") for e in h["events"]))
        facts.append(f"🟡 Safety car or VSC in {n} of {len(hist)} races here since {hist[0]['year']}")
    q, r = P.times_text(p)
    dsq = d.get("dsq") or []
    return clean(paragraphs(
        f"🧠 {p.title.title()} {d['ref']}: the strategy file",
        "🏁 Top 3 tyre plans:\n" + "\n".join(rows) if rows else "",
        facts,
        f"ℹ️ Official classification" + (f", after the disqualification of {' and '.join(dsq)}" if dsq else "") + ". Tyre and pit data: OpenF1.",
        f"⏰ Quali {q}\n🏁 Race {r}\n(local time)",
        "💾 Save this for race day.\n💬 One stop or two this year? Tell us below.",
        FOOTER, " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Strategy", "#RaceWeek"])))
