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

HANDLE = "@f1telemetryhub"
SITE = "f1telemetryhub.com"
LOGO = Path(__file__).resolve().parents[2] / "web" / "public" / "logo.png"

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
    HEAD = next((n for n in ("Space Grotesk", "Inter", "DejaVu Sans") if n in names), "DejaVu Sans")
    MONO = next((n for n in ("JetBrains Mono", "DejaVu Sans Mono") if n in names), "DejaVu Sans Mono")
    plt.rcParams.update({
        "font.family": HEAD, "text.color": INK, "axes.labelcolor": MUTE, "xtick.color": MUTE, "ytick.color": MUTE,
        "axes.edgecolor": BORDER, "axes.facecolor": BG, "figure.facecolor": BG, "savefig.facecolor": BG,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": BORDER,
        "grid.linewidth": 0.8, "font.size": 18,
    })


def logo_image():
    if LOGO.exists():
        try:
            return plt.imread(str(LOGO))
        except Exception:
            return None
    return None
