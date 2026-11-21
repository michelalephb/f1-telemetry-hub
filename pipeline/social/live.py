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
from .gp_facts import COMPOUND_COLOR, GRID_POLE
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
                                                   for _, r in drv.iterrows()},
            "teams": {r["name_acronym"]: r.get("team_name") for _, r in drv.iterrows()}}


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
    c = I._card(p, f"{_label(code)} speed trap", f"{best.iloc[0]:.0f}", "km/h",
                f"{best.index[0]} fastest through the trap in {_label(code).lower() if code == 'Q' else code}",
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
    c = I._card(p, f"{_label(code)} laps and tyres", str(int(by["total"].iloc[0])), "laps",
                f"{by.index[0]} did the most running in {_label(code).lower() if code == 'Q' else code}. {total} laps in total",
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


# ---------------------------------------------------------------- qualifying (Michel, 17 Nov: approved for Saturday)
# The automatic quali posts (carousel, Reel, story) show the result and the pole lap; these cards add what
# they do not: speed trap, ideal lap, knockouts, teammate duels, team gaps, track evolution, laps and sets.

def _label(code: str) -> str:
    return "Quali" if code == "Q" else code


def q_ideal(p, code: str = "Q"):
    s = session(p.season, p.round, code)
    if not s:
        return None
    laps = s["laps"]
    cols = ["duration_sector_1", "duration_sector_2", "duration_sector_3"]
    if not all(c in laps for c in cols):
        return None
    best = []
    for col in cols:
        v = pd.to_numeric(laps[col], errors="coerce")
        if v.notna().sum() < 10:
            return None
        k = v.idxmin()
        best.append((laps.loc[k, "code"], float(v.loc[k])))
    ideal = sum(t for _, t in best)
    fl = pd.to_numeric(laps["lap_duration"], errors="coerce")
    kf = fl.idxmin()
    pole = float(fl.loc[kf])
    c = I._card(p, "Quali ideal lap", lap_time(round(ideal * 1000)), "",
                f"Best three sectors of the session: {pole - ideal:.3f} s under the fastest lap, {laps.loc[kf, 'code']} {lap_time(round(pole * 1000))}",
                f"{p.season} qualifying: OpenF1 sector times (official timing)", swipe=False)
    for i, (dc, t) in enumerate(best):
        x = 0.5 + (i - 1) * 0.28
        c.text(x, 0.56, f"SECTOR {i + 1}", 14, color=P.CYAN, weight=600, track=True)
        c.text(x, 0.50, f"{t:.3f}", 40, weight=200)
        c.text(x, 0.45, dc, 20, weight=600, color=_col(s, dc))
    return c


def _q_results(p) -> list[dict]:
    from .. import jolpica
    try:
        q = jolpica._get(f"{p.season}/{p.round}/qualifying.json?limit=100")["RaceTable"]["Races"]
    except Exception:
        return []
    if not q:
        return []
    out = []
    for x in q[0].get("QualifyingResults", []):
        out.append({"code": x["Driver"].get("code"), "pos": int(x["position"]), "team": x["Constructor"]["name"],
                    "q1": x.get("Q1"), "q2": x.get("Q2"), "q3": x.get("Q3")})
    return out


def _ms(t):
    if not t:
        return None
    m, _, sec = t.rpartition(":")
    try:
        return (int(m or 0) * 60 + float(sec)) * 1000
    except ValueError:
        return None


def q_knockouts(p, code: str = "Q"):
    res = _q_results(p)
    if len(res) < 15:
        return None
    s = session(p.season, p.round, code) or {"colors": {}}
    q1 = [r for r in res if not r["q2"]]
    q2 = [r for r in res if r["q2"] and not r["q3"]]
    surprise = min(q1 + q2, key=lambda r: r["pos"]) if q1 + q2 else None
    c = I._card(p, "Who went out", str(len(q1) + len(q2)), "drivers", "knocked out in Q1 and Q2",
                f"{p.season} qualifying classification (Jolpica, official)", swipe=False)
    for col, (name, rows) in enumerate((("OUT IN Q2", q2), ("OUT IN Q1", q1))):
        x = 0.30 + col * 0.40
        c.text(x, 0.60, name, 15, color=P.CYAN, weight=600, track=True)
        for i, r in enumerate(rows[:8]):
            y = 0.555 - i * 0.045
            c.text(x - 0.12, y, f"P{r['pos']}", 15, color=P.MUTED, weight=400, ha="left")
            c.text(x - 0.03, y, r["code"], 18, color=_col(s, r["code"]), weight=600, ha="left")
            t = r["q2"] or r["q1"] or ""
            c.text(x + 0.15, y, t, 15, weight=300, ha="right")
    return c


def q_teammates(p, code: str = "Q"):
    res = _q_results(p)
    if len(res) < 15:
        return None
    s = session(p.season, p.round, code) or {"colors": {}}
    by: dict = {}
    for r in res:
        by.setdefault(r["team"], []).append(r)
    rows = []
    for t, rs in by.items():
        if len(rs) < 2:
            continue
        a, b = sorted(rs, key=lambda r: r["pos"])[:2]
        part = "q3" if a["q3"] and b["q3"] else "q2" if a["q2"] and b["q2"] else "q1"
        ta, tb = _ms(a[part]), _ms(b[part])
        gap = (tb - ta) / 1000 if ta and tb else None
        rows.append((t, a, b, gap, part.upper()))
    rows.sort(key=lambda x: x[1]["pos"])
    if len(rows) < 5:
        return None
    close = min((r for r in rows if r[3] is not None), key=lambda r: r[3])
    c = I._card(p, "Quali teammate duels", f"{close[3]:.3f}", "s",
                f"the closest duel: {close[1]['code']} ahead of {close[2]['code']}",
                f"Gap in the last part both drivers ran. {p.season} qualifying: Jolpica (official)", swipe=False)
    for i, (t, a, b, gap, part) in enumerate(rows[:11]):
        y = 0.60 - i * 0.043
        c.text(0.08, y, t, 13, color=P.MUTED, weight=400, ha="left")
        c.text(0.46, y, f"{a['code']} P{a['pos']}", 16, color=_col(s, a["code"]), weight=600, ha="right")
        c.text(0.52, y, "beat", 12, color=P.MUTED, weight=400)
        c.text(0.58, y, f"{b['code']} P{b['pos']}", 16, weight=300, ha="left")
        c.text(0.92, y, f"{gap:.3f} s {part}" if gap is not None else "", 14, color=P.CYAN, weight=500, ha="right")
    return c


def q_teams(p, code: str = "Q"):
    s = session(p.season, p.round, code)
    if not s:
        return None
    best = s["laps"].dropna(subset=["lap_duration"]).groupby("code")["lap_duration"].min()
    team = pd.Series({c: s["teams"].get(c) for c in best.index})
    tb = best.groupby(team).min().sort_values()
    if len(tb) < 6:
        return None
    lead = tb.iloc[0]
    c = I._card(p, "Quali gap by team", f"{tb.iloc[1] - lead:.3f}", "s",
                f"{tb.index[1]} to {tb.index[0]}, best car of each team",
                f"Best lap per team in the session. {p.season} qualifying: OpenF1 (official timing)", swipe=False)
    ax = I._ax(c, [0.30, 0.15, 0.60, 0.45])
    cars = {t: next(cd for cd in best.index if team[cd] == t and best[cd] == v) for t, v in tb.items()}
    for y, (t, v) in zip(range(len(tb))[::-1], tb.items()):
        g = v - lead
        ax.barh(y, max(g, 0.004), color=_col(s, cars[t]), height=0.62)
        ax.text(-0.01, y, t, ha="right", va="center", fontsize=13, color=P.TEXT, family=P.FONT, weight=500, transform=ax.get_yaxis_transform())
        ax.text(g + 0.02, y, ("FASTEST" if GRID_POLE.get((p.season, p.round)) else "POLE") if g == 0 else f"+{g:.3f}", va="center", fontsize=13, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(0, (tb.iloc[-1] - lead) * 1.25 + 0.05)
    return c


def q_evolution(p, code: str = "Q"):
    res = _q_results(p)
    if len(res) < 10:
        return None
    best = {}
    for part in ("q1", "q2", "q3"):
        v = [(_ms(r[part]), r["code"]) for r in res if _ms(r[part])]
        if v:
            best[part] = min(v)
    if len(best) < 3:
        return None
    gain = (best["q1"][0] - best["q3"][0]) / 1000
    c = I._card(p, "Track evolution", f"{gain:.3f}", "s faster",
                "from the best Q1 lap to the best Q3 lap, as rubber goes down and fuel and tyres change",
                f"Fastest lap of each part. {p.season} qualifying: Jolpica (official)", swipe=False)
    for i, part in enumerate(("q1", "q2", "q3")):
        x = 0.5 + (i - 1) * 0.28
        t, dc = best[part]
        c.text(x, 0.56, part.upper(), 16, color=P.CYAN, weight=600, track=True)
        c.text(x, 0.50, lap_time(round(t)), 34, weight=200)
        c.text(x, 0.45, dc, 18, weight=600, color=_col(session(p.season, p.round, code) or {"colors": {}}, dc))
    return c


def practice_combined(p):
    rows = []
    for code in PRACTICE:
        s = session(p.season, p.round, code)
        if not s:
            continue
        b = s["laps"].dropna(subset=["lap_duration"]).groupby("code")["lap_duration"].min()
        for dc, t in b.items():
            rows.append((dc, t, code, s["colors"].get(dc, P.CYAN)))
    if len(rows) < 20:
        return None
    df = pd.DataFrame(rows, columns=["code", "t", "fp", "col"]).sort_values("t").drop_duplicates("code").head(10)
    lead = df["t"].iloc[0]
    c = I._card(p, "All practice, best laps", lap_time(round(lead * 1000)), "",
                f"{df['code'].iloc[0]} quickest across FP1 to FP3 ({df['fp'].iloc[0]})",
                f"Best lap per driver across all practice sessions, top 10. {p.season}: OpenF1 (official timing)", swipe=False)
    ax = I._ax(c, [0.20, 0.15, 0.70, 0.45])
    for y, (_, r) in zip(range(len(df))[::-1], df.iterrows()):
        g = r["t"] - lead
        ax.barh(y, max(g, 0.004), color=r["col"], height=0.62)
        ax.text(-0.01, y, f"{r['code']}  {r['fp']}", ha="right", va="center", fontsize=13, color=P.TEXT, family=P.FONT, weight=600,
                transform=ax.get_yaxis_transform())
        ax.text(g + 0.02, y, "BEST" if g == 0 else f"+{g:.3f}", va="center", fontsize=13, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(0, (df["t"].iloc[-1] - lead) * 1.25 + 0.05)
    return c


# ---------------------------------------------------------------- race day: P2 scenarios

RACE_PTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]


def p2_drivers(p):
    from .extras import _std
    st = _std(p)
    d = st["drivers"]
    if len(d) < 3:
        return None
    a, b = d[1], d[2]                                   # P2 and P3 now
    gap = a["pts"] - b["pts"]
    fins = list(range(1, 11)) + [None]
    pts = lambda f: RACE_PTS[f - 1] if f else 0
    c = I._card(p, "Tonight: who leaves P2?", f"{gap:.0f}", "point lead" if gap == 1 else "points lead",
                f"{a['code']} over {b['code']}. Cell = who is P2 after Las Vegas for each pair of finishes",
                f"Official standings after round {st['after_round']} (Jolpica); race points 25 to 1. Ties: countback", swipe=False)
    ax = I._ax(c, [0.20, 0.14, 0.70, 0.46])
    import matplotlib.colors as mc
    grid = np.zeros((len(fins), len(fins)))
    for i, fa in enumerate(fins):
        for j, fb in enumerate(fins):
            grid[i, j] = 1 if a["pts"] + pts(fa) > b["pts"] + pts(fb) else (-1 if a["pts"] + pts(fa) < b["pts"] + pts(fb) else 0)
    cm = mc.ListedColormap(["#EF4444", "#2A3242", P.CYAN])
    ax.imshow(grid, cmap=cm, vmin=-1, vmax=1, aspect="auto")
    lab = [str(f) for f in fins[:-1]] + ["out"]
    ax.set_xticks(range(len(fins)), lab, fontsize=11, color=P.TEXT)
    ax.set_yticks(range(len(fins)), lab, fontsize=11, color=P.TEXT)
    ax.set_xlabel(f"{b['code']} finishes", color=P.MUTED, fontsize=12, family=P.FONT)
    ax.set_ylabel(f"{a['code']} finishes", color=P.MUTED, fontsize=12, family=P.FONT)
    c.text(0.30, 0.625, f"{a['code']} KEEPS P2", 13, color=P.CYAN, weight=600, track=True)
    c.text(0.70, 0.625, f"{b['code']} TAKES P2", 13, color="#EF4444", weight=600, track=True)
    return c


def p2_teams(p):
    from .extras import _std
    st = _std(p)
    t = st["teams"]
    if len(t) < 3:
        return None
    a, b = t[1], t[2]
    gap = a["pts"] - b["pts"]
    after = (st["races_left"] - 1) * 43
    need = after - gap + 1                              # what b must outscore a by tonight to keep the fight open
    alive = gap - after                                 # b must outscore a by at least this to avoid a being sealed
    c = I._card(p, "Tonight: teams P2", f"{max(alive, 0):.0f}", "points",
                f"{b['name']} must outscore {a['name']} by this much tonight to keep P2 open" if alive > 0
                else f"P2 stays open after tonight whatever happens: {after} points still to play",
                f"Official standings after round {st['after_round']} (Jolpica). A team can score up to 43 per race", swipe=False)
    ax = I._ax(c, [0.15, 0.25, 0.70, 0.22])
    ax.barh(0, 43, color="#2A3242", height=0.5)
    if alive > 0:
        ax.barh(0, alive, color=P.CYAN, height=0.5)
        ax.text(alive, 0.45, f"needed: {alive:.0f}", ha="center", fontsize=14, color=P.CYAN, family=P.FONT, weight=600)
    ax.text(43, -0.45, "43: the most a team can outscore another by in one race", ha="right", fontsize=12, color=P.MUTED, family=P.FONT)
    ax.set_xlim(0, 45), ax.set_ylim(-0.8, 0.8)
    ax.set_xticks([]), ax.set_yticks([])
    return c


def available(p) -> list[tuple[str, object]]:
    """(content name, card function) for every practice card whose data is in, in session order."""
    out = []
    _P_SEASON[:] = [p.season, p.round]
    for code in PRACTICE:
        try:
            if not session(p.season, p.round, code):
                continue
        except Exception as e:
            log.warning("practice %s unavailable: %s", code, e)
            continue
        kinds = [("fastest", fastest), ("trap", trap), ("mileage", mileage)] + ([("longruns", longruns)] if code == "FP2" else [])
        for k, f in kinds:
            out.append((f"{code}_{k}", f))
    if all(_safe(code) for code in PRACTICE):
        out.append(("PRACTICE_combined", None))
    if _safe("Q"):
        for k in ("trap", "ideal", "knockouts", "teammates", "teams", "evolution", "sets"):
            out.append((f"Q_{k}", None))
        out += [("RACEDAY_drivers", None), ("RACEDAY_teams", None)]
    return out


def _safe(code: str) -> bool:
    try:
        return bool(session(_P_SEASON[0], _P_SEASON[1], code)) if _P_SEASON else False
    except Exception:
        return False


_P_SEASON: list = []


def card_path(p, name: str, out):
    P.set_event(p)
    code, k = name.split("_", 1)
    if code == "PRACTICE":
        c = practice_combined(p)
    elif code == "RACEDAY":
        c = p2_drivers(p) if k == "drivers" else p2_teams(p)
    elif code == "Q":
        f = {"trap": trap, "ideal": q_ideal, "knockouts": q_knockouts, "teammates": q_teammates, "teams": q_teams,
             "evolution": q_evolution, "sets": mileage}[k]
        c = f(p, "Q")
    else:
        f = {"fastest": fastest, "trap": trap, "mileage": mileage, "longruns": longruns}[k]
        c = f(p, code)
    if c is None:
        raise ValueError(f"no data for {name}")
    return c.save(out / f"live_{name}.jpg")
