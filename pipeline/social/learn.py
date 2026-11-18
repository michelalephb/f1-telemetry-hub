"""Learn and save cards: the 2026 rules in numbers (checked facts with sources), when to watch in your
time zone (computed from the official schedule), and three more data cards from last year's race here
(speed trap, ideal lap from best sectors) and this season (form guide over the last 3 races).

Rule facts were checked on 17 Nov 2026 against the published 2026 regulations summaries; each card names
its source. Numbers are the regulation limits, not measurements.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np
import pandas as pd

from . import insights as I
from . import preview as P
from .render import lap_time

log = logging.getLogger(__name__)

# (key, kicker, number, unit, line, before label, before, after label, after, source)
RULES = [
    ("mguk", "2026 rules: electric power", "350", "kW", "MGU K output, up from 120 kW: almost three times more",
     "2025", 120, "2026", 350, "Source: FIA 2026 power unit regulations, via Honda Racing F1 (Jan 2026)"),
    ("mguh", "2026 rules: one motor fewer", "0", "MGU H", "The heat recovery motor on the turbo is gone; the 1.6 L V6 turbo stays",
     None, None, None, None, "Source: FIA 2026 power unit regulations, via Honda Racing F1 (Jan 2026)"),
    ("weight", "2026 rules: lighter cars", "768", "kg minimum", "30 kg lighter: 722 kg car and driver plus 46 kg of tyres",
     "2025", 798, "2026", 768, "Source: FIA 2026 technical regulations (minimum mass)"),
    ("size", "2026 rules: smaller cars", "3400", "mm wheelbase", "200 mm shorter, and 100 mm narrower at 1900 mm wide",
     "2025", 3600, "2026", 3400, "Source: FIA 2026 technical regulations (maximum wheelbase and width)"),
    ("tyres", "2026 rules: narrower tyres", "375", "mm rear", "Rears 30 mm narrower, fronts 25 mm narrower at 280 mm",
     "2025", 405, "2026", 375, "Source: FIA 2026 technical regulations, Pirelli 2026 tyre sizes"),
    ("fuel", "2026 rules: the fuel", "100", "% sustainable", "Drop in fuel from non food sources, waste or captured carbon",
     None, None, None, None, "Source: FIA 2026 power unit regulations"),
    ("aero", "2026 rules: moving wings", "55", "% less drag", "Active aero replaces DRS. Downforce about 30% lower",
     None, None, None, None, "Source: FIA 2026 aerodynamic targets, as published at the rules launch"),
]


def rule_card(p, key: str):
    r = next(x for x in RULES if x[0] == key)
    _, kicker, num, unit, line, bl, b, al, a, src = r
    c = I._card(p, kicker, num, unit, line, src, swipe=False)
    if b is not None:
        ax = I._ax(c, [0.22, 0.20, 0.56, 0.34])
        bars = ax.bar([0, 1], [b, a], width=0.55, color=["#2A3242", P.CYAN])
        for bar, v in zip(bars, (b, a)):
            ax.text(bar.get_x() + bar.get_width() / 2, v * 1.01, f"{v:g}", ha="center", va="bottom", fontsize=22,
                    color=P.TEXT, family=P.FONT, weight=300)
        ax.set_xticks([0, 1], [bl, al], fontsize=16, color=P.TEXT, family=P.FONT, weight=600)
        ax.set_yticks([])
        lo = min(a, b)
        ax.set_ylim(lo * 0.85 if lo > 300 else 0, max(a, b) * 1.12)
    elif key == "mguh":
        for col, (yr, els) in enumerate((("2025", ["ICE", "TURBO", "MGU H", "MGU K", "BATTERY", "ELECTRONICS"]),
                                         ("2026", ["ICE", "TURBO", "MGU K", "BATTERY", "ELECTRONICS"]))):
            x = 0.32 + col * 0.36
            c.text(x, 0.57, yr, 30, weight=200)
            for i, e in enumerate(els):
                gone = e == "MGU H"
                c.text(x, 0.51 - i * 0.045, e, 17, color="#EF4444" if gone else (P.CYAN if col else P.TEXT), weight=600, track=True)
                if gone:
                    c.rule(x - 0.08, x + 0.08, 0.51 - i * 0.045, color="#EF4444", lw=2)
    elif key == "fuel":
        for i, src_ in enumerate(("NON FOOD BIOMASS", "MUNICIPAL WASTE", "CAPTURED CARBON")):
            c.text(0.5, 0.53 - i * 0.07, src_, 24, color=P.CYAN, weight=300, track=True)
        c.text(0.5, 0.31, "where the fuel can come from", 16, color=P.MUTED, weight=300)
    elif key == "aero":
        ax = I._ax(c, [0.18, 0.20, 0.64, 0.34])
        for i, (lbl, v) in enumerate((("DRAG", 45), ("DOWNFORCE", 70))):
            ax.bar([i * 3], [100], width=0.9, color="#2A3242")
            ax.bar([i * 3 + 1], [v], width=0.9, color=P.CYAN)
            ax.text(i * 3, 102, "2025", ha="center", fontsize=13, color=P.MUTED, family=P.FONT)
            ax.text(i * 3 + 1, v + 2, f"2026: {v}", ha="center", fontsize=13, color=P.TEXT, family=P.FONT)
            ax.text(i * 3 + 0.5, -10, lbl, ha="center", fontsize=16, color=P.TEXT, family=P.FONT, weight=600)
        ax.set_ylim(-15, 115)
        ax.set_xticks([]), ax.set_yticks([])
        c.text(0.5, 0.17, "index, 2025 car = 100", 13, color=P.MUTED, weight=300)
    return c


# ---------------------------------------------------------------- when to watch

ZONES = [("Los Angeles", "America/Los_Angeles"), ("New York", "America/New_York"), ("London", "Europe/London"),
         ("Paris, Rome", "Europe/Paris"), ("Dubai", "Asia/Dubai"), ("Mumbai", "Asia/Kolkata"), ("Sydney", "Australia/Sydney")]


def when_to_watch(p, d, **kw):
    st = d.get("starts") or {}
    q, r = st.get("Q") or st.get("SQ"), st.get("R")
    if q is None or r is None:
        return None
    c = I._card(p, "When to watch", "7", "time zones", "Qualifying and the race in your time",
                "Session start times from the official schedule (OpenF1)", swipe=False)
    c.text(0.56, 0.60, "QUALIFYING", 14, color=P.CYAN, weight=600, track=True)
    c.text(0.82, 0.60, "RACE", 14, color=P.CYAN, weight=600, track=True)
    for i, (name, tz) in enumerate(ZONES):
        y = 0.55 - i * 0.055
        qq, rr = q.tz_convert(tz), r.tz_convert(tz)
        c.text(0.10, y, name, 19, weight=500, ha="left")
        c.text(0.56, y, qq.strftime("%a %-I:%M %p").replace(":00", ""), 18, weight=300)
        c.text(0.82, y, rr.strftime("%a %-I:%M %p").replace(":00", ""), 18, weight=300)
        if i < len(ZONES) - 1:
            c.rule(0.10, 0.92, y - 0.027, color="#1E2533", lw=0.6)
    return c


# ---------------------------------------------------------------- more from last year's race

@lru_cache(maxsize=4)
def laps_data(season: int, rnd: int) -> pd.DataFrame:
    from ..__main__ import schedule
    from ..openf1 import OpenF1
    oc = OpenF1()
    sess = [s for s in schedule(oc, season) if s["round"] == rnd]
    ck = int(sess[0]["circuit_key"])
    rs = oc.frame("sessions", year=season - 1, circuit_key=ck, session_name="Race")
    sk = int(rs.iloc[0]["session_key"])
    laps = oc.frame("laps", session_key=sk)
    drv = oc.frame("drivers", session_key=sk)
    code = {int(r["driver_number"]): r["name_acronym"] for _, r in drv.iterrows()}
    laps["code"] = laps["driver_number"].map(lambda n: code.get(int(n)))
    return laps


def speed_trap(p, d, **kw):
    try:
        laps = laps_data(p.season, p.round)
    except Exception as e:
        log.warning("laps unavailable: %s", e)
        return None
    if "st_speed" not in laps or laps["st_speed"].notna().sum() < 50:
        return None
    best = laps.groupby("code")["st_speed"].max().dropna().sort_values(ascending=False)
    top = best.head(8)
    ref = p.season - 1
    c = I._card(p, f"{ref} speed trap", f"{top.iloc[0]:.0f}", "km/h",
                f"{top.index[0]}: the highest speed trap reading of the race", f"Best speed trap reading per driver. {ref} race: OpenF1 laps (official timing)",
                swipe=False)
    ax = I._ax(c, [0.20, 0.17, 0.70, 0.40])
    lo = top.min() - 6
    for y, (code, v) in zip(range(len(top))[::-1], top.items()):
        ax.barh(y, v - lo, left=lo, color=I.team(d, code), height=0.6)
        ax.text(lo - 0.6, y, code, ha="right", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=600)
        ax.text(v + 0.4, y, f"{v:.0f}", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(lo, top.max() + 5)
    return c


def ideal_lap(p, d, **kw):
    try:
        laps = laps_data(p.season, p.round)
    except Exception as e:
        log.warning("laps unavailable: %s", e)
        return None
    cols = ["duration_sector_1", "duration_sector_2", "duration_sector_3"]
    if not all(c in laps for c in cols):
        return None
    ok = laps[laps["lap_number"] > 1].copy()
    best = []
    for col in cols:
        s = pd.to_numeric(ok[col], errors="coerce")
        k = s.idxmin()
        best.append((ok.loc[k, "code"], float(s.loc[k])))
    ideal = sum(b for _, b in best)
    fl = pd.to_numeric(ok["lap_duration"], errors="coerce")
    kf = fl.idxmin()
    fast = float(fl.loc[kf])
    ref = p.season - 1
    c = I._card(p, f"{ref} ideal lap", lap_time(round(ideal * 1000)), "",
                f"Best three sectors of the race put together: {fast - ideal:.3f} s under the fastest lap",
                f"Fastest lap {ok.loc[kf, 'code']} {lap_time(round(fast * 1000))}. {ref} race: OpenF1 sector times (official timing)", swipe=False)
    for i, (code, t) in enumerate(best):
        x = 0.5 + (i - 1) * 0.28
        c.text(x, 0.56, f"SECTOR {i + 1}", 14, color=P.CYAN, weight=600, track=True)
        c.text(x, 0.50, f"{t:.3f}", 40, weight=200)
        c.text(x, 0.45, code, 20, weight=600, color=I.team(d, code))
    return c


def form_guide(p, d, **kw):
    from .. import jolpica
    st = I.gather(p.season, p.round, p.title)
    from .extras import _std
    s = _std(p)
    last = s["after_round"]
    pts: dict = {}
    for rnd in range(max(1, last - 2), last + 1):
        try:
            res = jolpica.results(p.season, rnd)
        except Exception:
            return None
        for r in res:
            if r["session_code"] in ("R", "S") and r["points"]:
                pts[r["driver_code"]] = pts.get(r["driver_code"], 0) + r["points"]
    if not pts:
        return None
    top = sorted(pts.items(), key=lambda x: -x[1])[:8]
    c = I._card(p, "Form guide", f"{top[0][1]:.0f}", "points", f"{top[0][0]}: most points in the last 3 rounds",
                f"Race and sprint points, rounds {max(1, last - 2)} to {last}, {p.season}. Official results (Jolpica)", swipe=False)
    ax = I._ax(c, [0.20, 0.17, 0.70, 0.40])
    for y, (code, v) in zip(range(len(top))[::-1], top):
        ax.barh(y, v, color=d.get("colors", {}).get(code, P.CYAN), height=0.6)
        ax.text(-1, y, code, ha="right", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=600)
        ax.text(v + 0.8, y, f"{v:.0f}", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(0, top[0][1] * 1.15)
    return c


def _rule(key):
    def f(p, d, **kw):
        return rule_card(p, key)
    f.__name__ = f"rule_{key}"
    return f


LEARN = [when_to_watch, speed_trap, ideal_lap, form_guide] + [_rule(r[0]) for r in RULES]
