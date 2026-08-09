"""Centralized theming: a single source of truth for the app's color
palette and for which CustomTkinter native theme file backs it.

This replaces the previous pattern of a frozen ``ColorPalette`` dataclass
sitting in a bare module-level ``colors`` variable that every widget
constructor injected by hand. Two things changed:

1. Generic/structural widgets (plain frames, labels, entries, switches,
   sliders, checkboxes, buttons with no special branding) now take their
   colors from ``theme.json`` via CustomTkinter's own theming
   engine — call :func:`theme_manager.load` once at startup and simply
   stop passing ``fg_color``/``text_color`` to those widgets.
2. Widgets that legitimately need a specific brand/status color (the
   accent CTA button, success/error pills, glass-panel overlays,
   sparkline strokes, etc.) still need an explicit value — that value
   now comes from ``theme_manager.colors`` instead of a bare global.

Only ``paper``/``paper_noir`` force a specific Tk appearance mode;
``liquid_glass``/``crystal`` follow the OS and are distinguished purely
by the window vibrancy effect applied on top (see ``ui_support.py``). The
color palette itself is identical across all four themes — CustomTkinter's
native ``(light, dark)`` tuple convention is what makes each color
automatically track the active appearance mode.
"""

from __future__ import annotations

import customtkinter as ctk

from typing import Dict
from dataclasses import dataclass
from pathlib import Path


THEME_JSON_PATH = Path(__file__).resolve().parent / "theme.json"


@dataclass(frozen=True)
class ColorPalette:
    # Backgrounds
    bg_light: str = "#eef0f3"
    bg_dark: str = "#0a0a0c"

    # Glass
    glass_light: str = "#ffffff"
    glass_dark: str = "#1a1a1e"
    glass_overlay_light: str = "#f4f5f8"
    glass_overlay_dark: str = "#151518"

    # Accents
    accent_blue: str = "#007AFF"
    accent_blue_hover: str = "#0056CC"
    accent_green: str = "#32D74B"
    accent_red: str = "#FF453A"
    accent_orange: str = "#FF9F0A"

    # Text
    text_primary_light: str = "#1d1d1f"
    text_primary_dark: str = "#f5f5f7"
    text_secondary_light: str = "#515154"
    text_secondary_dark: str = "#a1a1a6"
    text_tertiary_light: str = "#8e8e93"
    text_tertiary_dark: str = "#636366"

    # Borders
    border_light: str = "#dde1e6"
    border_dark: str = "#2c2c2e"
    separator_light: str = "#e4e6ea"
    separator_dark: str = "#1c1c1e"

    # Status
    status_success: str = "#32D74B"
    status_warning: str = "#FF9F0A"
    status_error: str = "#FF453A"
    status_info: str = "#007AFF"


# Theme keys are visual-effect skins layered on top of the one shared
# palette above; they do not change any color value themselves.
THEME_KEYS = ("liquid_glass", "crystal", "paper", "paper_noir")

_THEME_KEY_ALIASES: Dict[str, str] = {
    "liquid": "liquid_glass",
    "liquid_glass": "liquid_glass",
    "liquid glass": "liquid_glass",
    "crystal": "crystal",
    "crystal_mode": "crystal",
    "paper": "paper",
    "flat": "paper",
    "light": "paper",
    "paper_noir": "paper_noir",
    "paper noir": "paper_noir",
    "noir": "paper_noir",
    "dark paper": "paper_noir",
    "dark": "paper_noir",
    "night": "paper_noir",
    "midnight": "paper_noir",
    "vibrancy": "liquid_glass",
    "enhanced_vibrancy": "liquid_glass",
}

# Themes that force a specific Tk appearance mode rather than following
# the OS. Anything not listed here uses "System".
_FORCED_APPEARANCE_MODE: Dict[str, str] = {
    "paper": "Light",
    "paper_noir": "Dark",
}


class ThemeManager:
    """Owns the color palette and the CustomTkinter theme-file wiring."""

    def __init__(self) -> None:
        self._colors = ColorPalette()
        self._loaded = False

    @property
    def colors(self) -> ColorPalette:
        return self._colors

    def load(self) -> None:
        """Point CustomTkinter at ``theme.json``. Call once, before the
        first widget is created."""
        if self._loaded:
            return
        ctk.set_default_color_theme(str(THEME_JSON_PATH))
        self._loaded = True

    @staticmethod
    def normalize_key(theme_key: str) -> str:
        """Map any accepted spelling/alias to a canonical theme key,
        defaulting to "paper_noir" for anything unrecognized."""
        key = str(theme_key or "").strip().lower()
        return _THEME_KEY_ALIASES.get(key, "paper_noir")

    @staticmethod
    def forced_appearance_mode(theme_key: str) -> str:
        """"Light"/"Dark" for themes that force a mode, else "System"."""
        return _FORCED_APPEARANCE_MODE.get(theme_key, "System")


theme_manager = ThemeManager()
