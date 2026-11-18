"""More race week story cards, each posted once (Michel, 17 Nov: fill every hour, no duplicates).

  craft     last year's race at this circuit: lap 1, pit window, fastest pit lane times by team, longest
            stint, tyre compound share, race trace of the top 5, winning margin, cars not classified
  champ     live standings: fights for P3 (drivers, constructors), midfield table, wins, teammate battles
  circuit   every race here since the circuit joined: pole conversion, winners' grid slots, fastest laps

Sources: Jolpica (official classification, lap by lap positions, pit stops, standings) and OpenF1 (pit lane
times, team names). Every card names its source. A card whose data is missing is skipped, never guessed.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import insights as I
from . import preview as P
from .gp_facts import COMPOUND_COLOR
from .render import lap_time

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- data

def _ms(s: str | None) -> float | None:
    if not s:
        return None
    m, _, sec = s.rpartition(":")
    try:
        return (int(m or 0) * 60 + float(sec)) * 1000
    except ValueError:
        return None


@lru_cache(maxsize=4)
def craft_data(season: int, rnd: int, title: str) -> dict:
    from .. import jolpica
    from ..openf1 import OpenF1
    d = I.gather(season, rnd, title)
    out: dict = {}
    try:
        cid = next(e["circuit_id"] for e in jolpica.events(season) if e["round"] == rnd)
        out["circuit_id"] = cid
        ref = season - 1
        prev = next(e for e in jolpica.events(ref) if e["circuit_id"] == cid)
        res = jolpica._get(f"{ref}/{prev['round']}/results.json?limit=100")["RaceTable"]["Races"][0]["Results"]
        out["results"] = [{"code": x["Driver"].get("code"), "pos_text": x.get("positionText"), "grid": int(x.get("grid") or 0),
                           "status": x.get("status"), "laps": int(x.get("laps") or 0),
                           "time": (x.get("Time") or {}).get("time"), "team": x["Constructor"]["name"]} for x in res]
        # lap by lap positions (official), paged
        laps, off = [], 0
        while True:
            r = jolpica._get(f"{ref}/{prev['round']}/laps.json?limit=100&offset={off}")
            races = r["RaceTable"]["Races"]
            if not races:
                break
            for lp in races[0]["Laps"]:
                for t in lp["Timings"]:
                    laps.append((int(lp["number"]), t["driverId"], int(t["position"])))
            off += 100
            if off >= int(r.get("total", 0)):
                break
        ids = {x["Driver"]["driverId"]: x["Driver"].get("code") for x in res}
        out["positions"] = [(n, ids.get(i), p) for n, i, p in laps]
    except Exception as e:
        log.warning("craft data unavailable: %s", e)
    try:                                           # pit lane time by team (OpenF1)
        oc = OpenF1()
        ck = None
        from ..__main__ import schedule
        sess = [s for s in schedule(oc, season) if s["round"] == rnd]
        ck = int(sess[0]["circuit_key"])
        rs = oc.frame("sessions", year=season - 1, circuit_key=ck, session_name="Race")
        sk = int(rs.iloc[0]["session_key"])
        pit = oc.frame("pit", session_key=sk)
        drv = oc.frame("drivers", session_key=sk)
        team = {int(r["driver_number"]): r["team_name"] for _, r in drv.iterrows()}
        col = "lane_duration" if "lane_duration" in pit and pit["lane_duration"].notna().any() else "pit_duration"
        pit["lane"] = pd.to_numeric(pit[col], errors="coerce")
        pit = pit[(pit["lane"] > 10) & (pit["lane"] < 60)]
        pit["team"] = pit["driver_number"].map(lambda n: team.get(int(n)))
        out["crews"] = (pit.groupby("team")["lane"].agg(["min", "median", "count"]).sort_values("min").reset_index()
                        .to_dict("records"))
        out["team_colors"] = {r["team_name"]: "#" + str(r.get("team_colour") or "888888").lstrip("#") for _, r in drv.iterrows()}
    except Exception as e:
        log.warning("pit crew data unavailable: %s", e)
    return out


@lru_cache(maxsize=4)
def circuit_history(season: int, rnd: int) -> list[dict]:
    """Every race at this circuit before this season (Jolpica): pole, winner and grid, fastest lap."""
    from .. import jolpica
    cid = next(e["circuit_id"] for e in jolpica.events(season) if e["round"] == rnd)
    out = []
    for y in range(max(1950, season - 6), season):
        ev = next((e for e in jolpica.events(y) if e["circuit_id"] == cid), None)
        if not ev:
            continue
        res = jolpica._get(f"{y}/{ev['round']}/results.json?limit=100")["RaceTable"]["Races"][0]["Results"]
        q = jolpica._get(f"{y}/{ev['round']}/qualifying.json?limit=100")["RaceTable"]["Races"]
        pole = q[0]["QualifyingResults"][0]["Driver"].get("code") if q and q[0].get("QualifyingResults") else None
        win = next(x for x in res if x["position"] == "1")
        pole_res = next((x for x in res if x["Driver"].get("code") == pole), None)
        fl = [x for x in res if (x.get("FastestLap") or {}).get("rank") == "1"]
        out.append({"year": y, "pole": pole, "pole_finish": pole_res.get("positionText") if pole_res else None,
                    "winner": win["Driver"].get("code"), "winner_grid": int(win.get("grid") or 0),
                    "fl_code": fl[0]["Driver"].get("code") if fl else None,
                    "fl_time": fl[0]["FastestLap"]["Time"]["time"] if fl else None,
                    "fl_lap": int(fl[0]["FastestLap"]["lap"]) if fl else None})
    return out


def _std(p) -> dict:
    from . import news
    return _standings(p.season)


@lru_cache(maxsize=2)
def _standings(season: int) -> dict:
    from . import news
    return news.standings(season)


def _src(ref) -> str:
    return f"{ref} race"


# ---------------------------------------------------------------- craft cards

def lap_one(p, d, **kw):
    c_ = craft_data(p.season, p.round, p.title)
    pos = c_.get("positions") or []
    res = {r["code"]: r for r in c_.get("results") or []}
    l1 = {code: ps for n, code, ps in pos if n == 1}
    rows = [(code, res[code]["grid"] or 20, l1[code]) for code in l1 if code in res]
    if len(rows) < 10:
        return None
    rows = [(c, g, q, g - q) for c, g, q in rows]
    rows.sort(key=lambda r: -r[3])
    best, worst = rows[0], rows[-1]
    ref = p.season - 1
    c = I._card(p, f"{ref} lap 1", f"+{best[3]}", "places", f"{best[0]}: P{best[1]} to P{best[2]} in one lap. Worst: {worst[0]}, {worst[3]:+d}",
                f"Grid slot vs position at the end of lap 1. {_src(ref)}: official lap chart (Jolpica)", **kw)
    ax = I._ax(c, [0.12, 0.15, 0.80, 0.45])
    ys = np.arange(len(rows))[::-1]
    for y, (code, g, q, dlt) in zip(ys, rows):
        ax.barh(y, dlt, color=P.CYAN if dlt > 0 else "#EF4444" if dlt < 0 else "#2A3242", height=0.7)
        ax.text(-0.3 if dlt >= 0 else 0.3, y, code, ha="right" if dlt >= 0 else "left", va="center", fontsize=11,
                color=I.team(d, code), family=P.FONT, weight=600)
    ax.axvline(0, color="#3A4458", lw=0.8)
    ax.set_yticks([])
    m = max(abs(r[3]) for r in rows) + 2
    ax.set_xlim(-m, m)
    ax.set_xlabel("places gained on lap 1", color=P.MUTED, fontsize=12, family=P.FONT)
    return c


def pit_window(p, d, **kw):
    from .. import jolpica
    ref = p.season - 1
    cl = d.get("classified") or []
    plan = d.get("plan") or {}
    first = {r["code"]: plan[r["code"]][0][2] for r in cl if r["code"] in plan and len(plan[r["code"]]) > 1}
    if len(first) < 8:
        return None
    v = np.array(sorted(first.values()))
    lo, hi = int(np.percentile(v, 25)), int(np.percentile(v, 75))
    win = cl[0]["code"]
    c = I._card(p, f"{ref} pit window", f"{lo} to {hi}", "laps",
                f"Half the field made its first stop in this window. {win} stopped on lap {first.get(win, '?')}",
                f"First stop of each classified finisher (in lap). {_src(ref)}: OpenF1 stints, official pit stops", **kw)
    ax = I._ax(c, [0.10, 0.17, 0.82, 0.40])
    total = d.get("laps") or int(v.max()) + 5
    cnt = pd.Series(v).value_counts().sort_index()
    ax.axvspan(lo - 0.5, hi + 0.5, color=P.CYAN, alpha=0.10)
    ax.bar(cnt.index, cnt.values, width=0.8, color=P.CYAN)
    if win in first:
        ax.annotate(win, (first[win], cnt.get(first[win], 0)), xytext=(0, 14), textcoords="offset points", ha="center",
                    color=I.team(d, win), fontsize=14, family=P.FONT, weight=700)
    ax.set_xlim(0, total + 1)
    ax.set_yticks([])
    ax.set_xlabel("lap", color=P.MUTED, fontsize=12, family=P.FONT)
    return c


def pit_crews(p, d, **kw):
    c_ = craft_data(p.season, p.round, p.title)
    crews = [r for r in c_.get("crews") or [] if r["team"]]
    if len(crews) < 5:
        return None
    ref = p.season - 1
    b = crews[0]
    c = I._card(p, f"{ref} quickest through the pits", f"{b['min']:.1f}", "s",
                f"{b['team']}: best pit lane time, entry to exit",
                f"Best and median pit lane time per team, {sum(int(r['count']) for r in crews)} stops. {_src(ref)}: OpenF1 pit data", **kw)
    ax = I._ax(c, [0.30, 0.15, 0.60, 0.45])
    rows = crews[:10][::-1]
    ys = np.arange(len(rows))
    lo = min(r["min"] for r in rows) - 0.8
    for y, r in zip(ys, rows):
        col = c_.get("team_colors", {}).get(r["team"], P.CYAN)
        ax.barh(y, r["min"] - lo, left=lo, color=col, height=0.62)
        ax.plot([r["median"]], [y], "|", color=P.TEXT, ms=14, mew=2)
        ax.text(lo - 0.15, y, r["team"], ha="right", va="center", fontsize=13, color=P.TEXT, family=P.FONT, weight=500)
        ax.text(r["min"] + 0.1 + (r["median"] - r["min"]) * 0, y, "", fontsize=1)
    ax.set_yticks([])
    ax.set_xlim(lo, max(r["median"] for r in rows) + 0.6)
    ax.set_xlabel("seconds in the pit lane (bar: best, tick: median)", color=P.MUTED, fontsize=12, family=P.FONT)
    return c


def longest_stint(p, d, **kw):
    cl = d.get("classified") or []
    plan = d.get("plan") or {}
    st = [(r["code"], cpd, b - a + 1, a, b) for r in cl if r["code"] in plan for cpd, a, b in plan[r["code"]]]
    if not st:
        return None
    st.sort(key=lambda x: -x[2])
    top = st[:6]
    ref = p.season - 1
    b = top[0]
    c = I._card(p, f"{ref} longest stint", str(b[2]), "laps on one set",
                f"{b[0]} on {b[1].lower()}s, laps {b[3]} to {b[4]}",
                f"Longest stints of the classified finishers. {_src(ref)}: OpenF1 stints, official pit stops", **kw)
    ax = I._ax(c, [0.18, 0.17, 0.74, 0.40])
    for y, (code, cpd, n, a, bb) in zip(range(len(top))[::-1], top):
        ax.barh(y, n, color=COMPOUND_COLOR.get(cpd, "#666"), height=0.6)
        ax.text(-0.8, y, code, ha="right", va="center", fontsize=15, color=I.team(d, code), family=P.FONT, weight=600)
        ax.text(n + 0.6, y, f"{n}", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([])
    ax.set_xlim(0, (d.get("laps") or top[0][2]) + 4)
    ax.set_xlabel("laps", color=P.MUTED, fontsize=12, family=P.FONT)
    return c


def compound_share(p, d, **kw):
    cl = d.get("classified") or []
    plan = d.get("plan") or {}
    tot: dict = {}
    for r in cl:
        for cpd, a, b in plan.get(r["code"], []):
            tot[cpd] = tot.get(cpd, 0) + (b - a + 1)
    n = sum(tot.values())
    if n < 100:
        return None
    share = {k: 100 * v / n for k, v in sorted(tot.items(), key=lambda x: -x[1])}
    top = next(iter(share))
    ref = p.season - 1
    c = I._card(p, f"{ref} tyre usage", f"{share[top]:.0f}", f"% of laps on {top.lower()}s",
                ", ".join(f"{k.lower()} {v:.0f}%" if v >= 0.5 else f"{k.lower()} under 1%" for k, v in share.items()),
                f"All laps of the classified finishers, {n} in total. {_src(ref)}: OpenF1 stints", **kw)
    ax = I._ax(c, [0.10, 0.30, 0.80, 0.10])
    x = 0
    for k, v in share.items():
        ax.barh(0, v, left=x, color=COMPOUND_COLOR.get(k, "#666"), height=1)
        if v > 6:
            ax.text(x + v / 2, 0, f"{k[0]}  {v:.0f}%", ha="center", va="center", fontsize=16, color="#0B0E14", family=P.FONT, weight=700)
        x += v
    ax.set_xlim(0, 100)
    ax.set_xticks([]), ax.set_yticks([])
    return c


def race_trace(p, d, **kw):
    c_ = craft_data(p.season, p.round, p.title)
    pos = c_.get("positions") or []
    cl = [r["code"] for r in (d.get("classified") or [])[:5]]
    if not pos or len(cl) < 3:
        return None
    df = pd.DataFrame(pos, columns=["lap", "code", "pos"])
    win = cl[0]
    led = int(((df["code"] == win) & (df["pos"] == 1)).sum())
    total = int(df["lap"].max())
    leaders = df[df["pos"] == 1]["code"].nunique()
    ref = p.season - 1
    c = I._card(p, f"{ref} race trace", f"{led} of {total}", "laps led",
                f"by the winner, {win}. {leaders} different leader{'s' if leaders != 1 else ''} in the race",
                f"Position at the end of each lap, top 5 finishers. {_src(ref)}: official lap chart (Jolpica)", **kw)
    ax = I._ax(c, [0.10, 0.15, 0.78, 0.45])
    for code in cl:
        s = df[df["code"] == code].sort_values("lap")
        col = I.team(d, code)
        ax.plot(s["lap"], s["pos"], color=col, lw=2.4)
        ax.text(total + 0.8, s["pos"].iloc[-1], code, color=col, fontsize=13, family=P.FONT, weight=700, va="center")
    ax.set_ylim(max(12, int(df[df["code"].isin(cl)]["pos"].max()) + 1), 0.5)
    ax.set_yticks([1, 5, 10])
    ax.set_yticklabels(["P1", "P5", "P10"], color=P.MUTED, fontsize=12)
    ax.set_xlim(0, total + 4)
    ax.set_xlabel("lap", color=P.MUTED, fontsize=12, family=P.FONT)
    return c


def margin(p, d, **kw):
    c_ = craft_data(p.season, p.round, p.title)
    res = c_.get("results") or []
    gaps = []
    for r in res:
        t = r.get("time")
        if t and t.startswith("+") and str(r["pos_text"]).isdigit() and r.get("status") == "Finished":
            try:
                gaps.append((r["code"], float(t.strip("+").rstrip("s"))))
            except ValueError:
                pass
    if not gaps:
        return None
    gaps = gaps[:9]
    ref = p.season - 1
    win = next(r["code"] for r in res if r["pos_text"] == "1")
    c = I._card(p, f"{ref} winning margin", f"{gaps[0][1]:.3f}", "s",
                f"{win} over {gaps[0][0]} at the flag", f"Gaps to the winner, cars on the lead lap. {_src(ref)}: official results (Jolpica)", **kw)
    ax = I._ax(c, [0.18, 0.15, 0.72, 0.45])
    rows = [(win, 0.0)] + gaps
    for y, (code, g) in zip(range(len(rows))[::-1], rows):
        ax.barh(y, g, color=I.team(d, code), height=0.6)
        ax.text(-0.5, y, code, ha="right", va="center", fontsize=14, color=I.team(d, code), family=P.FONT, weight=600)
        ax.text(g + 0.5, y, "WINNER" if g == 0 else f"+{g:.1f} s", va="center", fontsize=13, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([])
    ax.set_xlim(0, rows[-1][1] * 1.2 + 1)
    return c


def unclassified(p, d, **kw):
    c_ = craft_data(p.season, p.round, p.title)
    res = c_.get("results") or []
    out = [r for r in res if not str(r["pos_text"]).isdigit()]
    if not res:
        return None
    ref = p.season - 1
    c = I._card(p, f"{ref} attrition", str(len(out)), "of 20 not classified",
                f"{len(res) - len(out)} cars took a classified finish", f"Official classification and status. {_src(ref)}: Jolpica", **kw)
    for i, r in enumerate(out[:8]):
        y = 0.56 - i * 0.055
        why = "DISQUALIFIED" if r["pos_text"] == "D" else (r["status"] or "").upper()
        c.text(0.18, y, r["code"], 22, weight=500, ha="left", color=I.team(d, r["code"]))
        c.text(0.32, y, r["team"], 16, color=P.MUTED, weight=300, ha="left")
        c.text(0.86, y, why + (f", LAP {r['laps']}" if r["pos_text"] != "D" else ""), 14, color="#EF4444" if r["pos_text"] == "D" else "#FFC107",
               weight=600, ha="right", track=False)
    if not out:
        c.text(0.5, 0.45, "EVERY CAR FINISHED", 26, color=P.CYAN, weight=600, track=True)
    return c


CRAFT = [lap_one, pit_window, pit_crews, longest_stint, compound_share, race_trace, margin, unclassified]


# ---------------------------------------------------------------- championship cards

def p3_drivers(p, d, **kw):
    from . import news
    return news.title_math(p, _std(p), False, place=3)


def p3_teams(p, d, **kw):
    from . import news
    return news.title_math(p, _std(p), True, place=3)


def midfield(p, d, **kw):
    from . import news
    st = _std(p)
    rows = st["teams"][4:11]
    if len(rows) < 4:
        return None
    c = I._card(p, "Constructors midfield", news.fmt(rows[0]["pts"] - rows[1]["pts"]), f"pts between P5 and P6",
                f"Every place is worth prize money. {st['races_left']} races left, 43 points max each",
                f"Official standings after round {st['after_round']} (Jolpica)", swipe=False)
    for i, r in enumerate(rows):
        y = 0.58 - i * 0.058
        c.text(0.14, y, f"P{r['pos']}", 20, color=P.CYAN, weight=600, ha="left")
        c.text(0.24, y, r["name"], 20, weight=400, ha="left")
        c.text(0.84, y, news.fmt(r["pts"]), 24, weight=300, ha="right")
        if i < len(rows) - 1:
            c.rule(0.14, 0.86, y - 0.029, color="#1E2533", lw=0.6)
    return c


def wins(p, d, **kw):
    st = _std(p)
    rows = [r for r in st["drivers"] if r["wins"] > 0]
    if not rows:
        return None
    rows.sort(key=lambda r: -r["wins"])
    done = st["after_round"]
    c = I._card(p, f"{p.season} winners", str(rows[0]["wins"]), f"of {done} races",
                f"won by {rows[0]['name']}. {len(rows)} different winners so far",
                f"Official standings after round {done} (Jolpica)", swipe=False)
    ax = I._ax(c, [0.20, 0.17, 0.70, 0.40])
    for y, r in zip(range(len(rows))[::-1], rows):
        col = d.get("colors", {}).get(r["code"], P.CYAN)
        ax.barh(y, r["wins"], color=col, height=0.6)
        ax.text(-0.15, y, r["code"], ha="right", va="center", fontsize=15, color=P.TEXT, family=P.FONT, weight=600)
        ax.text(r["wins"] + 0.15, y, str(r["wins"]), va="center", fontsize=16, color=P.TEXT, family=P.FONT, weight=300)
    ax.set_yticks([]), ax.set_xticks([])
    ax.set_xlim(0, rows[0]["wins"] * 1.15)
    return c


def teammates(p, d, **kw):
    from . import news
    st = _std(p)
    by: dict = {}
    for r in st["drivers"]:
        by.setdefault(r["team"], []).append(r)
    pairs = []
    for t in [x["name"] for x in st["teams"]]:
        rs = sorted(by.get(t, []), key=lambda r: -r["pts"])
        if len(rs) >= 2 and rs[0]["pts"] + rs[1]["pts"] > 0:
            pairs.append((t, rs[0], rs[1]))
    if len(pairs) < 5:
        return None
    pairs = pairs[:8]
    big = max(pairs, key=lambda x: x[1]["pts"] - x[2]["pts"])
    c = I._card(p, "Teammate battles", news.fmt(big[1]["pts"] - big[2]["pts"]), "points",
                f"{big[1]['code']} over {big[2]['code']}, the biggest gap inside one team",
                f"Points this season, top 8 teams. Official standings after round {st['after_round']} (Jolpica)", swipe=False)
    for i, (t, a, b) in enumerate(pairs):
        y = 0.59 - i * 0.052
        tot = a["pts"] + b["pts"]
        c.text(0.10, y, t, 15, color=P.MUTED, weight=400, ha="left")
        c.text(0.40, y, f"{a['code']} {news.fmt(a['pts'])}", 16, weight=600, ha="right")
        x0, w = 0.42, 0.34
        share = a["pts"] / tot if tot else 0.5
        c.fig.add_artist(plt.Rectangle((x0, y - 0.008), w * share, 0.016, transform=c.fig.transFigure, color=P.CYAN))
        c.fig.add_artist(plt.Rectangle((x0 + w * share, y - 0.008), w * (1 - share), 0.016, transform=c.fig.transFigure, color="#2A3242"))
        c.text(0.78, y, f"{news.fmt(b['pts'])} {b['code']}", 16, weight=300, ha="left")
    return c


CHAMP = [p3_drivers, p3_teams, midfield, wins, teammates]


# ---------------------------------------------------------------- circuit history

def pole_conversion(p, d, **kw):
    h = circuit_history(p.season, p.round)
    if len(h) < 2:
        return None
    won = sum(1 for x in h if x["pole"] and x["pole"] == x["winner"])
    c = I._card(p, "Does pole win here?", f"{won} of {len(h)}", "races",
                "won from pole position", f"Every race at this circuit since {h[0]['year']}. Official results (Jolpica)", swipe=False)
    for i, x in enumerate(h):
        xx = 0.5 + (i - (len(h) - 1) / 2) * 0.28
        c.text(xx, 0.55, str(x["year"]), 34, weight=200)
        c.text(xx, 0.49, f"POLE  {x['pole'] or '?'}", 15, color=P.CYAN, weight=600, track=True)
        fin = x["pole_finish"]
        c.text(xx, 0.45, "WON" if fin == "1" else "DISQUALIFIED" if fin == "D" else f"FINISHED P{fin}" if fin and fin.isdigit() else "DID NOT FINISH",
               15, color=P.GOLD if fin == "1" else P.MUTED, weight=600, track=True)
        c.text(xx, 0.39, f"winner {x['winner']}", 16, weight=300)
    return c


def winners_grid(p, d, **kw):
    h = circuit_history(p.season, p.round)
    if len(h) < 2:
        return None
    lowest = max(h, key=lambda x: x["winner_grid"] or 0)
    c = I._card(p, "Where the winners started", f"P{lowest['winner_grid']}", "on the grid",
                f"the furthest back a winner started here: {lowest['winner']}, {lowest['year']}",
                f"Every race at this circuit since {h[0]['year']}. Official results (Jolpica)", swipe=False)
    for i, x in enumerate(h):
        xx = 0.5 + (i - (len(h) - 1) / 2) * 0.28
        c.text(xx, 0.55, str(x["year"]), 34, weight=200)
        c.text(xx, 0.49, x["winner"], 22, weight=600, color=I.team(d, x["winner"]))
        c.text(xx, 0.43, f"STARTED P{x['winner_grid']}", 15, color=P.CYAN if x is lowest else P.MUTED, weight=600, track=True)
    return c


def fastest_laps(p, d, **kw):
    h = [x for x in circuit_history(p.season, p.round) if x["fl_time"]]
    if len(h) < 2:
        return None
    best = min(h, key=lambda x: _ms(x["fl_time"]))
    c = I._card(p, "Fastest race laps here", best["fl_time"], "",
                f"{best['fl_code']}, {best['year']}, lap {best['fl_lap']}: the quickest race lap at this circuit",
                f"Fastest lap of each race since {h[0]['year']}. Official results (Jolpica)", swipe=False)
    for i, x in enumerate(h):
        y = 0.55 - i * 0.075
        c.text(0.20, y, str(x["year"]), 30, weight=200, ha="left")
        c.text(0.40, y, x["fl_code"], 22, weight=600, ha="left")
        c.text(0.80, y, f"{x['fl_time']}  (lap {x['fl_lap']})", 20, weight=300, ha="right", color=P.CYAN if x is best else P.TEXT)
    return c


CIRCUIT = [pole_conversion, winners_grid, fastest_laps]

from .learn import LEARN  # noqa: E402

GROUPS = {"craft": CRAFT, "champ": CHAMP, "circuit": CIRCUIT, "learn": LEARN}


def by_name(name: str):
    for fns in GROUPS.values():
        for f in fns:
            if f.__name__ == name:
                return f
    raise KeyError(name)


def card_path(p, name: str, out):
    P.set_event(p)
    d = I.gather(p.season, p.round, p.title)
    f = by_name(name)
    c = f(p, d, swipe=False)
    if c is None:
        raise ValueError(f"no data for {name}")
    return c.save(out / f"extra_{name}.jpg")
