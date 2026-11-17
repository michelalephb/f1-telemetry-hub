"""Brand: @f1telemetryhub dark theme (project spec section 4) and fonts."""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

BG = "#0B0E14"
CARD = "#141923"
BORDER = "#232D3F"
INK = "#E6EAF2"
MUTE = "#8A94A6"
CYAN = "#00E5FF"
PURPLE = "#A855F7"
GAIN = "#10B981"
LOSS = "#EF4444"
GOLD = "#F5C542"
COMPOUND = {"SOFT": "#FF3333", "MEDIUM": "#FFF200", "HARD": "#FFFFFF", "INTERMEDIATE": "#39B54A", "WET": "#00AEEF"}

# ---- Brand palette (Instagram), one system for every post ----
# Obsidian base, Bone ink, Champagne for structure (labels, rules), one fun ACCENT used once per
# slide for the hero element. The accent must not collide with any team colour, because drivers
# are drawn in team colours.
OBSIDIAN = "#0B0B0C"
OBSIDIAN_LIFT = "#17161A"
BONE = "#EDE8DF"
STONE = "#8D877C"
CHAMPAGNE = "#C9A96E"
HAIRLINE = "#3A3630"
# "Paddock Cyan" (locked 15 Nov 2026, Michel): brand cyan accent, a dash of luxury (thin type,
# champagne hairlines), obsidian base. Each GP may carry its own track line colour (EVENT_LINE);
# Las Vegas is hot pink, every other GP defaults to cyan.
INK_BG_TOP = "#0E121A"
INK_BG_BOTTOM = "#05070B"
TEXT = "#F2F4F7"
MUTED = "#8A93A3"
ACCENT = CYAN = "#00E5FF"
GOLD_HAIR = CHAMPAGNE        # the dash of luxury: thin rules and the round label only
TRACK_BASE = "#2A3242"
EVENT_LINE = {"Las Vegas": "#FF3D8B"}


def event_line(location: str | None) -> str:
    for k, v in EVENT_LINE.items():
        if location and k.lower() in location.lower():
            return v
    return CYAN


# Host country (as Jolpica / OpenF1 name it) to ISO code for the flag PNGs in ./flags
# (rendered from country-flag-icons, MIT, the same set the website uses).
COUNTRY_ISO = {
    "Argentina": "AR", "Australia": "AU", "Austria": "AT", "Azerbaijan": "AZ", "Bahrain": "BH", "Belgium": "BE",
    "Brazil": "BR", "Canada": "CA", "China": "CN", "France": "FR", "Germany": "DE", "Hungary": "HU", "India": "IN",
    "Italy": "IT", "Japan": "JP", "Korea": "KR", "South Korea": "KR", "Malaysia": "MY", "Mexico": "MX", "Monaco": "MC",
    "Morocco": "MA", "Netherlands": "NL", "Portugal": "PT", "Qatar": "QA", "Russia": "RU", "Saudi Arabia": "SA",
    "Singapore": "SG", "South Africa": "ZA", "Spain": "ES", "Sweden": "SE", "Switzerland": "CH", "Thailand": "TH",
    "Turkey": "TR", "Türkiye": "TR", "UAE": "AE", "United Arab Emirates": "AE", "UK": "GB", "United Kingdom": "GB",
    "Great Britain": "GB", "USA": "US", "United States": "US", "Vietnam": "VN", "Rwanda": "RW",
}
FLAGS = Path(__file__).resolve().parent / "flags"


def flag_image(country: str | None):
    iso = COUNTRY_ISO.get(country or "")
    f = FLAGS / f"{iso}.png" if iso else None
    return plt.imread(str(f)) if f and f.exists() else None

HANDLE = "@f1telemetryhub"
SITE = "f1telemetryhub.com"
# Michel's wordmark (03_logo_black.png), recoloured to TEXT for the dark cards. Every post carries it.
LOGO = Path(__file__).resolve().parent / "assets" / "f1th_logo_white_20261116_v01.png"
LOGO_ASPECT = 2190 / 300

HEAD = "DejaVu Sans"
MONO = "DejaVu Sans Mono"


def load_fonts() -> None:
    """Space Grotesk and JetBrains Mono from $SOCIAL_FONTS (the workflow downloads them), else Inter, else DejaVu."""
    global HEAD, MONO
    d = os.environ.get("SOCIAL_FONTS")
    if d and Path(d).is_dir():
        for f in Path(d).glob("*.ttf"):
            try:
                font_manager.fontManager.addfont(str(f))
            except Exception:
                pass
    names = {f.name for f in font_manager.fontManager.ttflist}
    # Paddock Cyan (template v01): Inter everywhere, thin numbers; charts sit on the card gradient.
    HEAD = next((n for n in ("Inter", "Space Grotesk", "DejaVu Sans") if n in names), "DejaVu Sans")
    MONO = next((n for n in ("Inter", "JetBrains Mono", "DejaVu Sans Mono") if n in names), "DejaVu Sans Mono")
    plt.rcParams.update({
        "font.family": HEAD, "text.color": TEXT, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.edgecolor": "#3A4458", "axes.facecolor": "none", "figure.facecolor": BG, "savefig.facecolor": BG,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#1E2533",
        "grid.linewidth": 0.6, "font.size": 18, "font.weight": 300,
    })


def logo_image():
    """Fails loudly: no post may go out without the logo."""
    if not LOGO.exists():
        raise FileNotFoundError(f"brand logo missing: {LOGO}")
    return plt.imread(str(LOGO))
