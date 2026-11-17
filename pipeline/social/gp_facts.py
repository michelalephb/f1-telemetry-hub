"""Hand checked facts per Grand Prix that no API gives us: Pirelli's compound choice and the history
reel. Every entry carries its source. A GP with no entry simply gets no tyre card or history reel:
nothing is ever guessed. Add the next GP here once its numbers are checked against the sources.

Keys are Preview.title (the OpenF1 location, upper case).
"""
from __future__ import annotations

# Compound colours as F1 broadcasts show them (project spec, Graphic 3).
COMPOUND_COLOR = {"SOFT": "#FF3333", "MEDIUM": "#FFF200", "HARD": "#F2F4F7",
                  "INTER": "#39B54A", "WET": "#00AEEF"}

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
    # LUSAIL left out on purpose: Pirelli gives Qatar the hardest trio (C1 C2 C3), but the tyre
    # card and captions say "softest 3 of 5", which would be wrong for it.
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
