"""Live practice cards: fresh data from this weekend's FP1, FP2 and FP3, posted in the hours after each session.

Per practice session: fastest laps (top 10, gap to the best), speed trap, laps run with tyre compounds;
FP2 also gets long run pace. Qualifying and the race are covered by the automatic posts.

Source: OpenF1 (official timing), available about 30 to 60 minutes after a session ends. A card appears only
once its session's data is in; nothing is estimated.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

from . import insights as I
from . import preview as P
from .gp_facts import COMPOUND_COLOR
from .render import lap_time

log = logging.getLogger(__name__)

PRACTICE = ("FP1", "FP2", "FP3")
SETTLE = timedelta(minutes=45)


@lru_cache(maxsize=8)
def session(season: int, rnd: int, code: str) -> dict:
    """Laps, stints and team colours of one practice session, if it ended and OpenF1 has its data."""
    from ..__main__ import schedule
    from ..openf1 import OpenF1
    oc = OpenF1()
    s = next((x for x in schedule(oc, season) if x["round"] == rnd and x["session_code"] == code), None)
    if s is None:
        return {}
    end = pd.Timestamp(s.get("end_utc") or s["start_utc"]) + (pd.Timedelta(0) if s.get("end_utc") else pd.Timedelta(hours=1))
    if datetime.now(timezone.utc) < end.to_pydatetime() + SETTLE:
        return {}
    sk = s["session_key"]
    laps = oc.frame("laps", session_key=sk)
    if laps.empty or laps["lap_duration"].notna().sum() < 40:
        return {}
    drv = oc.frame("drivers", session_key=sk)
    code_of = {int(r["driver_number"]): r["name_acronym"] for _, r in drv.iterrows()}
    laps["code"] = laps["driver_number"].map(lambda n: code_of.get(int(n)))
    st = oc.frame("stints", session_key=sk)
    if len(st):
        st["code"] = st["driver_number"].map(lambda n: code_of.get(int(n)))
    return {"laps": laps, "stints": st, "colors": {r["name_acronym"]: "#" + str(r.get("team_colour") or "888888").lstrip("#")
                                                   for _, r in drv.iterrows()}}


def _col(s, code):
    return s["colors"].get(code, P.CYAN)


def fastest(p, code: str):
    s = session(p.season, p.round, code)
    if not s:
        return None
    laps = s["laps"]
    best = laps.dropna(subset=["lap_duration"]).groupby("code")["lap_duration"].min().sort_values().head(10)
    if len(best) < 5:
        return None
    lead = best.iloc[0]
    c = I._card(p, f"{code} fastest laps", lap_time(round(lead * 1000)), "",
                f"{best.index[0]} tops {code}, {best.iloc[1] - lead:.3f} s clear of {best.index[1]}",
                f"Best lap per driver, top 10. {p.season} {code}: OpenF1 (official timing). Practice: fuel and programmes vary",
                swipe=False)
    ax = I._ax(c, [0.20, 0.15, 0.70, 0.45])
    for y, (dc, t) in zip(range(len(best))[::-1], best.items()):
        g = t - lead
        ax.barh(y, max(g, 0.004), color=_col(s, dc), height=0.62)
        ax.text(-0.01, y, dc, ha="right", va="center", fontsize=14, color=P.TEXT, family=P.FONT, weight=600, transform=ax.get_yaxis_transform())
        ax.text(g + 0.02, y, "BEST" if g == 0 else f"+{g:.3f}", va="center", fontsize=13, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(0, (best.iloc[-1] - lead) * 1.25 + 0.05)
    return c


def trap(p, code: str):
    s = session(p.season, p.round, code)
    if not s or "st_speed" not in s["laps"]:
        return None
    best = s["laps"].groupby("code")["st_speed"].max().dropna().sort_values(ascending=False).head(8)
    if len(best) < 5:
        return None
    c = I._card(p, f"{code} speed trap", f"{best.iloc[0]:.0f}", "km/h",
                f"{best.index[0]} fastest through the trap in {code}",
                f"Best speed trap reading per driver. {p.season} {code}: OpenF1 (official timing)", swipe=False)
    ax = I._ax(c, [0.20, 0.17, 0.70, 0.40])
    lo = best.min() - 6
    for y, (dc, v) in zip(range(len(best))[::-1], best.items()):
        ax.barh(y, v - lo, left=lo, color=_col(s, dc), height=0.6)
        ax.text(lo - 0.6, y, dc, ha="right", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=600)
        ax.text(v + 0.4, y, f"{v:.0f}", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(lo, best.max() + 5)
    return c


def mileage(p, code: str):
    s = session(p.season, p.round, code)
    if not s or s["stints"] is None or not len(s["stints"]):
        return None
    st = s["stints"].dropna(subset=["lap_start", "lap_end"]).copy()
    st["n"] = st["lap_end"] - st["lap_start"] + 1
    by = st.groupby(["code", "compound"])["n"].sum().unstack(fill_value=0)
    by["total"] = by.sum(axis=1)
    by = by.sort_values("total", ascending=False).head(8)
    if len(by) < 5:
        return None
    total = int(st["n"].sum())
    c = I._card(p, f"{code} laps run", str(int(by["total"].iloc[0])), "laps",
                f"{by.index[0]} did the most running in {code}. {total} laps in total",
                f"Laps per driver by tyre compound, top 8. {p.season} {code}: OpenF1 stints (official timing)", swipe=False)
    ax = I._ax(c, [0.20, 0.17, 0.70, 0.40])
    comps = [k for k in ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET") if k in by.columns]
    for y, (dc, r) in zip(range(len(by))[::-1], by.iterrows()):
        x = 0
        for k in comps:
            if r[k]:
                ax.barh(y, r[k], left=x, color=COMPOUND_COLOR.get(I.comp(k), "#666"), height=0.6)
                x += r[k]
        ax.text(-0.5, y, dc, ha="right", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=600)
        ax.text(x + 0.5, y, f"{int(r['total'])}", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(0, by["total"].max() * 1.15)
    return c


def longruns(p, code: str = "FP2"):
    s = session(p.season, p.round, code)
    if not s or not len(s["stints"]):
        return None
    laps, st = s["laps"], s["stints"]
    runs = []
    for _, r in st.dropna(subset=["lap_start", "lap_end"]).iterrows():
        mine = laps[(laps["code"] == r["code"]) & (laps["lap_number"] > r["lap_start"]) & (laps["lap_number"] < r["lap_end"])]
        v = mine["lap_duration"].dropna().to_numpy(float)
        if len(v) < 5:
            continue
        med = np.median(v)
        g = v[v <= med * 1.03]
        if len(g) >= 5:
            runs.append((r["code"], I.comp(r["compound"]), len(g), float(np.median(g))))
    if len(runs) < 4:
        return None
    best: dict = {}
    for r in runs:
        if r[0] not in best or r[3] < best[r[0]][3]:
            best[r[0]] = r
    top = sorted(best.values(), key=lambda r: r[3])[:8]
    c = I._card(p, f"{code} long run pace", lap_time(round(top[0][3] * 1000)), "per lap",
                f"{top[0][0]} on {top[0][1].lower()}s over {top[0][2]} laps: the best race simulation",
                f"Median lap of runs of 5+ laps on one set, best run per driver. {p.season} {code}: OpenF1. Fuel loads unknown",
                swipe=False)
    ax = I._ax(c, [0.20, 0.17, 0.70, 0.40])
    lead = top[0][3]
    for y, (dc, cp, n, t) in zip(range(len(top))[::-1], top):
        ax.barh(y, max(t - lead, 0.004), color=_col(s, dc), height=0.6)
        ax.text(-0.01, y, f"{dc}  {cp[0]}", ha="right", va="center", fontsize=14, color=P.TEXT, family=P.FONT, weight=600,
                transform=ax.get_yaxis_transform())
        ax.text(t - lead + 0.02, y, "BEST" if t == lead else f"+{t - lead:.3f}", va="center", fontsize=13, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(0, (top[-1][3] - lead) * 1.25 + 0.05)
    return c


def available(p) -> list[tuple[str, object]]:
    """(content name, card function) for every practice card whose data is in, in session order."""
    out = []
    for code in PRACTICE:
        try:
            if not session(p.season, p.round, code):
                continue
        except Exception as e:
            log.warning("practice %s unavailable: %s", code, e)
            continue
        kinds = [("fastest", fastest), ("trap", trap), ("mileage", mileage)] + ([("longruns", longruns)] if code == "FP2" else [])
        for k, f in kinds:
            out.append((f"{code}_{k}", (lambda f=f, code=code: (lambda p: f(p, code)))()))
    return out


def card_path(p, name: str, out):
    P.set_event(p)
    code, k = name.split("_", 1)
    f = {"fastest": fastest, "trap": trap, "mileage": mileage, "longruns": longruns}[k]
    c = f(p, code)
    if c is None:
        raise ValueError(f"no data for {name}")
    return c.save(out / f"live_{name}.jpg")
