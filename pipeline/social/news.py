"""Race weekend news cards: championship math, grid penalties, power unit usage, upgrades.

Michel, 17 Nov: "start adding news about the weekend too: any penalties coming up, PU changes, upgrades for
the teams, calculations on what it takes to seal #2 in the championship for the drivers and the
constructors championship. Show me templates before we start the postings."

Championship math is computed from the official standings (Jolpica) and the remaining calendar, so it
is always current. Penalties, power unit counts and upgrades come from the FIA documents of the weekend;
they are entered as checked facts (gp_facts.NEWS, filled by the research task with a source per item)
and a card is only drawn when its facts exist.

Points (2026 sporting regulations, unchanged from 2025): race 25 18 15 12 10 8 6 4 2 1, sprint 8 to 1,
no fastest lap point.
"""
from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt

from . import preview as P
from .render import H_POST

log = logging.getLogger(__name__)

RACE_MAX, SPRINT_MAX = 25, 8
TEAM_RACE_MAX, TEAM_SPRINT_MAX = 25 + 18, 8 + 7


# ---------------------------------------------------------------- data

def standings(season: int, after_round: int | None = None) -> dict:
    """Driver and constructor standings, and what is still to be scored."""
    from .. import jolpica
    rnd = f"/{after_round}" if after_round else ""
    ds = jolpica._get(f"{season}{rnd}/driverStandings.json?limit=40")["StandingsTable"]["StandingsLists"][0]
    cs = jolpica._get(f"{season}{rnd}/constructorStandings.json?limit=20")["StandingsTable"]["StandingsLists"][0]
    done = int(ds["round"])
    races = jolpica._get(f"{season}.json?limit=100")["RaceTable"]["Races"]
    left = [r for r in races if int(r["round"]) > done]
    sprints = sum(1 for r in left if "Sprint" in r)
    return {
        "season": season, "after_round": done, "races_left": len(left), "sprints_left": sprints,
        "next": [r["raceName"] for r in left],
        "drivers": [{"pos": int(x["position"]), "code": x["Driver"].get("code"), "name": x["Driver"]["familyName"],
                     "team": x["Constructors"][0]["name"] if x.get("Constructors") else "",
                     "pts": float(x["points"]), "wins": int(x["wins"])} for x in ds["DriverStandings"]],
        "teams": [{"pos": int(x["position"]), "name": x["Constructor"]["name"], "pts": float(x["points"]),
                   "wins": int(x["wins"])} for x in cs["ConstructorStandings"]],
    }


def max_left(st: dict, team: bool) -> int:
    r, s = (TEAM_RACE_MAX, TEAM_SPRINT_MAX) if team else (RACE_MAX, SPRINT_MAX)
    return st["races_left"] * r + st["sprints_left"] * s


def max_this_weekend(st: dict, team: bool, sprint: bool) -> int:
    r, s = (TEAM_RACE_MAX, TEAM_SPRINT_MAX) if team else (RACE_MAX, SPRINT_MAX)
    return r + (s if sprint else 0)


def seal(st: dict, team: bool, place: int = 2, sprint_now: bool = False) -> dict:
    """Can the holder of `place` lose it to anyone behind? Gap to the next car vs points still available.
    Sealed when the gap is larger than everything left (a tie would go to countback: treated as not sealed).
    'need' is how much more than the next one they must score this weekend to seal it before the next race."""
    rows = st["teams" if team else "drivers"]
    me, nxt = rows[place - 1], rows[place]
    gap = me["pts"] - nxt["pts"]
    total = max_left(st, team)
    after = total - max_this_weekend(st, team, sprint_now)
    need = after - gap + 1                         # outscore the next one by this much this weekend
    ahead = rows[place - 2] if place >= 2 else None
    return {"holder": me, "next": nxt, "gap": gap, "left": total, "left_after": after,
            "sealed": gap > total, "need": max(0, int(need)), "possible_now": need <= max_this_weekend(st, team, sprint_now),
            "ahead": ahead, "ahead_gap": (ahead["pts"] - me["pts"]) if ahead else None}


def fmt(x: float) -> str:
    return f"{x:.0f}" if float(x).is_integer() else f"{x:.1f}"


# ---------------------------------------------------------------- cards

def _base(p, kicker: str, n=None, total=None):
    c = P.Card(H_POST)
    c.header(p)
    c.kicker(c.top - 0.07, kicker, n, total)
    return c


def title_math(p, st: dict, team: bool, place: int = 2, sample: bool = False):
    s = seal(st, team, place)
    who = s["holder"]["name"] if team else s["holder"]["code"]
    nxt = s["next"]["name"] if team else s["next"]["code"]
    c = _base(p, f"{'Constructors' if team else 'Drivers'} championship: P{place}")
    if s["sealed"]:
        c.number(c.top - 0.215, "SEALED", "", size=120)
        line = f"{who} cannot drop below P{place}"
    else:
        margin = s["gap"] - s["left_after"]                       # > 0: P{place} sealed unless the next one gains this much or more
        if margin > 0:
            c.number(c.top - 0.215, fmt(margin - 1), "point of slack" if margin - 1 == 1 else "points of slack", size=150)
            line = f"{who} seals P{place} here unless {nxt} outscores them by {fmt(margin)} or more"
        elif s["possible_now"]:
            c.number(c.top - 0.215, f"+{s['need']}", "points", size=150)
            line = f"{who} must outscore {nxt} by {s['need']} here to seal P{place}"
        else:
            c.number(c.top - 0.215, fmt(s["gap"]), "point ahead" if s["gap"] == 1 else "points ahead", size=150)
            line = f"Not sealed here: {s['left_after']} points still to play after {p.title.title()}"
    c.text(0.5, c.top - 0.265, line, 22, weight=300)
    rows = (st["teams"] if team else st["drivers"])[:5]
    y0 = 0.58
    lead = rows[0]["pts"]
    for i, r in enumerate(rows):
        y = y0 - i * 0.062
        name = r["name"] if team else f"{r['code']}  {r['team']}"
        hl = r["pos"] in (place, place + 1)
        col = P.TEXT if hl else P.MUTED
        c.text(0.12, y, f"P{r['pos']}", 20, color=P.CYAN if r["pos"] == place else col, weight=600, ha="left")
        c.text(0.22, y, name, 20, color=col, weight=500 if hl else 300, ha="left")
        c.text(0.80, y, fmt(r["pts"]), 24, color=col, weight=300, ha="right")
        c.text(0.90, y, "" if i == 0 else f"-{fmt(lead - r['pts'])}", 15, color=P.MUTED, weight=400, ha="right")
        if i < len(rows) - 1:
            c.rule(0.12, 0.90, y - 0.031, color="#1E2533", lw=0.6)
    left = f"{st['races_left']} races" + (f" and {st['sprints_left']} sprints" if st["sprints_left"] else "")
    c.text(0.5, 0.235, f"Gap P{place} to P{place + 1}: {fmt(s['gap'])} pts   |   still to score: {s['left']} pts ({left})", 15,
           color=P.TEXT, weight=400)
    c.text(0.5, 0.105, f"Official standings after round {st['after_round']} (Jolpica). Max {RACE_MAX if not team else TEAM_RACE_MAX} "
                       f"per race{', ' + str(SPRINT_MAX if not team else TEAM_SPRINT_MAX) + ' per sprint' if st['sprints_left'] else ''}; "
                       "ties go to countback", 12, color=P.MUTED, weight=300)
    c.footer()
    if sample:
        watermark(c)
    return c


def watermark(c):
    c.text(0.5, 0.45, "TEMPLATE  |  SAMPLE DATA", 40, color="#FF3D8B", weight=700, alpha=0.35, rotation=18)


def penalties(p, items: list[dict], sample: bool = False):
    """items: driver, team, places (int or 'BACK OF GRID' / 'PIT LANE'), reason, source."""
    c = _base(p, "Grid penalty watch")
    c.number(c.top - 0.215, str(len(items)), "drivers penalised" if len(items) != 1 else "driver penalised", size=150)
    c.text(0.5, c.top - 0.265, "Grid drops for the race, from the stewards' decisions", 22, weight=300)
    for i, it in enumerate(items[:6]):
        y = 0.58 - i * 0.075
        c.text(0.10, y, it["driver"], 24, weight=500, ha="left")
        c.text(0.10, y - 0.027, it["team"], 14, color=P.MUTED, weight=400, ha="left")
        c.text(0.42, y - 0.012, it["reason"], 16, color=P.TEXT, weight=300, ha="left")
        pl = it["places"]
        c.text(0.90, y - 0.012, f"+{pl}" if isinstance(pl, int) else pl, 24 if isinstance(pl, int) else 15,
               color="#EF4444", weight=600, ha="right")
        c.rule(0.10, 0.90, y - 0.05, color="#1E2533", lw=0.6)
    c.text(0.5, 0.105, items[0].get("source", "Source: FIA stewards' decisions") if items else "", 12, color=P.MUTED, weight=300)
    c.footer()
    if sample:
        watermark(c)
    return c


ELEMENTS = ("ICE", "TC", "MGU-K", "ES", "CE")


def pu_usage(p, rows: list[dict], allowance: dict, sample: bool = False):
    """rows: driver, counts {element: n}. Cells over the allowance in red: the next new one is a penalty."""
    c = _base(p, "Power unit count")
    over = sum(1 for r in rows if any(r["counts"].get(e, 0) >= allowance.get(e, 99) for e in ELEMENTS))
    c.number(c.top - 0.215, str(over), "drivers at the limit", size=150)
    c.text(0.5, c.top - 0.265, "One more new element for them means a grid penalty", 22, weight=300)
    xs = [0.40 + i * 0.11 for i in range(len(ELEMENTS))]
    for x, e in zip(xs, ELEMENTS):
        c.text(x, 0.60, e.replace("-", " "), 13, color=P.CYAN, weight=600)
        c.text(x, 0.577, f"max {allowance.get(e, '?')}", 11, color=P.MUTED, weight=400)
    for i, r in enumerate(rows[:8]):
        y = 0.535 - i * 0.048
        c.text(0.10, y, r["driver"], 19, weight=500, ha="left")
        for x, e in zip(xs, ELEMENTS):
            n = r["counts"].get(e, 0)
            lim = allowance.get(e, 99)
            c.text(x, y, str(n), 20, weight=400 if n < lim else 600,
                   color="#EF4444" if n > lim else "#FFC107" if n == lim else P.TEXT)
    c.text(0.5, 0.105, "Elements used this season. Source: FIA power unit usage document of the event", 12, color=P.MUTED, weight=300)
    c.footer()
    if sample:
        watermark(c)
    return c


def upgrades(p, teams: list[dict], sample: bool = False):
    """teams: team, color, items [(area, what)]. From the FIA car presentation submissions."""
    c = _base(p, "Upgrade tracker")
    n = sum(len(t["items"]) for t in teams)
    c.number(c.top - 0.215, str(n), "new parts", size=150)
    c.text(0.5, c.top - 0.265, f"declared by {len(teams)} teams for {p.title.title()}", 22, weight=300)
    y = 0.60
    for t in teams[:5]:
        c.fig.add_artist(plt.Rectangle((0.10, y - 0.012), 0.008, 0.026, transform=c.fig.transFigure, color=t.get("color", P.CYAN)))
        c.text(0.13, y, t["team"], 20, weight=600, ha="left")
        y -= 0.036
        for area, what in t["items"][:3]:
            c.text(0.13, y, area.upper(), 12, color=P.CYAN, weight=600, ha="left")
            c.text(0.30, y, what, 15, color=P.TEXT, weight=300, ha="left")
            y -= 0.03
        y -= 0.012
    c.text(0.5, 0.105, "Source: FIA car presentation submissions, published Thursday of the event", 12, color=P.MUTED, weight=300)
    c.footer()
    if sample:
        watermark(c)
    return c


# ---------------------------------------------------------------- weekend news from checked facts

def facts(p) -> dict:
    from .gp_facts import NEWS
    return NEWS.get(p.title, {}).get(p.season, {})


def available(p) -> list[str]:
    """News cards whose facts are in (gp_facts.NEWS[title][season]), in a stable order."""
    f = facts(p)
    return [k for k in ("upgrades", "pu", "penalties") if (_list_penalties(f) if k == "penalties" else f.get(k))]


def _list_penalties(f: dict) -> list[dict]:
    """Penalties still to show on the list card: a driver who already had his own story (story: True) is left
    out, under any spelling of the same entry, so the list never repeats him."""
    told = {it["driver"].upper() for it in f.get("penalties", []) if it.get("story")}
    return [it for it in f.get("penalties", []) if it["driver"].upper() not in told]


def penalty_story(p, it: dict):
    """One grid penalty explained, native 9:16 story: what happened, the rule, what it means on the grid.
    it: driver, team, color, places, why [(label, line)], engines {used, limit}, source."""
    from .render import H_REEL
    c = P.Card(H_REEL, story=True)
    c.header(p)
    c.kicker(c.top - 0.05, "Grid penalty")
    c.number(c.top - 0.15, f"+{it['places']}", "grid places", size=150, color="#EF4444")
    c.text(0.5, c.top - 0.205, it["driver"].upper(), 34, weight=600, track=True)
    c.text(0.5, c.top - 0.233, it["team"].upper(), 16, color=it.get("color", P.CYAN), weight=600, track=True)
    e = it.get("engines")
    if e:                                       # one block per combustion engine of the season, the extra one in red
        n, lim = e["used"], e["limit"]
        w, gap, y = 0.11, 0.025, c.top - 0.31
        x0 = 0.5 - (n * w + (n - 1) * gap) / 2
        for k in range(n):
            x = x0 + k * (w + gap)
            over = k >= lim
            col = "#EF4444" if over else P.CYAN
            c.fig.add_artist(plt.Rectangle((x, y), w, 0.045, transform=c.fig.transFigure, fill=over,
                                           facecolor=col if over else "none", edgecolor=col, lw=1.6, alpha=0.9))
            c.text(x + w / 2, y + 0.0225, f"ICE {k + 1}", 15, color="#0B0E14" if over else P.CYAN, weight=700)
        c.text(0.5, y - 0.022, f"Limit {lim} per driver per season", 14, color=P.MUTED, weight=400)
    y = c.top - 0.395
    for label, line in it["why"][:5]:
        c.text(0.10, y, label.upper(), 13, color=P.CYAN, weight=600, ha="left", track=True)
        c.text(0.10, y - 0.022, line, 19, color=P.TEXT, weight=300, ha="left")
        c.rule(0.10, 0.90, y - 0.04, color="#1E2533", lw=0.6)
        y -= 0.062
    c.text(0.5, c.bottom + 0.035, it["source"], 11, color=P.MUTED, weight=300)
    c.footer()
    return c


def session_story(p, it: dict, story: bool = True):
    """A session report, native 9:16 story, posted within the hour after a session even when no timing
    data is out yet (Michel, 19 Nov). With "standings" it is the v2 layout Michel asked for on 19 Nov: the
    session named clearly, then the order as CODE + car number in team colour with times, then what
    happened in a few short lines. Without it, the first layout (FP1 washout)."""
    if not it.get("standings") and not it.get("times"):
        return _session_story_v1(p, it)
    from .gp_facts import DRIVERS
    from .render import H_REEL
    c = P.Card(H_REEL, story=True) if story else P.Card(H_POST)
    k_ = 1.0 if story else 1.2                      # a little more room per line on the 4:5 feed card
    c.header(p)
    y = c.top - 0.065 * k_
    c.text(0.06, y, it["session"], 64, color=P.CYAN, weight=700, ha="left")
    c.text(0.33, y + 0.012 * k_, it["session_name"].upper(), 20, weight=600, ha="left", track=True)
    c.text(0.33, y - 0.014 * k_, it["when"].upper(), 14, color=P.MUTED, weight=400, ha="left", track=True)
    y -= 0.06 * k_
    c.text(0.06, y, it["title"], 34, weight=600, ha="left")
    if it.get("subtitle"):
        c.text(0.06, y - 0.03 * k_, it["subtitle"], 18, color=P.MUTED, weight=300, ha="left")
    y -= 0.07 * k_
    c.rule(0.06, 0.94, y + 0.012 * k_, color="#232D3F", lw=0.8)
    if it.get("times"):                       # a timetable: zone left, time right
        step = 0.05 * k_
        for k, (zone, t) in enumerate(it["times"][:6]):
            yy = y - step * k - step / 2
            c.text(0.06, yy, zone, 22, weight=600, ha="left")
            c.text(0.94, yy, t, 22, color=P.CYAN if k == 0 else P.TEXT, weight=600 if k == 0 else 400, ha="right")
        rows = it["times"][:6]
    else:
        rows = it["standings"][:10]
        step = min(0.034 if story else 0.04, (0.36 if story else 0.40) / max(len(rows), 1))
    for k, (code, t) in enumerate(rows if not it.get("times") else []):
        num, team, col = DRIVERS.get(code, ("", "", "9AA1AC"))
        yy = y - step * k - step / 2
        c.text(0.085, yy, str(k + 1), 17, color=P.MUTED, weight=400, ha="center")
        c.fig.add_artist(plt.Rectangle((0.12, yy - step * 0.32), 0.008, step * 0.64, transform=c.fig.transFigure,
                                       facecolor="#" + col, edgecolor="none"))
        c.text(0.145, yy, code, 21, weight=700, ha="left")
        c.text(0.255, yy, str(num), 21, color="#" + col, weight=700, ha="left")
        c.text(0.34, yy, team.upper(), 12, color=P.MUTED, weight=500, ha="left", track=True)
        c.text(0.94, yy, t, 19, color=P.TEXT if k == 0 else P.MUTED, weight=600 if k == 0 else 400, ha="right")
    y -= step * len(rows) + 0.022 * k_
    c.rule(0.06, 0.94, y + 0.012 * k_, color="#232D3F", lw=0.8)
    c.text(0.06, y - 0.012 * k_, it.get("notes_label", "WHAT HAPPENED"), 13, color=P.CYAN, weight=600, ha="left", track=True)
    for line in it.get("notes", [])[:3]:
        y -= 0.029 * k_
        c.text(0.06, y - 0.012 * k_, line, 18, weight=300, ha="left")
    c.text(0.5, c.bottom + 0.035 * k_, it["source"], 11, color=P.MUTED, weight=300)
    c.footer()
    return c


def _session_story_v1(p, it: dict):
    from .render import H_REEL
    c = P.Card(H_REEL, story=True)
    c.header(p)
    c.kicker(c.top - 0.05, it["kicker"])
    c.number(c.top - 0.15, it["big"], it["big_label"], size=150, color=it.get("color", P.CYAN))
    c.text(0.5, c.top - 0.205, it["title"].upper(), 30, weight=600, track=True)
    if it.get("subtitle"):
        c.text(0.5, c.top - 0.233, it["subtitle"].upper(), 16, color=P.CYAN, weight=600, track=True)
    y = c.top - 0.30
    for label, line in it["why"][:6]:
        c.text(0.10, y, label.upper(), 13, color=P.CYAN, weight=600, ha="left", track=True)
        c.text(0.10, y - 0.022, line, 19, color=P.TEXT, weight=300, ha="left")
        c.rule(0.10, 0.90, y - 0.04, color="#1E2533", lw=0.6)
        y -= 0.062
    c.text(0.5, c.bottom + 0.035, it["source"], 11, color=P.MUTED, weight=300)
    c.footer()
    return c


def card_path(p, i: int, out: Path) -> Path:
    P.set_event(p)
    f = facts(p)
    k = available(p)[i]
    if k == "upgrades":
        c = upgrades(p, f["upgrades"])
    elif k == "pu":
        c = pu_usage(p, f["pu"]["rows"], f["pu"]["allowance"])
    else:
        c = penalties(p, _list_penalties(f))
    return c.save(out / f"news_{k}.jpg")


def title_carousel(p, out: Path) -> list[Path]:
    P.set_event(p)
    st = standings(p.season)
    return [title_math(p, st, False).save(out / "slide_01.jpg"), title_math(p, st, True).save(out / "slide_02.jpg")]


def title_caption(p) -> str:
    from .captions import FOOTER, clean, event_tag, paragraphs
    st = standings(p.season)
    rows = []
    for team in (False, True):
        s = seal(st, team)
        who = s["holder"]["name"] if team else s["holder"]["code"]
        nxt = s["next"]["name"] if team else s["next"]["code"]
        margin = s["gap"] - s["left_after"]
        head = "🏆 Constructors" if team else "🏎️ Drivers"
        if s["sealed"]:
            rows.append(f"{head}: {who} has P2 sealed")
        elif margin > 0:
            rows.append(f"{head}: {who} seals P2 in {p.title.title()} unless {nxt} outscores them by {fmt(margin)} or more")
        else:
            rows.append(f"{head}: {who} leads {nxt} by {fmt(s['gap'])}, P2 cannot be sealed in {p.title.title()}")
    left = f"{st['races_left']} races" + (f" and {st['sprints_left']} sprints" if st["sprints_left"] else "")
    return clean(paragraphs(
        "🧮 The fight for P2: what it takes",
        rows,
        f"📅 {left} to go. A race win is worth 25, a team 1 2 is worth 43.",
        f"ℹ️ Official standings after round {st['after_round']}. Ties go to countback.",
        "💾 Save this and check it after every race.\n💬 Who finishes second? Tell us below.",
        FOOTER, " ".join(["#F1", "#Formula1", event_tag(p.event), "#F1Standings", "#RaceWeek"])))
