"""The price card (Featured + Portfolio grids) and the price-history sparkline."""


from __future__ import annotations

import customtkinter as ctk
import tkinter as tk

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from core.config import config
from core.theme import theme_manager


# ==========================================================================
# CurrencyCardWidget
# ==========================================================================

class CurrencyCardWidget(ctk.CTkFrame):
    """Reusable currency card with fast update (no destroy/recreate)."""

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        *,
        on_remove: Optional[Callable[[str], None]] = None,
        on_open_detail: Optional[Callable[[str], None]] = None,
        show_remove: bool = False,
        font_getter: Optional[Callable[[int, bool], Tuple[Any, ...]]] = None,
        rtl: bool = False,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ):
        self._card_width = int(width or config.CARD_WIDTH)
        self._card_height = int(height or config.CARD_HEIGHT)

        super().__init__(
            parent,
            fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
            corner_radius=16,
            border_width=1,
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            width=self._card_width,
            height=self._card_height,
        )
        self.pack_propagate(False)

        self.symbol: str = ""
        self.currency_data: Dict[str, Any] = {}
        self._on_remove = on_remove
        self._on_open_detail = on_open_detail
        self._show_remove = show_remove

        self.font_getter = font_getter or (lambda size, bold=False: (config.FALLBACK_FONT, size, "bold") if bold else (config.FALLBACK_FONT, size))
        self.rtl = rtl

        # Header row
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=16, pady=(14, 6))

        badge_side = "right" if self.rtl else "left"
        name_side = "right" if self.rtl else "left"
        remove_side = "left" if self.rtl else "right"

        self.symbol_badge = ctk.CTkFrame(
            self.header,
            fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            corner_radius=8,
            width=44,
            height=26,
        )
        self.symbol_badge.pack(side=badge_side)
        self.symbol_badge.pack_propagate(False)

        self.symbol_label = ctk.CTkLabel(
            self.symbol_badge,
            text="---",
            font=self.font_getter(10, True),
            text_color="white",
        )
        self.symbol_label.place(relx=0.5, rely=0.5, anchor="center")

        self.name_label = ctk.CTkLabel(
            self.header,
            text="",
            font=self.font_getter(14, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
            justify="right" if self.rtl else "left",
            wraplength=int(self._card_width * 0.62),
        )
        self.name_label.pack(side=name_side, padx=(12, 8), fill="x", expand=True)

        self.remove_btn: Optional[ctk.CTkButton] = None
        if self._show_remove:
            self.remove_btn = ctk.CTkButton(
                self.header,
                text="✕",
                width=32,
                height=28,
                corner_radius=10,
                fg_color=(theme_manager.colors.separator_light, theme_manager.colors.separator_dark),
                hover_color=(theme_manager.colors.accent_orange, theme_manager.colors.accent_orange),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                border_width=1,
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
                command=self._remove_clicked,
            )
            self.remove_btn.pack(side=remove_side)

        # Price
        self.price_section = ctk.CTkFrame(self, fg_color="transparent")
        self.price_section.pack(fill="x", padx=16, pady=(0, 6))

        self.price_label = ctk.CTkLabel(
            self.price_section,
            text="—",
            font=self.font_getter(23, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.price_label.pack(fill="x")

        self.unit_label = ctk.CTkLabel(
            self.price_section,
            text="",
            font=self.font_getter(11, False),
            text_color=(theme_manager.colors.text_tertiary_light, theme_manager.colors.text_tertiary_dark),
            anchor="e" if self.rtl else "w",
            justify="right" if self.rtl else "left",
        )
        self.unit_label.pack(fill="x", pady=(2, 0))

        # Change pill
        self.change_pill = ctk.CTkFrame(self, corner_radius=12, height=28)
        self.change_pill.pack(fill="x", padx=16, pady=(6, 12))
        self.change_pill.pack_propagate(False)

        self.change_label = ctk.CTkLabel(
            self.change_pill,
            text="",
            font=self.font_getter(12, True),
        )
        self.change_label.place(relx=0.5, rely=0.5, anchor="center")

        self._set_change(None)

        clickable_children = [
            self, self.header, self.symbol_badge, self.symbol_label,
            self.name_label, self.price_section, self.price_label,
            self.unit_label, self.change_pill, self.change_label,
        ]
        for widget in clickable_children:
            widget.bind("<Button-1>", self._card_clicked)
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass

    def _card_clicked(self, _event: Any = None) -> None:
        if self._on_open_detail and self.symbol:
            self._on_open_detail(self.symbol)

    def set_typography(
        self,
        *,
        font_getter: Optional[Callable[[int, bool], Tuple[Any, ...]]] = None,
        rtl: Optional[bool] = None,
    ) -> None:
        if font_getter is not None:
            self.font_getter = font_getter
        if rtl is not None:
            self.rtl = rtl

        try:
            self.symbol_label.configure(font=self.font_getter(10, True))
            self.name_label.configure(
                font=self.font_getter(14, True),
                anchor="e" if self.rtl else "w",
                justify="right" if self.rtl else "left",
            )
            self.price_label.configure(font=self.font_getter(23, True), anchor="e" if self.rtl else "w")
            self.unit_label.configure(
                font=self.font_getter(11, False),
                anchor="e" if self.rtl else "w",
                justify="right" if self.rtl else "left",
            )
            self.change_label.configure(font=self.font_getter(12, True))
        except Exception:
            pass

    def _remove_clicked(self) -> None:
        if self._on_remove and self.symbol:
            self._on_remove(self.symbol)

    @staticmethod
    def _format_price(price: Any) -> str:
        try:
            val = float(price)
            if val >= 1_000_000_000:
                return f"{val/1_000_000_000:.2f}B"
            if val >= 1_000_000:
                return f"{val/1_000_000:.2f}M"
            if val >= 100_000:
                return f"{val:,.0f}"
            if val >= 1_000:
                return f"{val:,.2f}"
            if val >= 1:
                return f"{val:.4f}"
            return f"{val:.6f}"
        except Exception:
            s = str(price)
            return s[:12] + "…" if len(s) > 12 else s

    def _set_change(self, change_percent: Any) -> None:
        try:
            val = float(change_percent)
            if val > 0:
                self.change_pill.configure(fg_color=theme_manager.colors.accent_green)
                self.change_label.configure(text=f"↗ +{val:.2f}%", text_color="white")
            elif val < 0:
                self.change_pill.configure(fg_color=theme_manager.colors.accent_red)
                self.change_label.configure(text=f"↘ {val:.2f}%", text_color="white")
            else:
                self.change_pill.configure(fg_color=(theme_manager.colors.separator_light, theme_manager.colors.separator_dark))
                self.change_label.configure(text="0.00%", text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark))
        except Exception:
            self.change_pill.configure(fg_color=(theme_manager.colors.separator_light, theme_manager.colors.separator_dark))
            self.change_label.configure(text="N/A", text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark))

    def update_data(self, currency: Dict[str, Any]) -> None:
        self.currency_data = dict(currency)
        sym = str(currency.get("symbol", "")).upper().strip()
        self.symbol = sym

        self.symbol_label.configure(text=sym[:4] if sym else "---")

        name = str(currency.get("name", sym or "Currency"))
        # Keep the UI stable; allow longer names but avoid stretching the header too much
        if len(name) > 36:
            name = name[:33] + "…"
        self.name_label.configure(text=name)

        self.price_label.configure(text=self._format_price(currency.get("price", "0")))
        self.unit_label.configure(text=str(currency.get("unit", "")))

        self._set_change(currency.get("change_percent", None))


# =============================================================================
# Desktop Widgets + History UI helpers
# =============================================================================


# ==========================================================================
# SparklineCanvas
# ==========================================================================

class SparklineCanvas(tk.Canvas):
    """Tiny, fast chart without matplotlib."""

    def __init__(self, parent: Any, width: int = 520, height: int = 110):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bd=0, relief="flat")
        self._values: List[float] = []
        self._padding = 8
        self._width = int(width)
        self._height = int(height)
        self._last_mode = None

    def _bg(self) -> str:
        mode = str(ctk.get_appearance_mode() or "").lower()
        if "dark" in mode:
            return theme_manager.colors.glass_overlay_dark
        return theme_manager.colors.glass_overlay_light

    def _fg(self) -> str:
        return theme_manager.colors.accent_blue

    def set_values(self, values: Sequence[float]) -> None:
        self._values = [float(v) for v in values if v is not None]
        self._redraw()

    def clear(self) -> None:
        self._values = []
        self.delete("all")
        self.configure(bg=self._bg())

    def _redraw(self) -> None:
        self.delete("all")
        self.configure(bg=self._bg())
        if len(self._values) < 2:
            return

        vals = self._values[-int(max(2, config.HISTORY_MAX_POINTS)) :]
        mn = min(vals)
        mx = max(vals)
        if mx - mn < 1e-9:
            mx = mn + 1.0

        w = self._width
        h = self._height
        pad = self._padding
        inner_w = max(10, w - 2 * pad)
        inner_h = max(10, h - 2 * pad)

        points = []
        n = len(vals)
        for i, v in enumerate(vals):
            x = pad + (i / (n - 1)) * inner_w
            # higher value -> higher on chart
            y = pad + (1.0 - (v - mn) / (mx - mn)) * inner_h
            points.append((x, y))

        # Draw polyline
        flat = []
        for x, y in points:
            flat.extend([x, y])
        try:
            self.create_line(*flat, fill=self._fg(), width=2, smooth=True)
        except Exception:
            self.create_line(*flat, fill=self._fg(), width=2)

        # Optional: baseline dots (subtle)
        try:
            self.create_oval(pad - 1, h - pad - 1, pad + 1, h - pad + 1, fill=self._fg(), outline="")
            self.create_oval(w - pad - 1, h - pad - 1, w - pad + 1, h - pad + 1, fill=self._fg(), outline="")
        except Exception:
            pass
