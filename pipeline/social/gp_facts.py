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
