"""MainWindow mixins: dashboard layout, the floating action button dock, and section drag/show-hide customization."""


from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
import json

from typing import Any, Callable, Dict, List, Optional, Tuple
from core.theme import theme_manager
from tkinter import messagebox
from core.config import ConnectionStatus, config
from core.i18n import TRANSLATIONS, is_rtl
from core.utils import logger, IS_WINDOWS, PYWINSTYLES_AVAILABLE, pywinstyles, apply_dark_titlebar, apply_window_shape_region
from data.db import db_manager


# ==========================================================================
# LayoutMixin
# ==========================================================================

class LayoutMixin:
    """UI building blocks + top-level layout. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # UI building blocks
    # -------------------------------------------------------------------------

    def _create_glass_card(self, parent: ctk.CTkBaseClass, *, height: Optional[int] = None, glass_level: int = 1) -> ctk.CTkFrame:
        glass_colors = [
            (theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            (theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
        ]
        fg_color = glass_colors[min(max(glass_level - 1, 0), len(glass_colors) - 1)]
        kwargs: Dict[str, Any] = dict(
            fg_color=fg_color,
            corner_radius=16,
            border_width=1,
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
        )
        if height:
            kwargs["height"] = height
        frame = ctk.CTkFrame(parent, **kwargs)
        if height:
            frame.pack_propagate(False)
        return frame

    def _add_entry_context_menu(self, entry: ctk.CTkEntry) -> None:
        def show_menu(event):
            menu = None
            try:
                dark = ctk.get_appearance_mode() == "Dark"
                bg = theme_manager.colors.glass_overlay_dark if dark else theme_manager.colors.glass_overlay_light
                fg = theme_manager.colors.text_primary_dark if dark else theme_manager.colors.text_primary_light
                border = theme_manager.colors.border_dark if dark else theme_manager.colors.border_light
                menu = tk.Menu(
                    self, tearoff=0, bg=bg, fg=fg,
                    activebackground=theme_manager.colors.accent_blue, activeforeground="white",
                    bd=1, relief="flat", font=self._ui_font(11, False),
                    highlightthickness=1, highlightbackground=border,
                )
                menu.add_command(label=self._t("ctx_cut"), command=lambda: entry.event_generate("<<Cut>>"))
                menu.add_command(label=self._t("ctx_copy"), command=lambda: entry.event_generate("<<Copy>>"))
                menu.add_command(label=self._t("ctx_paste"), command=lambda: entry.event_generate("<<Paste>>"))
                menu.add_separator()
                menu.add_command(label=self._t("ctx_select_all"), command=lambda: (entry.select_range(0, "end"), entry.icursor("end")))
                menu.tk_popup(event.x_root, event.y_root)
            except Exception:
                pass
            finally:
                try:
                    if menu is not None:
                        menu.grab_release()
                except Exception:
                    pass

        try:
            entry.bind("<Button-3>", show_menu)
            entry.bind("<Button-2>", show_menu)  # some Linux/macOS configurations
        except Exception:
            pass

    def _create_button(
        self,
        parent: ctk.CTkBaseClass,
        *,
        text: str,
        command: Callable[[], None],
        style: str = "primary",
        width: Optional[int] = None,
    ) -> ctk.CTkButton:
        styles = {
            "primary": dict(
                fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
                hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
                text_color="white",
                border_width=0,
            ),
            "secondary": dict(
                fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                hover_color=(theme_manager.colors.separator_light, theme_manager.colors.separator_dark),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                border_width=0,
            ),
            "danger": dict(
                fg_color=(theme_manager.colors.accent_red, theme_manager.colors.accent_red),
                hover_color=(theme_manager.colors.accent_orange, theme_manager.colors.accent_orange),
                text_color="white",
                border_width=0,
            ),
        }
        cfg = styles.get(style, styles["primary"]).copy()
        kwargs: Dict[str, Any] = dict(
            text=text,
            command=command,
            font=self._ui_font(13, False),
            corner_radius=14,
            height=40,
        )
        if width:
            kwargs["width"] = width
        kwargs.update(cfg)
        return ctk.CTkButton(parent, **kwargs)

    # -------------------------------------------------------------------------
    # UI layout
    # -------------------------------------------------------------------------

    def _create_user_interface(self) -> None:
        self.main_container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)
        self.main_container.grid_columnconfigure(0, weight=1)
        # Scrollable content
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.main_container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            scrollbar_button_hover_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
        )
        self.scroll_frame.pack(fill="both", expand=True)
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        self._ui_row = 0

        builders: Dict[str, Callable[[], None]] = {
            "hero": self._create_hero_section,
            "status": self._create_status_section,
            "featured": self._create_featured_section,
            "insights": self._create_insights_section,
            "history": self._create_history_section,
            "portfolio": self._create_portfolio_section,
            "converter": self._create_converter_section,
            "widgets": self._create_widgets_section,
            "controls": self._create_controls_section,
            "settings": self._create_settings_section,
            "theme": self._create_theme_section,
        }

        order = list(getattr(self, "section_order", []) or builders.keys())
        enabled_map = dict(getattr(self, "section_enabled", {}) or {})

        for key in order:
            fn = builders.get(key)
            if not fn:
                continue
            if not enabled_map.get(key, True):
                continue
            fn()

        self._create_fab()

    def _next_row(self, inc: int = 1) -> int:
        r = self._ui_row
        self._ui_row += inc
        return r


# ==========================================================================
# FabMixin
# ==========================================================================

class FabMixin:
    """Floating action button + quick-access menu. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # Floating action button / quick-access menu
    # -------------------------------------------------------------------------

    _FAB_TRANSPARENT_KEY = "#ff00ff"  # matches the chroma key convention already used by DesktopWidgetWindow

    def _create_fab(self) -> None:
        try:
            if getattr(self, "fab_dock", None) is not None:
                return
        except Exception:
            pass

        try:
            # fab_dock previously sat directly on `self` with an assumed flat
            # bg_color. That can't actually work: fab_dock floats on top of
            # scrollable page content, and whatever is really behind it varies
            # with scroll position and theme — no single static color can match
            # it. This app already solves exactly this shape of problem for
            # DesktopWidgetWindow using real OS-level transparency, so fab_dock
            # gets its own tiny always-on-top window and a true transparent
            # hole everywhere except the rounded pill itself. `self.fab_window`
            # was already declared and cleaned up elsewhere in this class as a
            # `ctk.CTkToplevel` — this is what actually populates it.
            key = self._FAB_TRANSPARENT_KEY
            self.fab_window = ctk.CTkToplevel(self)
            
            try:
                self.fab_window.transient(self)
                if IS_WINDOWS:
                    self.fab_window.wm_attributes("-toolwindow", True)
            except Exception:
                pass

            self.fab_window.overrideredirect(True)
            try:
                self.fab_window.attributes("-topmost", False)
            except Exception:
                pass
            self.fab_window.configure(fg_color=key)
            if IS_WINDOWS:
                try:
                    self.fab_window.wm_attributes("-transparentcolor", key)
                except Exception:
                    pass

            self.fab_dock = ctk.CTkFrame(
                self.fab_window,
                fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                # On Windows the Toplevel itself is punched transparent above,
                # so fab_dock's own corner-filler only needs to match that same
                # chroma key to vanish completely, regardless of what the app
                # is actually showing behind it. Off Windows there's no
                # OS-level transparency to lean on, so fall back to the best
                # static approximation — still kept in sync in
                # ThemeMixin._apply_theme_with_feedback on every theme switch.
                bg_color=key if IS_WINDOWS else (theme_manager.colors.bg_light, theme_manager.colors.bg_dark),
                corner_radius=22,
                # A gray border anti-aliased against the magenta key produces
                # a visible pink/red fringe — Windows only keys out pixels
                # that are the *exact* key color, and the blended edge pixels
                # never are. Dropping the border on Windows means the only
                # anti-aliasing left is fg_color-against-key, which is far
                # less visible since glass_overlay is dark and close to the
                # key's own darkness. Off Windows keep the visible border,
                # since there's no transparency to protect there anyway.
                border_width=0 if IS_WINDOWS else 1,
                border_color=key if IS_WINDOWS else (theme_manager.colors.border_light, theme_manager.colors.border_dark),
            )
            self.fab_dock.pack(fill="both", expand=True)

            # crypto_toggle_button now drives both modes' price-basis pill
            # (see _toggle_price_basis / _price_basis_label). Left unpacked
            # here; _update_price_basis_toggle() packs it once, and it's
            # never unpacked again -- collapse/expand is done by animating
            # fab_window's width (_animate_fab_dock), not pack/forget.
            self.crypto_toggle_button = ctk.CTkButton(
                self.fab_dock,
                text="",
                width=64,
                height=38,
                corner_radius=19,
                font=self._ui_font(13, True),
                fg_color="transparent",
                # Real backdrop here is fab_dock's own fg_color (a solid,
                # fully-covered surface, never the chroma key) — matching it
                # explicitly is correct on every platform, unchanged from before.
                bg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                hover_color=(theme_manager.colors.separator_light, theme_manager.colors.separator_dark),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                border_width=0,
                command=self._toggle_price_basis,
            )

            self.fab_button = ctk.CTkButton(
                self.fab_dock,
                text="⋮",
                width=38,
                height=38,
                corner_radius=19,
                font=self._ui_font(20, True),
                fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
                hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
                text_color="white",
                border_width=0,
                command=self._fab_toggle_menu,
            )
            # Constant padding -- collapsed/expanded is just a measured
            # window width, see _recalculate_fab_dock_widths.
            self.fab_button.pack(side="right", padx=(6, 6), pady=6)

            # Packs the pill once and measures collapsed vs expanded widths.
            self._update_price_basis_toggle()

            self._fab_menu_open = False
            self._fab_closing = False
            self._fab_anim_job = None
            self._fab_close_anim_job = None
            self._fab_dock_anim_job = None

            self._reposition_fab()
            self.fab_window.deiconify()
        except Exception as e:
            logger.debug(f"FAB creation failed: {e}")

    def _price_basis_label(self) -> str:
        """Crypto mode: USDT vs Toman. Normal mode: USD vs Toman (default)."""
        if getattr(self, "app_mode", "normal") == "crypto":
            symbol = "USDT" if getattr(self, "crypto_price_basis", "usdt") == "usdt" else self._t("mode_irr_short")
        else:
            usd_label = "دلار" if self.language == "fa" else "USD"
            symbol = usd_label if getattr(self, "normal_price_basis", "irr") == "usd" else self._t("mode_irr_short")
        return f"⇄ {symbol}"

    def _toggle_price_basis(self) -> None:
        """Flip the active mode's price basis and refresh the cards."""
        try:
            if getattr(self, "app_mode", "normal") == "crypto":
                self.crypto_price_basis = "irr" if self.crypto_price_basis == "usdt" else "usdt"
                db_manager.save_preference("crypto_price_basis", self.crypto_price_basis)
            else:
                self.normal_price_basis = "usd" if self.normal_price_basis == "irr" else "irr"
                db_manager.save_preference("normal_price_basis", self.normal_price_basis)
            self._update_price_basis_toggle()
            self._render_featured_cards()
            self._render_portfolio_cards()
        except Exception as e:
            logger.debug(f"Price basis toggle failed: {e}")

    def _update_price_basis_toggle(self) -> None:
        """Refresh the pill's label. Packed once and never unpacked again;
        collapse/expand happens via _animate_fab_dock instead."""
        try:
            if getattr(self, "crypto_toggle_button", None) is None:
                return
            self.crypto_toggle_button.configure(text=self._price_basis_label())
            if not self.crypto_toggle_button.winfo_ismapped():
                self.crypto_toggle_button.pack(side="left", padx=(6, 2), pady=6, after=self.fab_button)
            self._recalculate_fab_dock_widths()
            self.after(10, self._reposition_fab)
        except Exception:
            pass

    def _recalculate_fab_dock_widths(self) -> None:
        """Measure the dock collapsed vs expanded by briefly unpacking the
        pill, instead of hard-coding pixel widths (keeps DPI/font/language
        changes correct automatically)."""
        try:
            if getattr(self, "crypto_toggle_button", None) is None or getattr(self, "fab_dock", None) is None:
                return
            self.update_idletasks()
            self._fab_dock_expanded_width = max(1, self.fab_dock.winfo_reqwidth())
            self.crypto_toggle_button.pack_forget()
            self.update_idletasks()
            self._fab_dock_solo_width = max(1, self.fab_dock.winfo_reqwidth())
            self.crypto_toggle_button.pack(side="left", padx=(6, 2), pady=6, after=self.fab_button)
            self.update_idletasks()
        except Exception:
            pass

    def _current_fab_dock_width(self) -> int:
        try:
            self.update_idletasks()
            w = int(self.fab_window.winfo_width())
            return w if w > 1 else int(self._fab_dock_solo_width or 1)
        except Exception:
            return int(self._fab_dock_solo_width or 1)

    def _animate_fab_dock(self, start_w: int, end_w: int, steps: int, step: int, *, opening: bool) -> None:
        """Grows/shrinks fab_window's width with the right edge pinned, so
        the pill slides out from behind the ⋮ button. fab_button is packed
        before the pill, so it always keeps its own space; the pill just
        runs out of cavity and gets clipped as the window narrows -- no
        pack_forget needed. Same timing/easing as _fab_animate/_fab_animate_close."""
        try:
            if getattr(self, "fab_window", None) is None or not self.fab_window.winfo_exists():
                return
            self.update_idletasks()
            dock_h = max(self.fab_dock.winfo_reqheight(), 1)
            right_edge = self.winfo_rootx() + self.winfo_width() - 28
            y = self.winfo_rooty() + self.winfo_height() - dock_h - 28
            t = step / float(max(1, steps))
            t = (1 - (1 - t) ** 3) if opening else (t * t)  # matches _fab_animate / _fab_animate_close
            w = int(start_w + (end_w - start_w) * t)
            x = right_edge - w
            self.fab_window.geometry(f"{w}x{dock_h}+{max(x, 0)}+{max(y, 0)}")
            if step < steps:
                delay = 11 if opening else 10
                self._fab_dock_anim_job = self.after(
                    delay, lambda: self._animate_fab_dock(start_w, end_w, steps, step + 1, opening=opening)
                )
            else:
                self._fab_dock_anim_job = None
                self._reposition_fab()
        except Exception:
            self._fab_dock_anim_job = None

    def _open_fab_dock(self) -> None:
        """Expand the dock, timed with the quick-access menu opening."""
        try:
            if getattr(self, "_fab_dock_anim_job", None):
                self.after_cancel(self._fab_dock_anim_job)
                self._fab_dock_anim_job = None
            if not self._fab_dock_expanded_width or not self._fab_dock_solo_width:
                self._recalculate_fab_dock_widths()
            start_w = self._current_fab_dock_width()
            self._animate_fab_dock(start_w, self._fab_dock_expanded_width, steps=11, step=0, opening=True)
        except Exception:
            pass

    def _close_fab_dock(self) -> None:
        """Collapse the dock, timed with the quick-access menu closing."""
        try:
            if getattr(self, "_fab_dock_anim_job", None):
                self.after_cancel(self._fab_dock_anim_job)
                self._fab_dock_anim_job = None
            if not self._fab_dock_expanded_width or not self._fab_dock_solo_width:
                self._recalculate_fab_dock_widths()
            start_w = self._current_fab_dock_width()
            self._animate_fab_dock(start_w, self._fab_dock_solo_width, steps=8, step=0, opening=False)
        except Exception:
            pass

    def _set_fab_visible(self, visible: bool) -> None:
        self._fab_visible = bool(visible)
        try:
            if getattr(self, "fab_window", None) is not None and self.fab_window.winfo_exists():
                if visible:
                    self._reposition_fab()
                    self.fab_window.deiconify()
                    self.fab_window.lift()
                else:
                    self.fab_window.withdraw()
        except Exception:
            pass

    def _reposition_fab(self) -> None:
        try:
            if getattr(self, "fab_window", None) is None or not self.fab_window.winfo_exists():
                return
            if not getattr(self, "_fab_visible", True):
                return
            if getattr(self, "_fab_dock_anim_job", None):
                return  # dock animation owns the geometry right now
            self.update_idletasks()
            expanded = bool(getattr(self, "_fab_menu_open", False))
            dock_w = (self._fab_dock_expanded_width if expanded else self._fab_dock_solo_width) or self.fab_dock.winfo_reqwidth()
            dock_w = max(int(dock_w), 1)
            dock_h = max(self.fab_dock.winfo_reqheight(), 1)
            x = self.winfo_rootx() + self.winfo_width() - dock_w - 28
            y = self.winfo_rooty() + self.winfo_height() - dock_h - 28
            self.fab_window.geometry(f"{dock_w}x{dock_h}+{max(x, 0)}+{max(y, 0)}")
            self.fab_window.lift()
        except Exception:
            pass

    def _fab_toggle_menu(self) -> None:
        if self._fab_menu_open:
            self._fab_close_menu()
        else:
            self._fab_open_menu()

    def _fab_open_menu(self) -> None:
        if self._fab_menu_open or self._fab_closing:
            return
        try:
            if self._fab_anim_job:
                self.after_cancel(self._fab_anim_job)
                self._fab_anim_job = None
        except Exception:
            pass

        try:
            if self.fab_menu_frame is not None:
                self.fab_menu_frame.destroy()
        except Exception:
            pass

        try:
            panel = ctk.CTkToplevel(self)
            panel.overrideredirect(True)
            try:
                panel.attributes("-topmost", True)
            except Exception:
                pass
            panel.transient(self)
            try:
                panel.configure(fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark))
            except Exception:
                pass
            self.fab_menu_frame = panel

            card = ctk.CTkFrame(
                panel,
                fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                corner_radius=20,
                border_width=1,
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
                width=260,
            )
            card.pack(fill="both", expand=True)

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=14, pady=14)

            title = ctk.CTkLabel(
                inner,
                text=self._t("fab_menu_title"),
                font=self._ui_font(14, True),
                text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
                anchor="e" if self.rtl else "w",
            )
            title.pack(fill="x", pady=(0, 8))

            self._fab_menu_buttons = {}

            def add_item(key: str, text: str, cmd: Callable[[], None]) -> None:
                btn = self._create_button(inner, text=text, command=cmd, style="secondary", width=228)
                btn.pack(fill="x", pady=4)
                self._fab_menu_buttons[key] = btn

            add_item("mode", self._fab_mode_label(), self._fab_toggle_mode)
            if self.connection_status in (ConnectionStatus.ERROR, ConnectionStatus.DISCONNECTED, ConnectionStatus.RATE_LIMITED):
                add_item("refresh", self._t("fab_refresh"), self._fab_refresh_now)
            add_item("language", self._fab_language_label(), self._fab_toggle_language)
            add_item("theme", self._fab_theme_label(), self._fab_open_theme_popup)
            add_item("session", self._t("fab_session"), self._fab_show_session_tracker)
            add_item("alerts", self._fab_alerts_label(), self._fab_show_alerts)
            add_item("api_test", self._t("fab_api_test"), self._fab_test_api)
            add_item("export", self._t("fab_export"), self._fab_export_csv)
            add_item("cache", self._t("fab_cache"), self._fab_clear_cache)
            add_item("performance", self._t("fab_performance"), self._fab_show_performance)
            add_item("converter", self._t("fab_converter"), self._fab_open_converter_popup)
            add_item("widgets", self._t("fab_widgets"), self._fab_open_widgets_popup)
            add_item("controls", self._t("fab_controls"), self._fab_open_controls_popup)
            add_item("settings", self._t("fab_settings"), self._fab_open_settings_popup)
            add_item("layout", self._t("fab_layout"), self._fab_open_layout)

            self._apply_theme_to_popup(panel)
            try:
                target_alpha = float(panel.attributes("-alpha"))
            except Exception:
                target_alpha = 1.0

            # Position above the FAB, anchored to the main window's bottom-right corner
            panel.update_idletasks()
            panel_w = max(260, panel.winfo_reqwidth())
            panel_h = panel.winfo_reqheight()
            self.update_idletasks()
            end_x = self.winfo_rootx() + self.winfo_width() - panel_w - 28
            end_y = self.winfo_rooty() + self.winfo_height() - panel_h - 96
            start_y = self.winfo_rooty() + self.winfo_height() - panel_h - 40
            try:
                panel.attributes("-alpha", 0.0)
            except Exception:
                pass
            panel.geometry(f"{panel_w}x{panel_h}+{end_x}+{start_y}")
            apply_window_shape_region(panel, panel_w, panel_h, radius=20)

            self._fab_panel_geom = (end_x, start_y, panel_w, panel_h, target_alpha)
            try:
                self.fab_button.configure(text="×")
            except Exception:
                pass

            self._fab_menu_open = True
            self._open_fab_dock()
            self._fab_animate(panel, panel_w, panel_h, end_x, start_y, end_y, steps=11, step=0,
                               start_alpha=0.0, end_alpha=target_alpha)
        except Exception as e:
            logger.debug(f"FAB menu open failed: {e}")

    def _apply_theme_to_popup(self, win: "ctk.CTkToplevel") -> None:
        """Make a popup visually match the currently active theme — real
        acrylic/blur on Windows via pywinstyles (same candidates the main
        window itself uses per theme), simulated translucency elsewhere.
        Paper / Paper Noir are intentionally flat (no glass), matching how
        those themes render on the main window."""
        theme = self._normalize_theme_key(self.selected_theme)
        try:
            if theme in ("paper", "paper_noir"):
                win.attributes("-alpha", 1.0)
                return

            candidates = {
                "liquid_glass": [("acrylic", 0.97), ("mica", 0.96), ("blur", 0.95), ("aero", 0.94)],
                "crystal": [("optimised", 0.89), ("acrylic", 0.88), ("blur", 0.90)],
            }.get(theme, [("acrylic", 0.97), ("blur", 0.95)])

            if IS_WINDOWS and PYWINSTYLES_AVAILABLE:
                for style_name, alpha in candidates:
                    try:
                        pywinstyles.apply_style(win, style_name)  # type: ignore[name-defined]
                        win.attributes("-alpha", alpha)
                        return
                    except Exception:
                        continue
            win.attributes("-alpha", 0.97 if theme == "liquid_glass" else 0.96)
        except Exception:
            pass

    def _fab_animate(
        self,
        panel: "ctk.CTkToplevel",
        w: int,
        h: int,
        x: int,
        start_y: int,
        end_y: int,
        steps: int,
        step: int,
        start_alpha: Optional[float] = None,
        end_alpha: Optional[float] = None,
    ) -> None:
        try:
            if panel is None or not panel.winfo_exists():
                return
            t = step / float(max(1, steps))
            t = 1 - (1 - t) ** 3  # ease-out cubic — smoother, more native-feeling deceleration
            y = int(start_y + (end_y - start_y) * t)
            panel.geometry(f"{w}x{h}+{x}+{y}")
            if start_alpha is not None and end_alpha is not None:
                try:
                    panel.attributes("-alpha", start_alpha + (end_alpha - start_alpha) * t)
                except Exception:
                    pass
            if step < steps:
                self._fab_anim_job = self.after(
                    11, lambda: self._fab_animate(panel, w, h, x, start_y, end_y, steps, step + 1, start_alpha, end_alpha)
                )
            else:
                self._fab_anim_job = None
        except Exception:
            pass

    def _fab_close_menu(self) -> None:
        if not self._fab_menu_open:
            return
        self._fab_menu_open = False
        self._close_fab_dock()
        self._fab_closing = True
        try:
            self.fab_button.configure(text="⋮")
        except Exception:
            pass
        try:
            if self._fab_anim_job:
                self.after_cancel(self._fab_anim_job)
                self._fab_anim_job = None
        except Exception:
            pass
        try:
            if self._fab_close_anim_job:
                self.after_cancel(self._fab_close_anim_job)
                self._fab_close_anim_job = None
        except Exception:
            pass

        panel = self.fab_menu_frame
        geom = self._fab_panel_geom
        if panel is None or not panel.winfo_exists() or geom is None:
            self._fab_destroy_panel()
            return

        x, open_y, w, h, alpha = geom
        close_y = open_y + 24
        self._fab_animate_close(panel, w, h, x, open_y, close_y, alpha, steps=8, step=0)

    def _fab_animate_close(
        self,
        panel: "ctk.CTkToplevel",
        w: int,
        h: int,
        x: int,
        start_y: int,
        end_y: int,
        start_alpha: float,
        steps: int,
        step: int,
    ) -> None:
        try:
            if panel is None or not panel.winfo_exists():
                self._fab_destroy_panel()
                return
            t = step / float(max(1, steps))
            t = t * t  # ease-in — accelerates away, mirrors the ease-out entrance
            y = int(start_y + (end_y - start_y) * t)
            panel.geometry(f"{w}x{h}+{x}+{y}")
            try:
                panel.attributes("-alpha", max(0.0, start_alpha * (1 - t)))
            except Exception:
                pass
            if step < steps:
                self._fab_close_anim_job = self.after(
                    10, lambda: self._fab_animate_close(panel, w, h, x, start_y, end_y, start_alpha, steps, step + 1)
                )
            else:
                self._fab_close_anim_job = None
                self._fab_destroy_panel()
        except Exception:
            self._fab_destroy_panel()

    def _fab_destroy_panel(self) -> None:
        self._fab_closing = False
        try:
            if self.fab_menu_frame is not None:
                self.fab_menu_frame.destroy()
                self.fab_menu_frame = None
        except Exception:
            pass


    def _fab_language_label(self) -> str:
        lang_name = "فارسی" if self.language == "fa" else "English"
        return self._t("fab_language", lang_name=lang_name)

    def _fab_theme_label(self) -> str:
        return self._t("fab_theme", name=self._get_theme_display_name(self.selected_theme))

    def _fab_toggle_language(self) -> None:
        try:
            self.language = "en" if self.language == "fa" else "fa"
            self.rtl = is_rtl(self.language)
            db_manager.save_preference("language", self.language)
            self._rebuild_main_sections()
        except Exception:
            pass
        self._fab_close_menu()

    def _fab_open_section_popup(self, key: str, title_key: str, builder: Callable[..., None], width: int = 520, height: int = 420) -> None:
        self._fab_close_menu()

        # Avoid a second, out-of-sync instance if it's already pinned to the dashboard
        if self.section_enabled.get(key):
            name = self._t(title_key)
            self.toasts.show(self._t("toast_already_on_dashboard", name=name), duration=2400)
            return

        try:
            win = ctk.CTkToplevel(self)
            win.title(self._t(title_key))
            win.geometry(f"{width}x{height}")
            win.minsize(360, 260)
            win.transient(self)
            win.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
            apply_dark_titlebar(win, ctk.get_appearance_mode() == "Dark")
            self._apply_theme_to_popup(win)

            holder = ctk.CTkScrollableFrame(win, fg_color="transparent")
            holder.pack(fill="both", expand=True, padx=12, pady=(12, 6))

            builder(parent=holder)

            close_btn = self._create_button(win, text=self._t("btn_close"), command=win.destroy, style="secondary", width=140)
            close_btn.pack(pady=(0, 14))
        except Exception as e:
            logger.debug(f"FAB section popup failed for {key}: {e}")

    def _fab_open_theme_popup(self) -> None:
        self._fab_open_section_popup("theme", "section_theme", self._create_theme_section, width=420, height=260)

    def _fab_open_converter_popup(self) -> None:
        self._fab_open_section_popup("converter", "section_converter", self._create_converter_section, width=520, height=320)

    def _fab_open_widgets_popup(self) -> None:
        self._fab_open_section_popup("widgets", "section_widgets", self._create_widgets_section, width=560, height=480)

    def _fab_open_controls_popup(self) -> None:
        self._fab_open_section_popup("controls", "section_controls", self._create_controls_section, width=480, height=260)

    def _fab_open_settings_popup(self) -> None:
        self._fab_open_section_popup("settings", "section_settings", self._create_settings_section, width=560, height=520)

    def _fab_mode_label(self) -> str:
        mode_name = self._t("mode_crypto") if self.app_mode == "crypto" else self._t("mode_normal")
        return self._t("fab_mode", mode=mode_name)

    def _fab_toggle_mode(self) -> None:
        self._fab_close_menu()
        try:
            self.app_mode = "crypto" if self.app_mode == "normal" else "normal"
            db_manager.save_preference("app_mode", self.app_mode)

            if self.app_mode == "crypto":
                self.crypto_price_basis = "usdt"
                self._tether_irr_rate = None
            else:
                self.normal_price_basis = "irr"
            self._update_price_basis_toggle()

            # Stale data from the other mode must never linger on screen —
            # different symbol universes, different meaning entirely.
            self.currencies = {}
            self.featured_symbols = []
            for card in list(self.portfolio_cards.values()):
                try:
                    card.destroy()
                except Exception:
                    pass
            self.portfolio_cards.clear()
            for card in list(self.featured_cards.values()):
                try:
                    card.destroy()
                except Exception:
                    pass
            self.featured_cards.clear()

            self._render_featured_cards()
            self._render_portfolio_cards()
            self._update_currency_selector()

            mode_name = self._t("mode_crypto") if self.app_mode == "crypto" else self._t("mode_normal")
            self.toasts.show(self._t("toast_mode_switched", mode=mode_name), duration=2200)

            self._update_connection_status(ConnectionStatus.CONNECTING, self._t("status_connecting"))
            self.executor.submit(self._initial_refresh_worker)
        except Exception as e:
            logger.debug(f"Mode toggle failed: {e}")

    def _fab_refresh_now(self) -> None:
        self._fab_close_menu()
        try:
            self._manual_refresh()
            self.toasts.show(self._t("toast_refreshing_now"), duration=1600)
        except Exception:
            pass

    def _fab_open_layout(self) -> None:
        self._fab_close_menu()
        try:
            self._open_layout_popup()
        except Exception:
            pass

    def _open_currency_picker(
        self,
        options: List[Tuple[str, str]],
        on_select: Callable[[str], None],
        title: str,
        current: Optional[str] = None,
        initial_search: str = "",
        stay_open: bool = False,
    ) -> None:
        """options: list of (symbol, display_text). Native CTk dropdowns
        (CTkComboBox/CTkOptionMenu) use a plain tkinter.Menu for their list,
        which has no mouse-wheel support and no search — this replaces both
        with a proper searchable, scrollable popup."""
        try:
            win = ctk.CTkToplevel(self)
            win.title(title)
            win.geometry("380x460")
            win.minsize(320, 300)
            win.transient(self)
            win.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
            apply_dark_titlebar(win, ctk.get_appearance_mode() == "Dark")
            self._apply_theme_to_popup(win)

            card = ctk.CTkFrame(
                win,
                fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                corner_radius=16,
                border_width=1,
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            )
            card.pack(fill="both", expand=True, padx=14, pady=14)

            search_var = ctk.StringVar(value=str(initial_search or ""))
            search_entry = ctk.CTkEntry(
                card,
                textvariable=search_var,
                placeholder_text=self._t("placeholder_search"),
                height=38,
                corner_radius=10,
                fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                font=self._ui_font(13, False),
                justify="right" if self.rtl else "left",
            )
            search_entry.pack(fill="x", padx=12, pady=(12, 8))
            self._add_entry_context_menu(search_entry)

            list_holder = ctk.CTkScrollableFrame(card, fg_color="transparent")
            list_holder.pack(fill="both", expand=True, padx=8, pady=(0, 12))

            def pick(symbol: str) -> None:
                if not stay_open:
                    try:
                        win.destroy()
                    except Exception:
                        pass
                try:
                    on_select(symbol)
                except Exception as e:
                    logger.debug(f"Currency picker selection failed: {e}")
                if stay_open:
                    try:
                        options[:] = [t for t in options if t[0] != symbol]
                        rebuild()
                        search_entry.focus_set()
                    except Exception:
                        pass

            def rebuild(*_args) -> None:
                for child in list(list_holder.winfo_children()):
                    try:
                        child.destroy()
                    except Exception:
                        pass
                term = search_var.get().strip().lower()
                shown = 0
                for symbol, display in options:
                    if term and term not in display.lower() and term not in symbol.lower():
                        continue
                    is_current = current is not None and symbol == current
                    row = ctk.CTkButton(
                        list_holder,
                        text=display,
                        anchor="e" if self.rtl else "w",
                        height=34,
                        corner_radius=8,
                        fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue) if is_current else "transparent",
                        hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover) if is_current else (theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                        text_color="white" if is_current else (theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                        font=self._ui_font(13, False),
                        command=lambda s=symbol: pick(s),
                    )
                    row.pack(fill="x", pady=1)
                    shown += 1
                    if shown >= 400:
                        break  # keep the popup responsive even with thousands of options

            search_var.trace_add("write", rebuild)
            rebuild()

            try:
                search_entry.focus_set()
            except Exception:
                pass
            win.bind("<Escape>", lambda _e: win.destroy())
        except Exception as e:
            logger.debug(f"Currency picker failed: {e}")

    def _show_themed_message(self, title: str, message: str, kind: str = "info") -> None:
        """Themed, RTL-aware replacement for tkinter.messagebox — native message
        boxes never respected the app's theme (always plain OS light style)."""
        try:
            win = ctk.CTkToplevel(self)
            win.title(title)
            win.resizable(False, False)
            win.transient(self)
            win.grab_set()
            win.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
            apply_dark_titlebar(win, ctk.get_appearance_mode() == "Dark")
            self._apply_theme_to_popup(win)

            accent = theme_manager.colors.accent_red if kind == "error" else theme_manager.colors.accent_blue
            icon = "⚠️" if kind == "error" else "✅"

            card = ctk.CTkFrame(
                win,
                fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                corner_radius=18,
                border_width=1,
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            )
            card.pack(fill="both", expand=True, padx=16, pady=16)

            head = ctk.CTkLabel(
                card,
                text=f"{icon}  {title}",
                font=self._ui_font(15, True),
                text_color=(accent, accent),
                anchor="e" if self.rtl else "w",
            )
            head.pack(fill="x", padx=20, pady=(18, 6))

            body = ctk.CTkLabel(
                card,
                text=str(message),
                font=self._ui_font(13, False),
                text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
                anchor="e" if self.rtl else "w",
                justify="right" if self.rtl else "left",
                wraplength=360,
            )
            body.pack(fill="both", expand=True, padx=20, pady=(0, 14))

            ok_btn = self._create_button(win, text=self._t("btn_close") if "btn_close" in TRANSLATIONS.get(self.language, {}) else "OK", command=win.destroy, style="secondary", width=140)
            ok_btn.pack(pady=(0, 16))

            win.update_idletasks()
            w, h = max(360, win.winfo_reqwidth()), max(180, win.winfo_reqheight())
            win.geometry(f"{w}x{h}")
            win.minsize(w, h)
        except Exception as e:
            logger.debug(f"Themed message dialog failed: {e}")
            try:
                if kind == "error":
                    messagebox.showerror(title, message)
                else:
                    messagebox.showinfo(title, message)
            except Exception:
                pass

    def _fab_alerts_label(self) -> str:
        state = self._t("state_on") if self.alerts_enabled else self._t("state_off")
        return self._t("fab_alerts", state=state)

    def _fab_show_alerts(self) -> None:
        self._fab_close_menu()
        try:
            win = ctk.CTkToplevel(self)
            win.title(self._t("alerts_title"))
            win.geometry("440x420")
            win.resizable(False, False)
            win.transient(self)
            win.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
            apply_dark_titlebar(win, ctk.get_appearance_mode() == "Dark")
            self._apply_theme_to_popup(win)

            card = ctk.CTkFrame(
                win,
                fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                corner_radius=18,
                border_width=1,
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            )
            card.pack(fill="both", expand=True, padx=16, pady=16)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=18, pady=(16, 8))

            title = ctk.CTkLabel(
                header,
                text=self._t("alerts_title"),
                font=self._ui_font(16, True),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            )
            title.pack(side="right" if self.rtl else "left")

            toggle_var = ctk.BooleanVar(value=self.alerts_enabled)

            def on_toggle():
                self.alerts_enabled = bool(toggle_var.get())
                db_manager.save_preference("alerts_enabled", self.alerts_enabled)
                try:
                    if hasattr(self, "alerts_var"):
                        self.alerts_var.set(self.alerts_enabled)
                except Exception:
                    pass
                self.toasts.show(self._t("toast_alerts_on") if self.alerts_enabled else self._t("toast_alerts_off"), duration=1600)

            toggle = ctk.CTkSwitch(
                header,
                text=self._t("alerts_enable_label", threshold=self.alert_threshold_percent),
                variable=toggle_var,
                command=on_toggle,
                font=self._ui_font(12, False),
                progress_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            )
            toggle.pack(side="left" if self.rtl else "right")

            log_holder = ctk.CTkScrollableFrame(card, fg_color="transparent")
            log_holder.pack(fill="both", expand=True, padx=18, pady=(0, 12))

            if self._recent_alerts:
                for entry in self._recent_alerts:
                    row = ctk.CTkLabel(
                        log_holder,
                        text=entry,
                        font=self._ui_font(12, False),
                        text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
                        anchor="e" if self.rtl else "w",
                        justify="right" if self.rtl else "left",
                    )
                    row.pack(fill="x", pady=2)
            else:
                empty = ctk.CTkLabel(
                    log_holder,
                    text=self._t("alerts_empty"),
                    font=self._ui_font(12, False),
                    text_color=(theme_manager.colors.text_tertiary_light, theme_manager.colors.text_tertiary_dark),
                    wraplength=360,
                )
                empty.pack(fill="x", pady=20)

            close_btn = self._create_button(win, text=self._t("btn_close"), command=win.destroy, style="secondary", width=140)
            close_btn.pack(pady=(0, 14))
        except Exception as e:
            logger.debug(f"Alerts popup failed: {e}")

    def _fab_show_session_tracker(self) -> None:
        self._fab_close_menu()
        try:
            win = ctk.CTkToplevel(self)
            win.title(self._t("session_tracker_title"))
            win.geometry("440x380")
            win.resizable(False, False)
            win.transient(self)
            win.grab_set()
            win.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
            apply_dark_titlebar(win, ctk.get_appearance_mode() == "Dark")
            self._apply_theme_to_popup(win)

            card = ctk.CTkFrame(
                win,
                fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                corner_radius=18,
                border_width=1,
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            )
            card.pack(fill="both", expand=True, padx=16, pady=16)

            title = ctk.CTkLabel(
                card,
                text=self._t("session_tracker_title"),
                font=self._ui_font(16, True),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                anchor="e" if self.rtl else "w",
            )
            title.pack(fill="x", padx=18, pady=(16, 8))

            txt = self._build_session_summary_text() or self._t("session_tracker_empty")
            body = ctk.CTkLabel(
                card,
                text=txt,
                font=self._ui_font(13, False),
                text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
                anchor="e" if self.rtl else "w",
                justify="right" if self.rtl else "left",
                wraplength=380,
            )
            body.pack(fill="both", expand=True, padx=18, pady=(0, 12))

            close_btn = self._create_button(win, text=self._t("btn_close"), command=win.destroy, style="secondary", width=140)
            close_btn.pack(pady=(0, 16))
        except Exception as e:
            logger.debug(f"Session tracker popup failed: {e}")

    def _fab_test_api(self) -> None:
        self._fab_close_menu()
        try:
            self._test_api_connection()
        except Exception:
            pass

    def _fab_export_csv(self) -> None:
        self._fab_close_menu()
        try:
            self._export_csv()
        except Exception:
            pass

    def _fab_clear_cache(self) -> None:
        self._fab_close_menu()
        try:
            self._clear_cache()
        except Exception:
            pass

    def _fab_show_performance(self) -> None:
        self._fab_close_menu()
        try:
            self._show_performance_report()
        except Exception:
            pass

    def _refresh_fab_texts(self) -> None:
        try:
            if self.fab_menu_frame is not None and self._fab_menu_open:
                # Rebuild in place so labels/RTL/theme colors stay correct
                self._fab_close_menu()
                self._fab_open_menu()
        except Exception:
            pass

    


# ==========================================================================
# SectionCustomizationMixin
# ==========================================================================

class SectionCustomizationMixin:
    """Layout customization for sections. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # Layout customization (sections)
    # -------------------------------------------------------------------------

    def _save_layout_preferences(self) -> None:
        try:
            db_manager.save_preference("section_order_json", json.dumps(list(self.section_order)))
            db_manager.save_preference("section_enabled_json", json.dumps(dict(self.section_enabled)))
        except Exception:
            pass

    def _rebuild_main_sections(self) -> None:
        try:
            for child in list(self.scroll_frame.winfo_children()):
                child.destroy()
        except Exception:
            pass

        self._ui_row = 0

        builders: Dict[str, Callable[[], None]] = {
            "hero": self._create_hero_section,
            "status": self._create_status_section,
            "featured": self._create_featured_section,
            "insights": self._create_insights_section,
            "history": self._create_history_section,
            "portfolio": self._create_portfolio_section,
            "converter": self._create_converter_section,
            "widgets": self._create_widgets_section,
            "controls": self._create_controls_section,
            "settings": self._create_settings_section,
            "theme": self._create_theme_section,
        }

        order = list(getattr(self, "section_order", []) or builders.keys())
        enabled_map = dict(getattr(self, "section_enabled", {}) or {})

        for key in order:
            fn = builders.get(key)
            if not fn:
                continue
            if not enabled_map.get(key, True):
                continue
            fn()

        try:
            self._apply_language()
            self._apply_grid_columns()
        except Exception:
            pass

    def _layout_move(self, key: str, direction: int) -> None:
        try:
            order = list(self.section_order)
            i = order.index(key)
            j = i + int(direction)
            if j < 0 or j >= len(order):
                return
            order[i], order[j] = order[j], order[i]
            self.section_order = order
            self._save_layout_preferences()
            self._rebuild_main_sections()
        except Exception:
            pass

    
    def _open_layout_popup(self) -> None:
        try:
            win = ctk.CTkToplevel(self)
        except Exception:
            return
        try:
            win.title("Layout")
            win.geometry("520x520")
            win.resizable(False, False)
            win.transient(self)
            win.grab_set()
        except Exception:
            pass

        try:
            win.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
            apply_dark_titlebar(win, ctk.get_appearance_mode() == "Dark")
            self._apply_theme_to_popup(win)
        except Exception:
            pass

        card = ctk.CTkFrame(win, fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark), corner_radius=18)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        title = ctk.CTkLabel(
            card,
            text=("چیدمان بخش ها" if self.language == "fa" else "Sections Layout"),
            font=self._ui_font(16, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        title.pack(fill="x", padx=18, pady=(16, 10))

        container = ctk.CTkScrollableFrame(card, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        section_labels = {
            "hero": self._t("section_hero") if "section_hero" in TRANSLATIONS.get(self.language, {}) else ("خانه" if self.language == "fa" else "Home"),
            "status": self._t("section_status") if "section_status" in TRANSLATIONS.get(self.language, {}) else ("وضعیت" if self.language == "fa" else "Status"),
            "featured": self._t("section_featured"),
            "insights": self._t("section_insights"),
            "portfolio": self._t("section_portfolio"),
            "converter": self._t("section_converter"),
            "widgets": self._t("section_widgets"),
            "controls": self._t("section_controls"),
            "settings": self._t("section_settings"),
            "theme": self._t("section_theme"),
        }

        vars_map: Dict[str, tk.BooleanVar] = {}
        mandatory_sections = {"hero", "featured", "portfolio"}

        order = list(getattr(self, "section_order", []) or [])
        enabled_map = dict(getattr(self, "section_enabled", {}) or {})

        for key in order:
            line = ctk.CTkFrame(container, fg_color="transparent")
            line.pack(fill="x", pady=4)

            is_mandatory = key in mandatory_sections
            var = tk.BooleanVar(value=True if is_mandatory else bool(enabled_map.get(key, True)))
            vars_map[key] = var

            cb = ctk.CTkCheckBox(
                line,
                text=section_labels.get(key, key) + (f" ({self._t('layout_always_on')})" if is_mandatory else ""),
                variable=var,
                onvalue=True,
                offvalue=False,
                state="disabled" if is_mandatory else "normal",
                command=lambda k=key, v=var: self._layout_set_enabled(k, bool(v.get())),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark) if not is_mandatory else (theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
                fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            )
            cb.pack(side="right" if self.rtl else "left", padx=(0, 8))

            btn_up = self._create_button(line, text="▲", command=lambda k=key: self._layout_move(k, -1), style="secondary", width=44)
            btn_down = self._create_button(line, text="▼", command=lambda k=key: self._layout_move(k, +1), style="secondary", width=44)

            if self.rtl:
                btn_down.pack(side="left", padx=(0, 6))
                btn_up.pack(side="left")
            else:
                btn_up.pack(side="right", padx=(6, 0))
                btn_down.pack(side="right")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 16))

        close_btn = self._create_button(btn_row, text=("بستن" if self.language == "fa" else "Close"), command=lambda: win.destroy(), style="secondary", width=140)
        close_btn.pack(side="left" if self.rtl else "right")

    def _layout_set_enabled(self, key: str, enabled: bool) -> None:
        try:
            if str(key) in {"hero", "featured", "portfolio"}:
                enabled = True
            self.section_enabled[str(key)] = bool(enabled)
            self._save_layout_preferences()
            self._rebuild_main_sections()
        except Exception:
            pass

    def _create_hero_section(self) -> None:
        row = self._next_row()
        hero_card = self._create_glass_card(self.scroll_frame, height=185, glass_level=2)
        hero_card.grid(row=row, column=0, sticky="ew", pady=(0, 20))

        content = ctk.CTkFrame(hero_card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=32, pady=24)

        self.hero_title_label = ctk.CTkLabel(
            content,
            text=self._t("hero_title"),
            font=self._ui_font(40, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.hero_title_label.pack(fill="x")

        self.hero_subtitle_label = ctk.CTkLabel(
            content,
            text=self._t("hero_subtitle"),
            font=self._ui_font(18, False),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.hero_subtitle_label.pack(fill="x", pady=(8, 0))

        self.hero_version_label = ctk.CTkLabel(
            content,
            text=self._t("hero_version", version=config.APP_VERSION),
            font=self._ui_font(14, False),
            text_color=(theme_manager.colors.text_tertiary_light, theme_manager.colors.text_tertiary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.hero_version_label.pack(fill="x", pady=(12, 0))


    def _create_status_section(self) -> None:
        row = self._next_row()
        status_card = self._create_glass_card(self.scroll_frame, height=120, glass_level=2)
        status_card.grid(row=row, column=0, sticky="ew", pady=(0, 20))

        content = ctk.CTkFrame(status_card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=18)

        grid = ctk.CTkFrame(content, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1, 2), weight=1)

        self._create_status_indicator(grid, self._t("api"), "🔗", "api_status", row=0, col=0)
        self._create_status_indicator(grid, self._t("data"), "📊", "data_status", row=0, col=1)
        self._create_status_indicator(grid, self._t("effects"), "✨", "effects_status", row=0, col=2)

    def _create_status_indicator(self, parent, title: str, icon: str, key: str, row: int, col: int) -> None:
        box = ctk.CTkFrame(
            parent,
            fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
            corner_radius=12,
            border_width=1,
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            height=70,
        )
        box.grid(row=row, column=col, padx=8, pady=4, sticky="ew")
        box.pack_propagate(False)

        content = ctk.CTkFrame(box, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=10)

        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x")

        ctk.CTkLabel(header, text=icon, font=self._ui_font(16, False)).pack(side="left")
        ctk.CTkLabel(
            header,
            text=title,
            font=self._ui_font(13, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
        ).pack(side="left", padx=(8, 0))

        status_label = ctk.CTkLabel(
            content,
            text=self._t("status_connecting"),
            font=self._ui_font(12, False),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
        )
        status_label.pack(anchor="w", pady=(6, 0))

        self.ui_elements[key] = {"status_label": status_label}

    def _create_featured_section(self) -> None:
        row = self._next_row(2)
        self.featured_title_label = ctk.CTkLabel(
            self.scroll_frame,
            text=self._t("section_featured"),
            font=self._ui_font(24, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.featured_title_label.grid(row=row, column=0, sticky="e" if self.rtl else "w", pady=(0, 14))

        self.featured_container = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        self.featured_container.grid(row=row + 1, column=0, sticky="ew", pady=(0, 26))
        for i in range(8):
            self.featured_container.grid_columnconfigure(i, weight=1 if i < self.grid_columns else 0)


    def _create_insights_section(self) -> None:
        row = self._next_row()
        card = self._create_glass_card(self.scroll_frame, height=155, glass_level=2)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 20))

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=18)

        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x")

        self.insights_title_label = ctk.CTkLabel(
            header,
            text=self._t("section_insights"),
            font=self._ui_font(18, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.insights_title_label.pack(side="left" if not self.rtl else "right")

        body = ctk.CTkFrame(content, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(10, 0))
        body.grid_columnconfigure((0, 1), weight=1)

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(14, 0))

        self.gainers_title_label = ctk.CTkLabel(
            left,
            text=self._t("top_gainers"),
            font=self._ui_font(13, True),
            text_color=(theme_manager.colors.accent_green, theme_manager.colors.accent_green),
        )
        self.gainers_title_label.pack(anchor="w")

        self.ui_elements["top_gainers"] = [
            ctk.CTkLabel(
                left,
                text="—",
                font=self._ui_font(12, False),
                text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
                anchor="e" if self.rtl else "w",
                justify="right" if self.rtl else "left",
            )
            for _ in range(3)
        ]
        for lbl in self.ui_elements["top_gainers"]:
            lbl.pack(anchor="w", pady=1, fill="x")

        self.losers_title_label = ctk.CTkLabel(
            right,
            text=self._t("top_losers"),
            font=self._ui_font(13, True),
            text_color=(theme_manager.colors.accent_red, theme_manager.colors.accent_red),
        )
        self.losers_title_label.pack(anchor="w")

        self.ui_elements["top_losers"] = [
            ctk.CTkLabel(
                right,
                text="—",
                font=self._ui_font(12, False),
                text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
                anchor="e" if self.rtl else "w",
                justify="right" if self.rtl else "left",
            )
            for _ in range(3)
        ]
        for lbl in self.ui_elements["top_losers"]:
            lbl.pack(anchor="w", pady=1, fill="x")