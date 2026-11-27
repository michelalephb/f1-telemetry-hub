"""Hand checked facts per Grand Prix that no API gives us: Pirelli's compound choice and the history
reel. Every entry carries its source. A GP with no entry simply gets no tyre card or history reel:
nothing is ever guessed. Add the next GP here once its numbers are checked against the sources.

Keys are Preview.title (the OpenF1 location, upper case).
"""
from __future__ import annotations

# Compound colours as F1 broadcasts show them (project spec, Graphic 3).
COMPOUND_COLOR = {"SOFT": "#FF3333", "MEDIUM": "#FFF200", "HARD": "#F2F4F7",
                  "INTER": "#39B54A", "WET": "#00AEEF"}

def trio(t: dict) -> str:
    """Where the three nominated compounds sit in Pirelli's range: softest, hardest or middle."""
    soft, hard = int(t["soft"][1:]), int(t["hard"][1:])
    return "softest" if soft == t["range"] else "hardest" if hard == 1 else "middle"


def streak_text(t: dict) -> str:
    n = t.get("streak", 1)
    if n > 1:
        return f"for the {n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')} year running"
    return "Pirelli's pick this year"


TYRES = {
    "LAS VEGAS": {
        "hard": "C3", "medium": "C4", "soft": "C5",
        "range": 5,                     # 2026 range is C1 to C5, no C6
        "streak": 4,                    # C3 C4 C5 in 2023, 2024, 2025 and 2026
        "why": "Cold desert nights: the tyres must switch on fast",
        "source": "Pirelli, 2026 compound selection",
        "refs": [
            "https://press.pirelli.com/tyre-compounds-selected-for-the-final-three-races-of-the-season/",
            "https://www.formula1.com/en/latest/article/what-tyres-will-the-teams-and-drivers-have-for-the-2025-las-vegas-grand-prix.5qcQtekAT0xEFID0CX8nGC",
            "https://www.formula1.com/en/latest/article/pirelli-confirm-2026-tyre-compounds-as-f1-gets-set-for-a-new-era-of.6la0zKVsCYwWk9AAISz4Yw",
        ],
    },
    "YAS MARINA": {
        "hard": "C3", "medium": "C4", "soft": "C5",
        "range": 5,                     # 2026 range is C1 to C5, no C6
        "streak": 8,                    # C3 C4 C5 every season from 2019 to 2026
        "why": "The softest trio gives the widest range of strategies",
        "source": "Pirelli, 2026 compound selection",
        "refs": [
            "https://press.pirelli.com/tyre-compounds-selected-for-the-final-three-races-of-the-season/",
            "https://press.pirelli.com/the-range-of-compounds-for-the-2026-season-has-been-set/",
            "https://www.formula1.com/en/latest/article/what-tyres-will-the-teams-and-drivers-have-for-the-2025-abu-dhabi-grand-prix.7dAs4svUzCpUlKIdh20q4Y",
            "https://press.pirelli.com/to-abu-dhabi-for-the-grand-finale/",
            "https://press.pirelli.com/abu-dhabi-brings-the-season-to-a-close-with-a-test-as-well/",
            "https://press.pirelli.com/2022-abu-dhabi-grand-prix--preview/",
            "https://www.formula1.com/en/latest/article.what-tyres-will-the-teams-and-drivers-have-for-the-2021-season-finale-in-abu.7LK9slIFSac8O9vO0eE5yD.html",
            "https://press.pirelli.com/2020-abu-dhabi-grand-prix---preview/",
            "https://press.pirelli.com/2019-abu-dhabi-grand-prix--preview/",
        ],
    },
    "LUSAIL": {
        "hard": "C1", "medium": "C2", "soft": "C3",
        "range": 5,                     # 2026 range is C1 to C5, no C6
        "streak": 4,                    # C1 C2 C3 in 2023, 2024, 2025 and 2026 (also 2021; no race in 2022)
        "why": "Fast corners and high lateral loads stress the tyres",
        "source": "Pirelli, 2026 compound selection (Motorsport.com, Tyrepress)",
        "refs": [
            "https://es.motorsport.com/f1/news/neumaticos-pirelli-qatar-vegas-abudhabi/10874388/",
            "https://www.tyrepress.com/2026/11/pirelli-confirms-tyre-compound-selections-for-final-rounds-of-2026-f1-season/",
            "https://press.pirelli.com/the-range-of-compounds-for-the-2026-season-has-been-set/",
            "https://www.formula1.com/en/latest/article/what-tyres-will-the-teams-and-drivers-have-for-the-2025-qatar-grand-prix.5uM7XCc74nzDcQgtnJivy9",
            "https://www.formula1.com/en/latest/article/what-tyres-will-the-teams-and-drivers-have-for-the-2024-qatar-grand-prix.3wg5fMRihKy4tF17WRrDvw",
            "https://www.formula1.com/en/latest/article/what-tyres-will-the-teams-and-drivers-have-for-the-2023-qatar-grand-prix.7lwS2mAXKyyh7Un1AV8RVp",
            "https://press.pirelli.com/another-new-beginning-in-qatar/",
            "https://www.formula1.com/en/latest/article.what-tyres-will-the-teams-and-drivers-have-for-the-first-ever-qatar-grand.5EjA6dp5WuQRERP6WAcrUH.html",
        ],
    },
}

# Race day card: official race format, hand checked.
RACE_DAY = {
    "LAS VEGAS": {
        "laps": 50, "lap_km": "6.201", "race_km": "309.958", "corners": 17,
        "lap_record": "1:33.365", "lap_record_by": "VER 2025",
        "source": "Wikipedia, Las Vegas Grand Prix and Strip Circuit; Pirelli",
        "refs": ["https://en.wikipedia.org/wiki/Las_Vegas_Grand_Prix",
                 "https://en.wikipedia.org/wiki/Las_Vegas_Strip_Circuit",
                 "https://www.lightsoutblog.com/f1-las-vegas-grand-prix-facts-statistics/"],
    },
    "LUSAIL": {
        "laps": 57, "lap_km": "5.419", "race_km": "308.611", "corners": 16,
        "lap_record": "1:22.384", "lap_record_by": "NOR 2024",
        "source": "formula1.com, Qatar circuit; Wikipedia, Lusail International Circuit; Mercedes",
        "refs": ["https://www.formula1.com/en/racing/2026/qatar/circuit",
                 "https://en.wikipedia.org/wiki/Lusail_International_Circuit",
                 "https://www.mercedesamgf1.com/races/qatar-grand-prix-2026",
                 "https://en.wikipedia.org/wiki/2024_Qatar_Grand_Prix",
                 "https://www.formula1.com/en/results/2025/races/1275/qatar/fastest-laps"],
    },
    "YAS MARINA": {
        "laps": 58, "lap_km": "5.281", "race_km": "306.188", "corners": 16,
        "lap_record": "1:25.637", "lap_record_by": "MAG 2024",
        "source": "formula1.com, Abu Dhabi circuit",
        "refs": ["https://www.formula1.com/en/racing/2026/united-arab-emirates/circuit",
                 "https://www.formula1.com/en/latest/article/what-makes-the-abu-dhabi-grand-prix-special-and-why-you-should-see-it.2SPlcsPWUwX6RgS752fMKh",
                 "https://en.wikipedia.org/wiki/Yas_Marina_Circuit",
                 "https://www.formula1.com/en/results/2025/races/1276/abu-dhabi/fastest-laps"],
    },
}

# History reel chapters: year, hero number, unit, headline, detail line, source.
HISTORY = {
    "LAS VEGAS": {
        "chapters": [
            {"year": "1981", "number": "3.65", "unit": "km", "head": "A Grand Prix in a hotel car park",
             "line": "Caesars Palace. 14 turns, 75 laps. Alan Jones won for Williams",
             "source": "Wikipedia, Caesars Palace Grand Prix; formula1.com"},
            {"year": "1981", "number": "P5", "unit": "and champion", "head": "Nelson Piquet clinches the title",
             "line": "Fifth for Brabham beat Reutemann to the title by 1 point. The first of his three",
             "source": "formula1.com, Tremayne; Wikipedia, 1981 Caesars Palace GP"},
            {"year": "1982", "number": "165", "unit": "km/h", "head": "Fastest lap average",
             "line": "Michele Alboreto, Tyrrell: 1:19.639 at 102.5 mph. He won the race too",
             "source": "Motor Sport database"},
            {"year": "1982", "number": "P5", "unit": "and champion", "head": "Keke Rosberg, Williams",
             "line": "One year on, same car park, same story: a title from fifth",
             "source": "formula1.com, Tremayne"},
            {"year": "1982 to 2023", "number": "41", "unit": "years", "head": "Until Formula 1 came back",
             "line": "A new 6.201 km street circuit, 17 corners, 1.9 km down the Strip",
             "source": "Wikipedia, Las Vegas Strip Circuit"},
            {"year": "2024", "number": "1:32.312", "unit": "", "head": "Pole record, George Russell",
             "line": "Russell then won from pole. Verstappen clinched his fourth title the same night",
             "source": "flyinglap.com.br records; formula1.com"},
            {"year": "2025", "number": "1:33.365", "unit": "", "head": "Race lap record, Max Verstappen",
             "line": "239.1 km/h average. Verstappen's second Las Vegas win",
             "source": "Wikipedia, Las Vegas Strip Circuit"},
            {"year": "1981 to 2024", "number": "3", "unit": "world titles", "head": "Decided in Las Vegas",
             "line": "Piquet 1981, Rosberg 1982, Verstappen 2024",
             "source": "formula1.com, Tremayne"},
        ],
        "refs": [
            "https://en.wikipedia.org/wiki/Caesars_Palace_Grand_Prix",
            "https://en.wikipedia.org/wiki/1981_Caesars_Palace_Grand_Prix",
            "https://www.formula1.com/en/drivers/hall-of-fame/Nelson_Piquet.html",
            "https://www.formula1.com/en/latest/article/tremayne-verstappen-wrapped-up-the-title-at-last-years-race-but-two-other.1NgPeGCmwHsndVmWN08lH0",
            "https://motorsportmagazine.com/database/circuits/caesars-palace",
            "https://en.wikipedia.org/wiki/Las_Vegas_Strip_Circuit",
            "https://www.flyinglap.com.br/?p=166213",
            "https://www.f1oversteer.com/races/everything-to-know-about-the-las-vegas-grand-prix-including-track-stats-and-previous-winners/",
        ],
    },
}

# Checked chapters on hold: history.py still writes the Las Vegas hook ("From a hotel car park to the
# Strip") on every history cover and caption, so these would post a false line. Move each entry into
# HISTORY once that text comes from the GP's own facts. Nothing reads this dict.
HISTORY_ON_HOLD = {
    "LUSAIL": {
        "chapters": [
            {"year": "2008", "number": "1st", "unit": "night race", "head": "MotoGP under the lights",
             "line": "Lusail hosted the first night race in MotoGP history",
             "source": "Motor Sport; Wikipedia, Lusail International Circuit"},
            {"year": "2021", "number": "25.743", "unit": "s", "head": "The first Qatar Grand Prix",
             "line": "Lewis Hamilton won from pole, 25.743 s clear of Max Verstappen",
             "source": "formula1.com"},
            {"year": "2022", "number": "10", "unit": "year deal", "head": "A year off, then a decade",
             "line": "No race in 2022 for the FIFA World Cup. A 10 year contract from 2023",
             "source": "Wikipedia, Qatar Grand Prix; formula1.com"},
            {"year": "2023", "number": "P2", "unit": "and champion", "head": "A title sealed in a sprint",
             "line": "Second in the 19 lap sprint gave Verstappen his third straight title",
             "source": "formula1.com; Wikipedia, 2023 Qatar GP"},
            {"year": "2023", "number": "18", "unit": "laps", "head": "Tyre life cap per set",
             "line": "The FIA capped every set at 18 laps after sidewall damage on the kerbs",
             "source": "fia.com; RaceFans"},
            {"year": "2024", "number": "1:22.384", "unit": "", "head": "Race lap record, Lando Norris",
             "line": "Set on lap 56, after a 10 second stop go penalty. Verstappen won",
             "source": "formula1.com; Wikipedia, 2024 Qatar GP; The Race"},
            {"year": "2025", "number": "25", "unit": "laps", "head": "Maximum per set of tyres",
             "line": "Verstappen won from third on the grid, 7.995 s ahead of Piastri",
             "source": "formula1.com; fia.com; Motor Sport"},
            {"year": "2023 to 2025", "number": "3", "unit": "wins", "head": "Max Verstappen, most wins here",
             "line": "Three Qatar Grands Prix in a row for Verstappen and Red Bull",
             "source": "formula1.com results; Wikipedia, Qatar Grand Prix"},
        ],
        "refs": [
            "https://motorsportmagazine.com/archive/article/may-2008/27/mpoto-gp-hails-first-night-race",
            "https://en.wikipedia.org/wiki/Lusail_International_Circuit",
            "https://www.formula1.com/en/latest/article/hamilton-narrows-verstappens-title-lead-with-qatar-win-as-alonso-takes-first.5rYgipXuNRiQ0QNs7Xmu1B",
            "https://en.wikipedia.org/wiki/Qatar_Grand_Prix",
            "https://www.formula1.com/en/racing/2026/qatar/circuit",
            "https://www.formula1.com/en/latest/article/verstappen-secures-third-f1-world-title-as-piastri-takes-sprint-victory-in.4d0SLopnXU9W8uzefnJmu3",
            "https://en.wikipedia.org/wiki/2023_Qatar_Grand_Prix",
            "https://www.fia.com/news/fia-statement-treatment-tyres-2023-fia-formula-1-qatar-grand-prix",
            "https://www.racefans.net/2023/10/08/fia-confirms-tyre-restrictions-for-qatar-gp-forcing-drivers-to-pit-three-times/",
            "https://www.formula1.com/en/results/2023/races/1221/qatar/race-result",
            "https://en.wikipedia.org/wiki/2024_Qatar_Grand_Prix",
            "https://www.the-race.com/formula-1/big-norris-penalty-keeps-constructors-fight-open-as-verstappen-wins-qatar-grand-prix",
            "https://www.formula1.com/en/latest/article/what-tyres-will-the-teams-and-drivers-have-for-the-2025-qatar-grand-prix.5uM7XCc74nzDcQgtnJivy9",
            "https://www.motorsportmagazine.com/articles/single-seaters/f1/verstappen-wins-qatar-gp-to-set-up-three-way-title-fight-in-f1-finale/",
            "https://raceprogramme.formula1.com/2025/abu-dhabi/round-recap-qatar",
            "https://www.fia.com/news/f1-verstappen-wins-qatar-ahead-piastri-norris-fourth-take-title-fight-final-round-showdown",
            "https://en.wikipedia.org/wiki/2025_Qatar_Grand_Prix",
        ],
    },
    "YAS MARINA": {
        "chapters": [
            {"year": "2009", "number": "1st", "unit": "day to night race", "head": "Formula 1 at twilight",
             "line": "The first Abu Dhabi Grand Prix. Sebastian Vettel won for Red Bull",
             "source": "formula1.com"},
            {"year": "2010", "number": "4", "unit": "title contenders", "head": "The only four way finale",
             "line": "Vettel came in 15 points behind Alonso and left champion by 4",
             "source": "formula1.com"},
            {"year": "2014", "number": "50", "unit": "points", "head": "Double points for one win",
             "line": "Hamilton won and took the title by 67 points over Rosberg",
             "source": "formula1.com"},
            {"year": "2016", "number": "P2", "unit": "and champion", "head": "Nico Rosberg, Mercedes",
             "line": "Second was enough. Champion like his father Keke in 1982",
             "source": "formula1.com"},
            {"year": "2021", "number": "369.5", "unit": "points each", "head": "Level before the final race",
             "line": "Verstappen passed Hamilton on the last lap for his first title",
             "source": "formula1.com"},
            {"year": "2021", "number": "16", "unit": "corners", "head": "A shorter layout",
             "line": "Down from 21 corners. The lap went from 5.554 km to 5.281 km",
             "source": "formula1.com; Yas Marina Circuit; Wikipedia; RacingNews365"},
            {"year": "2015 to 2025", "number": "11", "unit": "in a row", "head": "Won from pole every time",
             "line": "A Formula 1 record for any venue",
             "source": "formula1.com"},
            {"year": "2025", "number": "2", "unit": "points", "head": "Lando Norris, champion",
             "line": "Third in the race, 423 points. Closest title margin since the 2010 points system",
             "source": "fia.com; formula1.com"},
        ],
        "refs": [
            "https://www.formula1.com/en/latest/article/what-makes-the-abu-dhabi-grand-prix-special-and-why-you-should-see-it.2SPlcsPWUwX6RgS752fMKh",
            "https://www.formula1.com/en/latest/article/why-the-yas-marina-circuit-makes-for-a-great-season-finale.4z4Y9uuDhIo7V2Fl2xRFmY",
            "https://en.wikipedia.org/wiki/Abu_Dhabi_Grand_Prix",
            "https://www.formula1.com/en/racing/2020/united-arab-emirates",
            "https://www.formula1.com/en/racing/2026/united-arab-emirates/circuit",
            "https://yasmarinacircuit.com/en/mediacenter/what-the-track-changes-mean-for-f1",
            "https://racingnews365.com/what-changes-have-been-made-to-the-track-for-the-abu-dhabi-gp",
            "https://en.wikipedia.org/wiki/Yas_Marina_Circuit",
            "https://www.formula1.com/en/latest/article/facts-and-stats-verstappen-won-more-piastri-led-longer-but-norris-is.14xcBAi0H4ASrOzunupYFv",
            "https://www.fia.com/news/f1-norris-crowned-fia-formula-one-world-champion-verstappen-takes-abu-dhabi-win",
        ],
    },
}


# Weekend news from the FIA documents of the event, filled by the race week research task with a source per
# item, then checked. {title: {season: {"upgrades": [{team, color, items: [(area, what)]}],
#   "pu": {"rows": [{driver, counts: {ICE: n, ...}}], "allowance": {ICE: n, ...}},
#   "penalties": [{driver, team, places, reason, source}]}}}
# A card is drawn only when its list is filled; nothing is guessed.
# A penalty with story: True already had its own story (social __main__ mode news): the list card leaves that
# driver out, so do not add him again from the FIA documents.
NEWS: dict = {
    "LAS VEGAS": {
        2026: {
            "penalties": [
                {
                    "driver": "Oscar Piastri", "code": "PIA", "team": "McLaren", "color": "#FF8000",
                    "places": 10, "reason": "5th ICE of the season", "story": True,
                    "engines": {"used": 5, "limit": 4},
                    "why": [
                        ("What happened", "New combustion engine after a reliability issue"),
                        ("The rule", "4 ICEs per driver per season. This is his 5th"),
                        ("The price", "First extra ICE of the year: 10 places back"),
                        ("On the grid", "Even pole in qualifying means P11 on Saturday"),
                        ("McLaren's view", "A good chance to recover places by overtaking"),
                    ],
                    "source": "Source: McLaren Las Vegas GP preview, 17 Nov 2026 (Motorsport.com, Sky Sports)",
                    "sources": [
                        "https://www.motorsport.com/f1/news/oscar-piastri-set-for-grid-penalty-at-f1-las-vegas-gp/10875180/",
                        "https://www.skysports.com/f1/news/13613606/oscar-piastri-to-serve-grid-penalty-at-las-vegas-gp-as-mclaren-confirm-addition-of-more-upgrades-to-mcl40",
                        "https://f1i.com/news/578148-piastri-hit-with-10-place-grid-penalty-for-las-vegas-gp.html",
                    ],
                },
            ],
        },
    },
    "LUSAIL": {
        2026: {
            "penalties": [
                {
                    "driver": "PER", "code": "PER", "team": "Cadillac",
                    "places": 5, "reason": "Caused collision with Camara in Las Vegas",
                    "source": "Source: FIA stewards decision, document 61",
                },
            ],
        },
    },
}


# Session reports from the news, posted within the hour after each session even before timing data is out
# (Michel, 19 Nov). SESSION_NEWS[gp][season][session code] = list of stories (news.session_story). Each line is
# a fact found in at least two outlets; posted once each by social __main__ mode news, kind = session code.
SESSION_NEWS: dict = {
    "LAS VEGAS": {
        2026: {
            "FP1": [
                {
                    "kicker": "FP1 report", "big": "0", "big_label": "timed laps", "color": "#00AEEF",
                    "title": "Washed out", "subtitle": "Rain and standing water on the Strip",
                    "why": [
                        ("The track", "Heavy rain, standing water, aquaplaning"),
                        ("Top of the sheet", "Perez, Cadillac: first car out, no time"),
                        ("Stayed in", "Norris, Piastri, Stroll, Lawson, Lindblad"),
                        ("Last minute", "Both Alpines out for practice starts"),
                        ("Next", "FP2 at 8 PM PT, drier conditions expected"),
                    ],
                    "source": "Sources: PlanetF1, Crash.net, RacingNews365, GrandPrix247, 19 Nov 2026",
                    "sources": [
                        "https://www.planetf1.com/news/2026-las-vegas-grand-prix-fp1-report",
                        "https://www.crash.net/f1/results/1110235/1/2026-f1-las-vegas-grand-prix-friday-practice-results",
                        "https://racingnews365.com/2026-f1-las-vegas-grand-prix-free-practice-1-results",
                        "https://www.grandprix247.com/formula-1-news/las-vegas-grand-prix-fp1-nothing-to-report-actually-just-rain",
                        "https://autoindiadaily.in/motorsport/2026-f1-las-vegas-gp-fp1-results/",
                    ],
                },
                {
                    "kicker": "FP1: who lost out", "big": "5", "big_label": "never left the pits", "color": "#FF8000",
                    "title": "Dry laps wanted", "subtitle": "Rain wiped out the hour",
                    "why": [
                        ("McLaren", "Norris and Piastri kept in the garage"),
                        ("Racing Bulls", "Lawson and Lindblad stayed in too"),
                        ("Aston Martin", "Stroll did not run"),
                        ("Piastri", "No FP1 laps, and a 10 place grid drop"),
                        ("Wet again", "Rain also hit 2025 FP3 and qualifying"),
                        ("Tonight", "FP2 at 8 PM PT, drier conditions expected"),
                    ],
                    "source": "Sources: Crash.net, Grande Premio, PlanetF1, Motorsport.com, McLaren, 19 Nov 2026",
                    "sources": [
                        "https://www.crash.net/f1/results/1110235/1/2026-f1-las-vegas-grand-prix-friday-practice-results",
                        "https://grandepremio.com/en/f1/las-vegas-f1-practice-wiped-out-by-heavy-rain-as-all-22-drivers-fail-to-set-lap-times/",
                        "https://autoindiadaily.in/motorsport/2026-f1-las-vegas-gp-fp1-results/",
                        "https://www.planetf1.com/news/2026-las-vegas-grand-prix-fp1-report",
                        "https://www.motorsport.com/f1/news/what-was-behind-f1-las-vegas-gps-worst-conditions-ever/10778910/",
                        "https://www.news.gp/en/max-verstappen-unimpressed-with-low-grip-las-vegas-qualifying-conditions",
                    ],
                },
            ],
            "QPRE": [
                {
                    "session": "Q", "session_name": "Qualifying", "when": "Tonight, Fri 20 Nov, Las Vegas",
                    "title": "Grid set tonight", "subtitle": "One hour, three parts, 22 cars",
                    "times": [["Las Vegas (PT)", "Fri 8:00 PM"], ["New York (ET)", "Fri 11:00 PM"],
                              ["London (GMT)", "Sat 4:00 AM"], ["Paris (CET)", "Sat 5:00 AM"]],
                    "notes_label": "BEFORE QUALIFYING",
                    "notes": ["FP3 today at 4:30 PM PT", "Russell fastest in FP2, 1:47.272",
                              "Piastri starts 10 places down"],
                    "source": "Sources: formula1.com, The Race, GPblog, RacingNews365, GPFans, 20 Nov 2026",
                    "sources": [
                        "https://www.formula1.com/en/latest/article/what-time-is-the-formula-1-2026-las-vegas-grand-prix-and-how-can-i-watch-it.5klYngWOQMjROxZ3nEp5Pr",
                        "https://www.the-race.com/formula-1/what-time-is-f1s-2026-las-vegas-grand-prix-full-weekend-schedule/",
                        "https://www.gpblog.com/en/news/formula-1-las-vegas-gp-2026-all-session-times-and-full-weekend-schedule",
                        "https://racingnews365.com/2026-f1-las-vegas-grand-prix-time-schedule",
                        "https://www.gpfans.com/en/f1-news/1092915/f1-las-vegas-grand-prix-2026-schedule-uk-start-times-how-to-watch-on-tv/",
                    ],
                },
            ],
            "FP2": [
                {
                    "kicker": "FP2 report", "big": "1:47.272", "big_label": "Russell, Mercedes", "color": "#27F4D2",
                    "title": "Russell on top", "subtitle": "A late lap in damp FP2",
                    "why": [
                        ("Second", "Gasly, Alpine, 0.071s behind"),
                        ("Third", "Leclerc, Ferrari, top until late"),
                        ("P4 to P8", "Hadjar, Piastri, Hamilton, Norris, Antonelli"),
                        ("Red flag", "Plastic debris on track, late stop"),
                        ("Verstappen", "Late to set a time, P13"),
                    ],
                    "source": "Sources: GPblog, RacingNews365, Autosport, Pit Debrief, 19 Nov 2026",
                    "sources": [
                        "https://www.gpblog.com/en/breaking-news/russell-strikes-late-to-deny-dominant-leclerc-top-spot-in-las-vegas-fp2",
                        "https://racingnews365.com/2026-f1-las-vegas-grand-prix-free-practice-2-results",
                        "https://www.autosport.com/f1/live-text/f1-las-vegas-gp-follow-fp2-from-las-vegas-with-live-timing/1128340/",
                        "https://www.pitdebrief.com/post/2026-f1-las-vegas-gp-fp2-results/",
                    ],
                },
                {
                    "session": "FP2", "session_name": "Second practice", "when": "Thu 19 Nov, Las Vegas",
                    "title": "Russell on top, late", "subtitle": "Wet start, drying track, fastest laps in the final minutes",
                    "standings": [["RUS", "1:47.272"], ["GAS", "+0.071"], ["LEC", "+0.333"], ["HAD", "+1.135"],
                                  ["PIA", "+1.181"], ["HAM", "+1.211"], ["NOR", "+1.565"], ["ANT", "+1.771"],
                                  ["COL", "+1.957"], ["ALO", "+1.959"]],
                    "notes": ["Full wets first, then intermediates as it dried",
                              "Red flag late on for plastic debris",
                              "Verstappen P13, 2.869s off"],
                    "source": "Sources: GPblog, PlanetF1, Crash.net, RacingNews365, GrandPrix247, 19 Nov 2026",
                    "sources": [
                        "https://www.gpblog.com/en/news/full-results-russell-snatches-topping-day-one-from-ferrari-in-las-vegas",
                        "https://www.planetf1.com/news/f1-results-las-vegas-grand-prix-2026-fp2-las-vegas-strip-circuit",
                        "https://www.crash.net/f1/results/1110235/1/2026-f1-las-vegas-grand-prix-friday-practice-results",
                        "https://racingnews365.com/2026-f1-las-vegas-grand-prix-free-practice-2-results",
                        "https://www.grandprix247.com/formula-1-news/las-vegas-grand-prix-fp2-george-russell-tops-wet-session-ahead-of-pierre-gasly-and-charles-leclerc",
                    ],
                },
                {
                    "session": "FP2", "session_name": "Second practice", "when": "Thu 19 Nov, Las Vegas",
                    "title": "Leclerc pipped late", "subtitle": "Ferrari led most of the hour, Mercedes and Alpine struck last",
                    "standings": [["RUS", "1:47.272"], ["GAS", "+0.071"], ["LEC", "+0.333"]],
                    "notes": ["Leclerc set the benchmark at 1:47.605",
                              "Russell and Gasly beat it on the final laps",
                              "Hamilton P6 in the other Ferrari, +1.211"],
                    "source": "Sources: GPblog, RacingNews365, GrandPrix247, F1 Oversteer, PlanetF1, 19 Nov 2026",
                    "sources": [
                        "https://www.gpblog.com/en/breaking-news/russell-strikes-late-to-deny-dominant-leclerc-top-spot-in-las-vegas-fp2",
                        "https://racingnews365.com/2026-f1-las-vegas-grand-prix-free-practice-2-results",
                        "https://www.grandprix247.com/formula-1-news/las-vegas-grand-prix-fp2-george-russell-tops-wet-session-ahead-of-pierre-gasly-and-charles-leclerc",
                        "https://www.f1oversteer.com/races/george-russell-tops-red-flagged-las-vegas-gp-fp2-as-max-verstappen-bemoans-engine-issue/",
                        "https://planetf1.com/news/2026-las-vegas-grand-prix-fp2-report",
                    ],
                },
            ],
            "FP3": [
                {
                    "session": "FP3", "session_name": "Third practice", "when": "Fri 20 Nov, Las Vegas",
                    "title": "Russell by 0.9s", "subtitle": "First dry running of the weekend, Mercedes one two",
                    "standings": [["RUS", "1:34.041"], ["ANT", "+0.911"], ["NOR", "+0.974"], ["LEC", "+1.150"],
                                  ["COL", "+1.157"], ["VER", "+1.309"], ["LAW", "+1.361"], ["HAM", "+1.393"],
                                  ["GAS", "+1.402"], ["LIN", "+1.409"]],
                    "notes": ["Dry at last after rain on Thursday",
                              "Verstappen v Colapinto sent to the stewards",
                              "Late Russell v Verstappen moment noted too"],
                    "source": "Sources: PlanetF1, GPblog, Pit Debrief, Autosport, RacingNews365, 20 Nov 2026",
                    "sources": [
                        "https://www.planetf1.com/news/f1-results-las-vegas-grand-prix-2026-fp3-strip-circuit",
                        "https://www.gpblog.com/en/breaking-news/russell-in-a-league-of-his-own-as-furious-verstappen-faces-double-fp3-investigation",
                        "https://www.pitdebrief.com/post/2026-f1-las-vegas-gp-fp3-results/",
                        "https://www.autosport.com/f1/live-text/f1-las-vegas-gp-follow-fp3-from-las-vegas-with-live-timing-/1128352/",
                        "https://racingnews365.com/max-verstappen-under-investigation-after-erratic-incident-with-franco-colapinto",
                        "https://autoindiadaily.in/motorsport/f1-las-vegas-gp-2026-fp3-live/",
                    ],
                },
                {
                    "session": "FP3", "session_name": "Third practice", "when": "Fri 20 Nov, Las Vegas",
                    "title": "Verstappen's tough hour", "subtitle": "P6, two stewards' probes and a steering complaint",
                    "standings": [["RUS", "1:34.041", 1], ["COL", "+1.157", 5], ["VER", "+1.309", 6]],
                    "notes": ["Weaved early, Colapinto passed, he repassed",
                              "Wheel to wheel with Russell late on",
                              "Complained about his steering"],
                    "source": "Sources: GPblog, RacingNews365, Autosport, PlanetF1, Pit Debrief, 20 Nov 2026",
                    "sources": [
                        "https://www.gpblog.com/en/breaking-news/verstappen-lands-in-hot-water-with-stewards-over-las-vegas-gp-fp3-incident",
                        "https://www.gpblog.com/en/breaking-news/russell-in-a-league-of-his-own-as-furious-verstappen-faces-double-fp3-investigation",
                        "https://racingnews365.com/max-verstappen-under-investigation-after-erratic-incident-with-franco-colapinto",
                        "https://www.autosport.com/f1/live-text/f1-las-vegas-gp-follow-fp3-from-las-vegas-with-live-timing-/1128352/",
                        "https://www.planetf1.com/news/f1-results-las-vegas-grand-prix-2026-fp3-strip-circuit",
                        "https://www.pitdebrief.com/post/2026-f1-las-vegas-gp-fp3-results/",
                    ],
                },
            ],
            "Q": [
                {
                    "session": "Q", "session_name": "Qualifying", "when": "Fri 20 Nov, Las Vegas", "color": "#4781D7",
                    "title": "Verstappen on pole", "subtitle": "Antonelli fastest, his grid drop hands Max P1",
                    "standings": [["ANT", "1:33.893"], ["VER", "+0.258"], ["RUS", "+0.331"], ["NOR", "+0.351"],
                                  ["HAD", "+0.699"], ["LIN", "+0.775"]],
                    "notes": ["Antonelli drops five places, sixth combustion engine",
                              "Verstappen and Russell share the front row",
                              "Both Ferraris out in Q2, P11 and P12"],
                    "source": "Sources: GPblog, Pit Debrief, Crash.net, Autosport, formula1.com, 21 Nov 2026",
                    "sources": [
                        "https://www.gpblog.com/en/news/f1-full-results-verstappen-inherits-las-vegas-gp-pole-antonelli-fastest",
                        "https://www.gpblog.com/en/breaking-news/antonelli-claims-striking-las-vegas-pole-as-ferrari-suffer-double-humiliation",
                        "https://www.pitdebrief.com/post/2026-f1-las-vegas-gp-qualifying-results/",
                        "https://www.crash.net/f1/news/1110511/1/max-verstappen-las-vegas-gp-pole-ferrari-suffers-qualifying-shocker",
                        "https://www.autosport.com/f1/live-text/f1-las-vegas-gp-follow-qualifying-from-las-vegas-with-live-timing-/1128364/",
                        "https://www.formula1.com/en/latest/article/antonelli-bearman-and-stroll-set-for-grid-penalties-at-las-vegas-grand-prix.37Vixk6Mt1gvZlVXDsO8S",
                    ],
                },
                {
                    "session": "Q", "session_name": "Qualifying", "when": "Fri 20 Nov, Las Vegas", "color": "#00E5FF",
                    "title": "Grid after penalties", "subtitle": "Start slots, with each driver's qualifying lap",
                    "standings": [["VER", "1:34.151", 1], ["RUS", "1:34.224", 2], ["NOR", "1:34.244", 3],
                                  ["ANT", "1:33.893", 6]],
                    "notes": ["Antonelli fastest, starts sixth after his drop",
                              "Piastri 10 places down, Bearman at the back",
                              "Sainz and Stroll also take 10 place drops"],
                    "source": "Sources: Crash.net, Pit Debrief, Autosport, GPblog, formula1.com, Grande Premio, 21 Nov 2026",
                    "sources": [
                        "https://www.crash.net/f1/news/1110511/1/max-verstappen-las-vegas-gp-pole-ferrari-suffers-qualifying-shocker",
                        "https://www.pitdebrief.com/post/2026-f1-las-vegas-gp-qualifying-results/",
                        "https://www.autosport.com/f1/live-text/f1-las-vegas-gp-follow-qualifying-from-las-vegas-with-live-timing-/1128364/",
                        "https://www.gpblog.com/en/news/f1-full-results-verstappen-inherits-las-vegas-gp-pole-antonelli-fastest",
                        "https://www.formula1.com/en/latest/article/antonelli-bearman-and-stroll-set-for-grid-penalties-at-las-vegas-grand-prix.37Vixk6Mt1gvZlVXDsO8S",
                        "https://www.crash.net/f1/news/1110267/1/five-f1-drivers-carrying-grid-penalties-las-vegas-gp",
                        "https://www.gpblog.com/en/news/fia-stewards-confirm-grid-penalties-for-the-las-vegas-grand-prix",
                        "https://grandepremio.com/en/f1/sainz-stroll-and-bearman-join-antonelli-and-piastri-on-las-vegas-f1-grid-penalty-list/",
                    ],
                },
            ],
            # Race build up, one story an hour from 4 PM PT on race day (hourly RACE_ONLY window), 21 Nov 2026
            "RPRE": [
                {
                    "session": "R", "session_name": "Race", "when": "Tonight, Sat 21 Nov, Las Vegas", "color": "#4781D7",
                    "title": "The grid, top 10", "subtitle": "Start slot, and where each driver qualified",
                    "standings": [["VER", "Qualified P2", 1], ["RUS", "Qualified P3", 2], ["NOR", "Qualified P4", 3],
                                  ["HAD", "Qualified P5", 4], ["LIN", "Qualified P6", 5], ["ANT", "Qualified P1", 6],
                                  ["LAW", "Qualified P8", 7], ["GAS", "Qualified P9", 8], ["COL", "Qualified P10", 9],
                                  ["LEC", "Qualified P11", 10]],
                    "notes_label": "ON THE GRID",
                    "notes": ["Row 2: Norris and Hadjar",
                              "Row 3: Lindblad alongside Antonelli",
                              "Both Racing Bulls and Alpines in the top 10"],
                    "source": "Sources: Crash.net, RacingNews365, PlanetF1, Grande Premio, GPblog, formula1.com, 21 Nov 2026",
                    "sources": [
                        "https://www.crash.net/f1/news/1110516/1/f1-2026-las-vegas-grand-prix-starting-grid-after-five-engine-penalties",
                        "https://racingnews365.com/las-vegas-starting-grid-heavily-adjusted-after-five-driver-penalties",
                        "https://www.planetf1.com/las-vegas-grand-prix/f1-starting-grid-2026-las-vegas-grand-prix",
                        "https://grandepremio.com/en/f1/las-vegas-f1-starting-grid-2026-full-22-driver-order-after-five-penalties/",
                        "https://www.gpblog.com/en/news/las-vegas-starting-grid-shaken-up-after-penalties-for-antonelli-and-others",
                        "https://www.formula1.com/en/latest/article/antonelli-quickest-in-las-vegas-gp-qualifying-as-verstappen-inherits-pole-position.6R7udh8iYMHunSOGI6zStK",
                    ],
                },
                {
                    "session": "R", "session_name": "Race", "when": "Tonight, Sat 21 Nov, Las Vegas", "color": "#00E5FF",
                    "title": "Five grid penalties", "subtitle": "All for power unit parts over the season limit",
                    "standings": [["ANT", "5 places", 6], ["PIA", "10 places", 17], ["SAI", "10 places", 20],
                                  ["STR", "10 places", 21], ["BEA", "35 places", 22]],
                    "notes_label": "WHY",
                    "notes": ["ANT sixth and PIA fifth combustion engine",
                              "SAI fifth turbo. STR energy store, electronics",
                              "BEA four new engine parts: back of the grid"],
                    "source": "Sources: grandprix.com, Grande Premio, RaceFans, f1i, formula1.com, GPblog, 20 and 21 Nov 2026",
                    "sources": [
                        "https://www.grandprix.com/news/bearman-heads-las-vegas-grid-penalties-as-stroll-and-sainz-also-drop.html",
                        "https://grandepremio.com/en/f1/sainz-stroll-and-bearman-join-antonelli-and-piastri-on-las-vegas-f1-grid-penalty-list/",
                        "https://www.racefans.net/2026/11/20/five-drivers-to-take-grid-penalties-at-las-vegas-grand-prix/",
                        "https://f1i.com/news/578279-five-drivers-hit-with-grid-penalties-for-las-vegas-gp.html/amp",
                        "https://www.formula1.com/en/latest/article/antonelli-quickest-in-las-vegas-gp-qualifying-as-verstappen-inherits-pole-position.6R7udh8iYMHunSOGI6zStK",
                        "https://www.gpblog.com/en/news/las-vegas-starting-grid-shaken-up-after-penalties-for-antonelli-and-others",
                        "https://racingnews365.com/las-vegas-starting-grid-heavily-adjusted-after-five-driver-penalties",
                    ],
                },
                {
                    "session": "R", "session_name": "Race", "when": "Tonight, Sat 21 Nov, Las Vegas", "color": "#FF3333",
                    "title": "One stop expected", "subtitle": "Pirelli: soft and medium, the fastest pair on paper",
                    "times": [["Soft", "C5"], ["Medium", "C4"], ["Hard", "C3"], ["Stops", "One"],
                              ["Pit window", "Laps 22 to 28"]],
                    "notes_label": "PIRELLI SAYS",
                    "notes": ["Hard: a couple of seconds slower overall",
                              "Very limited wear on all three compounds",
                              "Undercut weaker: tyres cool on the pit exit"],
                    "source": "Sources: Pirelli, Italpress, GrandPrix247, Scuderia Fans, 17 to 21 Nov 2026",
                    "sources": [
                        "https://press.pirelli.com/antonelli-goes-all-in-sets-the-fastest-time-on-soft/",
                        "https://www.italpress.com/gp-las-vegas-marrafuschi-una-sosta-e-soft-medium-la-strategia-piu-veloce/",
                        "https://www.f1network.net/main/s107/st209184.htm",
                        "https://press.pirelli.com/tyre-compounds-selected-for-the-final-three-races-of-the-season/",
                        "https://www.grandprix247.com/formula-1-news/pirelli-warns-tyre-warm-up-and-graining-could-prove-decisive-at-2026-formula-1-las-vegas-grand-prix",
                        "https://scuderiafans.com/pirelli-warns-of-tyre-graining-risk-and-extreme-pressures-ahead-of-2026-f1-las-vegas-gp/",
                    ],
                },
                {
                    "session": "R", "session_name": "Race", "when": "Tonight, Sat 21 Nov, Las Vegas", "color": "#00AEEF",
                    "title": "Dry and cold", "subtitle": "The forecast for tonight's race on the Strip",
                    "times": [["Rain chance", "0%"], ["Air, race day", "5 to 11 C"], ["Track, Pirelli", "About 14 C"],
                              ["Wind", "8 km/h, gusts 18"]],
                    "notes_label": "WHAT IT MEANS",
                    "notes": ["Pirelli expects track temps like qualifying",
                              "Cold tyres: warm up is the big challenge",
                              "Thursday's rain is not in the forecast"],
                    "source": "Sources: formula1.com, Athlon Sports, Pirelli, 18 to 21 Nov 2026",
                    "sources": [
                        "https://www.formula1.com/en/latest/article/what-is-the-weather-forecast-for-the-2026-las-vegas-grand-prix.1ki78WcweOZ8vq2zQ1HOJX",
                        "https://athlonsports.com/racing/f1/weather-forecast-rain-las-vegas-grand-prix-2026",
                        "https://press.pirelli.com/antonelli-goes-all-in-sets-the-fastest-time-on-soft/",
                        "https://www.grandprix247.com/formula-1-news/pirelli-warns-tyre-warm-up-and-graining-could-prove-decisive-at-2026-formula-1-las-vegas-grand-prix",
                        "https://scuderiafans.com/pirelli-warns-of-tyre-graining-risk-and-extreme-pressures-ahead-of-2026-f1-las-vegas-gp/",
                    ],
                },
                {
                    "session": "R", "session_name": "Race", "when": "Tonight, Sat 21 Nov, Las Vegas", "color": "#00D7B6",
                    "title": "The fight for P2", "subtitle": "Antonelli is champion, five drivers chase second",
                    "standings": [["ANT", "390 pts"], ["VER", "279 pts"], ["RUS", "262 pts"], ["HAM", "261 pts"],
                                  ["LEC", "249 pts"], ["NOR", "246 pts"]],
                    "notes_label": "WHAT IS AT STAKE",
                    "notes": ["Antonelli sealed the title in Mexico City",
                              "Russell 17 behind Verstappen, Hamilton 18",
                              "Leclerc 30 back, Norris 33. A win is 25"],
                    "source": "Sources: formula1.com official standings and title report, Nov 2026",
                    "sources": [
                        "https://www.formula1.com/en/results/2026/drivers",
                        "https://www.formula1.com/en/latest/article/f1s-youngest-world-champions-as-antonelli-smashes-the-record.4otUr4h4wmWd6VmIEaNjzV",
                        "https://www.racefans.net/2026/11/08/2026-brazilian-grand-prix-race-result-and-championship-points/",
                    ],
                },
                {
                    "session": "R", "session_name": "Race", "when": "Tonight, Sat 21 Nov, Las Vegas", "color": "#00E5FF",
                    "title": "Lights out at 8 PM", "subtitle": "50 laps, 309.958 km on the Strip",
                    "times": [["Las Vegas (PT)", "Sat 8:00 PM"], ["New York (ET)", "Sat 11:00 PM"],
                              ["London (GMT)", "Sun 4:00 AM"], ["Paris (CET)", "Sun 5:00 AM"],
                              ["Laps", "50"], ["Distance", "309.958 km"]],
                    "notes_label": "THE RACE",
                    "notes": ["Lap 6.201 km, 17 corners",
                              "Lap record 1:33.365, Verstappen 2025"],
                    "source": "Sources: formula1.com, The Race, GPblog, RacingNews365, 21 Nov 2026",
                    "sources": [
                        "https://www.formula1.com/en/latest/article/what-time-is-the-formula-1-2026-las-vegas-grand-prix-and-how-can-i-watch-it.5klYngWOQMjROxZ3nEp5Pr",
                        "https://www.the-race.com/formula-1/what-time-is-f1s-2026-las-vegas-grand-prix-full-weekend-schedule/",
                        "https://www.gpblog.com/en/news/formula-1-las-vegas-gp-2026-all-session-times-and-full-weekend-schedule",
                        "https://racingnews365.com/2026-f1-las-vegas-grand-prix-start-time",
                        "https://www.formula1.com/en/racing/2026/las-vegas/circuit",
                    ],
                },
            ],
            # Race reports, 22 Nov 2026. Winner's total time not published by any outlet yet: "50 laps".
            # Points: formula1.com standings after Brazil plus race points, matching RaceFans, RacingNews365, GPblog.
            "R": [
                {
                    "session": "R", "session_name": "Race", "when": "Sat 21 Nov, Las Vegas", "color": "#4781D7",
                    "title": "Verstappen wins Vegas", "subtitle": "From pole, 0.639s clear. McLaren double podium",
                    "standings": [["VER", "50 laps"], ["NOR", "+0.639"], ["PIA", "+1.529"], ["ANT", "+2.574"],
                                  ["GAS", "+2.927"], ["COL", "+7.955"], ["HAM", "+12.795"], ["SAI", "+12.938"],
                                  ["RUS", "+13.192"], ["LEC", "+17.554"]],
                    "notes": ["Antonelli lost power late, dropped to P4",
                              "Russell hit the wall at Turn 5 late, P9",
                              "Leclerc 10s penalty for hitting Hamilton"],
                    "source": "Sources: The Race, PlanetF1, grandprix.com, Grande Premio, Scuderia Fans, PA, 22 Nov 2026",
                    "sources": [
                        "https://www.the-race.com/formula-1/f1-2026-las-vegas-grand-prix-race-result/",
                        "https://www.planetf1.com/news/f1-results-las-vegas-grand-prix-2026-race",
                        "https://www.planetf1.com/news/2026-las-vegas-grand-prix-race-report",
                        "https://www.grandprix.com/races/las-vegas-gp-2026-race-notes.html",
                        "https://grandepremio.com/en/f1/verstappen-wins-spectacular-las-vegas-f1-race-as-mclaren-takes-double-podium-and-russell-crashes/",
                        "https://scuderiafans.com/2026-f1-las-vegas-gp-race-results-full-finishing-order-and-final-classification/",
                        "https://readmotorsport.com/2026/11/22/f1-las-vegas-gp-race-results-2026-verstappen-wins/",
                        "https://www.irishnews.com/sport/motorsport/max-verstappen-wins-in-las-vegas-as-ferrari-rivals-clash-again-HBEYZDA64RL6DFXMAHM7XILUTU/",
                    ],
                },
                {
                    "session": "R", "session_name": "Race", "when": "Sat 21 Nov, Las Vegas", "color": "#00E5FF",
                    "title": "Verstappen 37 clear", "subtitle": "The fight for P2, with two races and 50 points left",
                    "standings": [["ANT", "402 pts"], ["VER", "304 pts"], ["HAM", "267 pts"], ["RUS", "264 pts"],
                                  ["NOR", "264 pts"], ["LEC", "250 pts"]],
                    "notes_label": "WHAT IT MEANS",
                    "notes": ["Hamilton 37 back, Russell and Norris 40",
                              "Leclerc is 54 back: out of the P2 fight",
                              "Teams: Ferrari 77 up on Red Bull, 86 left"],
                    "source": "Sources: formula1.com standings, RaceFans, RacingNews365, GPblog, grandprix.com, 22 Nov 2026",
                    "sources": [
                        "https://www.formula1.com/en/results/2026/drivers",
                        "https://www.racefans.net/2026/11/22/2026-las-vegas-grand-prix-race-result-and-championship-points/",
                        "https://racingnews365.com/2026-f1-championship-standings-after-las-vegas-grand-prix",
                        "https://www.gpblog.com/en/news/f1-standings-verstappen-moves-step-closer-to-securing-p2-with-las-vegas-win",
                        "https://www.grandprix.com/races/las-vegas-gp-2026-race-notes.html",
                        "https://scuderiafans.com/f1-driver-standings-2026-ferrari-positions-after-las-vegas-grand-prix/",
                    ],
                },
            ],
        },
    },
}


# 2026 grid: code -> (car number, team, team colour hex), from the official timing data of the last race
# (Supabase drivers, session 2026_20_R). Reserve drivers in FP1 are not in it: they show in grey.
DRIVERS: dict = {
    "NOR": (1, "McLaren", "F47600"), "PIA": (81, "McLaren", "F47600"),
    "VER": (3, "Red Bull", "4781D7"), "HAD": (6, "Red Bull", "4781D7"),
    "BOR": (5, "Audi", "F50537"), "HUL": (27, "Audi", "F50537"),
    "GAS": (10, "Alpine", "00A1E8"), "COL": (43, "Alpine", "00A1E8"),
    "PER": (11, "Cadillac", "909090"), "BOT": (77, "Cadillac", "909090"),
    "ANT": (12, "Mercedes", "00D7B6"), "RUS": (63, "Mercedes", "00D7B6"),
    "ALO": (14, "Aston Martin", "229971"), "STR": (18, "Aston Martin", "229971"),
    "LEC": (16, "Ferrari", "ED1131"), "HAM": (44, "Ferrari", "ED1131"),
    "ALB": (23, "Williams", "1868DB"), "SAI": (55, "Williams", "1868DB"),
    "LAW": (30, "Racing Bulls", "6C98FF"), "LIN": (41, "Racing Bulls", "6C98FF"),
    "BEA": (87, "Haas", "9C9FA2"), "CAM": (51, "Haas", "9C9FA2"),
}


# Feed carousels of session cards (Michel, 20 Nov: report FP2 and post the qualifying times). Key: the
# card list after "FEED:" in social __main__ mode news. "{dot:CODE}" becomes the team colour dot.
SESSION_FEEDS: dict = {
    "LAS VEGAS": {
        2026: {
            "FP2.2+QPRE.1": """🏁 FP2 in Las Vegas: Russell on top, late

{dot:RUS} George Russell, Mercedes: 1:47.272
{dot:GAS} Pierre Gasly, Alpine: +0.071
{dot:LEC} Charles Leclerc, Ferrari: +0.333

🌧️ Full wets first, then intermediates as the track dried. A red flag late on for plastic debris. Verstappen P13, 2.869s off.

⏱️ Qualifying tonight: 8 PM PT, 11 PM ET, 4 AM GMT and 5 AM CET on Saturday. Swipe for the times ➡️

⚠️ {dot:PIA} Piastri starts 10 places down after his fifth combustion engine of 2026.

Who takes pole on the Strip? Drop your pick below 👇

Sources: GPblog, PlanetF1, Crash.net, RacingNews365, formula1.com, The Race, McLaren

#F1 #LasVegasGP #Formula1 #F1Telemetry #Qualifying""",
        },
    },
}


# Grid pole when the fastest qualifier does not start from pole (grid penalty). (season, round) -> driver code.
# Las Vegas 2026: Antonelli fastest, five place drop for a sixth combustion engine; Verstappen starts from pole
# (GPblog, Pit Debrief, Crash.net, formula1.com, 21 Nov 2026).
GRID_POLE = {(2026, 21): "VER"}


def grid_pole(season, rnd, fastest: str):
    """The driver starting from pole when that is not the fastest qualifier, else None."""
    gp = GRID_POLE.get((season, rnd))
    return gp if gp and gp != fastest else None


# Official best qualifying laps of drivers outside the session report's standings, for comparison Reels while Jolpica
# has not published. Las Vegas 2026: PlanetF1 and grandprix.com (Q1 and Q2 columns), Pit Debrief, The Race, 21 Nov 2026.
Q_EXTRA = {("LAS VEGAS", 2026): {"LEC": "1:35.040", "HAM": "1:35.253"}}
