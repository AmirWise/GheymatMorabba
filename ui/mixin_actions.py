"""MainWindow mixins: portfolio actions, settings actions, and theme switching."""


from __future__ import annotations

import time
import customtkinter as ctk

from typing import Any, Dict, List, Optional
from core.config import ConnectionStatus
from core.utils import logger, IS_WINDOWS, apply_dark_titlebar
from data.db import db_manager
from ui.ui_support import performance_monitor
from ui.widgets import CurrencyCardWidget
from core.theme import theme_manager


# ==========================================================================
# PortfolioActionsMixin
# ==========================================================================

class PortfolioActionsMixin:
    """Portfolio actions. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # Portfolio actions
    # -------------------------------------------------------------------------

    def _remove_currency(self, symbol: str) -> None:
        sym = str(symbol).upper().strip()
        if not sym:
            return
        if sym in self.user_portfolio:
            self.user_portfolio.remove(sym)
            db_manager.save_selected_currencies(self.user_portfolio, mode=self.app_mode)
            self._render_portfolio_cards()
            self._update_currency_selector()
            self.toasts.show(self._t("toast_removed", sym=sym), duration=1800)

    def _sort_portfolio_symbols(self, symbols: List[str]) -> List[str]:
        mode = self._normalize_sort_key(self.portfolio_sort_mode_key)

        def safe_float(x: Any) -> float:
            try:
                return float(x)
            except Exception:
                return float("nan")

        if mode in ("default", "symbol"):
            return sorted(symbols)

        if mode == "name":
            return sorted(symbols, key=lambda s: str(self._currency_display_name(s, self.currencies.get(s, {}))).lower())

        if mode == "price":
            return sorted(symbols, key=lambda s: safe_float(self.currencies.get(s, {}).get("price", 0)), reverse=True)

        if mode == "change":
            return sorted(symbols, key=lambda s: safe_float(self.currencies.get(s, {}).get("change_percent", 0)), reverse=True)

        return sorted(symbols)

    def _on_portfolio_sort_changed(self, selection: Optional[str] = None) -> None:
        display = str(selection or self.portfolio_sort_var.get() or "")
        self.portfolio_sort_mode_key = self._sort_display_to_key(display)
        db_manager.save_preference("portfolio_sort_mode", self.portfolio_sort_mode_key)
        self._render_portfolio_cards()
    def _manual_refresh(self) -> None:
        msg = self._t("status_refreshing")
        self._update_connection_status(ConnectionStatus.CONNECTING, msg)
        self.executor.submit(self._manual_refresh_worker)

    def _manual_refresh_worker(self) -> None:
        try:
            performance_monitor.inc("api_calls")
            currencies = self._fetch_currencies_for_current_mode(force=True)
            if currencies:
                self._enqueue_ui(lambda: self._update_ui_with_data(currencies, ConnectionStatus.CONNECTED, quiet=False))
                return
            self._enqueue_ui(lambda: self._handle_refresh_failed())
        except Exception:
            self._enqueue_ui(lambda: self._handle_refresh_failed())

    def _handle_refresh_failed(self) -> None:
        performance_monitor.inc("errors")
        self._update_connection_status(ConnectionStatus.ERROR)
        self.toasts.show(self._t("toast_refresh_failed"), duration=2600)

    def _test_api_connection(self) -> None:
        self._update_connection_status(ConnectionStatus.CONNECTING, f"🧪 {self._t('api_test_title')}…")
        self.executor.submit(self._api_test_worker)

    def _api_test_worker(self) -> None:
        try:
            start = time.time()
            performance_monitor.inc("api_calls")
            currencies = self._fetch_currencies_for_current_mode(force=True)
            elapsed = time.time() - start
            if currencies:
                msg = self._t("api_test_ok", elapsed=elapsed, count=len(currencies))
                self._enqueue_ui(lambda: self._show_themed_message(self._t("api_test_title"), msg, kind="info"))
                self._enqueue_ui(lambda: self._update_connection_status(ConnectionStatus.CONNECTED))
            else:
                msg = self._t("api_test_fail")
                self._enqueue_ui(lambda: self._show_themed_message(self._t("api_test_title"), msg, kind="error"))
                self._enqueue_ui(lambda: self._update_connection_status(ConnectionStatus.ERROR))
        except Exception as e:
            err_prefix = "خطا" if self.language == "fa" else "Error"
            err_text = str(e)
            self._enqueue_ui(lambda: self._show_themed_message(self._t("api_test_title"), f"{err_prefix}:\n{err_text}", kind="error"))
            self._enqueue_ui(lambda: self._update_connection_status(ConnectionStatus.ERROR))

    def _toggle_auto_refresh(self) -> None:
        self.auto_refresh_active = bool(self.auto_refresh_var.get())
        db_manager.save_preference("auto_refresh", self.auto_refresh_active)
        self.toasts.show(self._t("toast_autorefresh_on") if self.auto_refresh_active else self._t("toast_autorefresh_off"), duration=1800)

    def _export_csv(self) -> None:
        try:
            from tkinter import filedialog
            import csv

            path = filedialog.asksaveasfilename(
                title=self._t("export_title"),
                defaultextension=".csv",
                filetypes=[(self._t("filetype_csv"), "*.csv"), (self._t("filetype_all"), "*.*")],
            )
            if not path:
                return

            symbols = list(dict.fromkeys(self.featured_symbols + sorted(self.user_portfolio)))
            rows = []
            for sym in symbols:
                d = self.currencies.get(sym)
                if not d:
                    continue
                dd = self._display_currency_data(sym, d)
                rows.append({
                    "symbol": sym,
                    "name": dd.get("name", ""),
                    "price": d.get("price", ""),
                    "unit": dd.get("unit", ""),
                    "change_percent": d.get("change_percent", ""),
                    "category": d.get("category", ""),
                    "source": d.get("source", ""),
                    "timestamp": d.get("timestamp", ""),
                })

            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["symbol", "name", "price", "unit", "change_percent"])
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)

            self.toasts.show(self._t("toast_csv_exported"), duration=2400)
        except Exception as e:
            self._show_themed_message(self._t("export_title"), self._t("export_failed", error=e), kind="error")

    def _copy_to_clipboard(self) -> None:
        try:
            symbols = list(dict.fromkeys(self.featured_symbols + sorted(self.user_portfolio)))
            lines = []
            for sym in symbols:
                d = self.currencies.get(sym, {})
                dd = self._display_currency_data(sym, d) if d else {"name": "", "unit": ""}
                lines.append(f"{sym}\t{dd.get('name','')}\t{d.get('price','')}\t{dd.get('unit','')}\t{d.get('change_percent','')}")
            text = "\n".join(lines) if lines else ""
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
            self.toasts.show(self._t("toast_copied"), duration=2000)
        except Exception as e:
            logger.debug(f"Clipboard copy failed: {e}")


# ==========================================================================
# SettingsActionsMixin
# ==========================================================================

class SettingsActionsMixin:
    """Settings actions. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # Settings actions
    # -------------------------------------------------------------------------
    def _on_alerts_toggle(self) -> None:
        self.alerts_enabled = bool(self.alerts_var.get())
        db_manager.save_preference("alerts_enabled", self.alerts_enabled)
        self.toasts.show(self._t("toast_alerts_on") if self.alerts_enabled else self._t("toast_alerts_off"), duration=1800)

    def _on_threshold_changed(self, value: float) -> None:
        try:
            self.alert_threshold_percent = float(value)
            self.alert_threshold_label.configure(text=self._t("threshold", value=float(self.alert_threshold_percent)))
        except Exception:
            return

        # Persist lazily (avoid too many writes)
        self.after(250, lambda: db_manager.save_preference("alert_threshold_percent", float(self.alert_threshold_percent)))


    def _on_background_toggle(self) -> None:
        try:
            if self.background_var is None:
                return
            self.run_in_background = bool(self.background_var.get())
            db_manager.save_preference("run_in_background", bool(self.run_in_background))
            self.toasts.show(self._t("toast_background_on") if self.run_in_background else self._t("toast_background_off"), duration=2200)
        except Exception:
            pass

    def _on_always_on_top_toggle(self) -> None:
        """Toggle window 'always on top' (useful for a price tracker)."""
        try:
            if self.always_on_top_var is None:
                return
            self.always_on_top = bool(self.always_on_top_var.get())
            db_manager.save_preference("always_on_top", bool(self.always_on_top))
            try:
                self.attributes("-topmost", bool(self.always_on_top))
            except Exception:
                pass
            self.toasts.show(
                self._t("toast_topmost_on") if self.always_on_top else self._t("toast_topmost_off"),
                duration=1800,
            )
        except Exception:
            pass


    def _clear_cache(self) -> None:
        try:
            db_manager.prune_cache(keep_last_seconds=0)
            self.toasts.show(self._t("toast_cache_cleared"), duration=2400)
        except Exception as e:
            self._show_themed_message(self._t("clear_cache_title"), str(e), kind="error")

    def _show_performance_report(self) -> None:
        rep = performance_monitor.report()
        if self.language == "fa":
            msg = (
                f"مدت اجرا: {rep['runtime_formatted']}\n\n"
                f"بروزرسانی رابط: {rep['metrics']['ui_updates']}\n"
                f"فراخوانی API: {rep['metrics']['api_calls']}\n"
                f"بارگذاری کش: {rep['metrics']['cache_loads']}\n"
                f"خطاها: {rep['metrics']['errors']}\n"
            )
        else:
            msg = (
                f"Runtime: {rep['runtime_formatted']}\n\n"
                f"UI updates: {rep['metrics']['ui_updates']}\n"
                f"API calls: {rep['metrics']['api_calls']}\n"
                f"Cache loads: {rep['metrics']['cache_loads']}\n"
                f"Errors: {rep['metrics']['errors']}\n"
            )
        self._show_themed_message(self._t("performance_title"), msg, kind="info")

    # Alerts
    # -------------------------------------------------------------------------

    def _maybe_emit_price_alerts(self, old: Dict[str, Dict[str, Any]], new: Dict[str, Dict[str, Any]]) -> None:
        if not self.alerts_enabled:
            return

        now = time.time()
        cooldown = 60.0  # seconds per symbol
        watch = set(self.featured_symbols) | set(self.user_portfolio)

        for sym in watch:
            if sym not in new:
                continue
            try:
                new_price = float(new[sym].get("price", 0) or 0)
            except Exception:
                continue
            if new_price <= 0:
                continue

            old_price = self._last_seen_prices.get(sym)
            if old_price is None or old_price <= 0:
                self._last_seen_prices[sym] = new_price
                continue

            delta = (new_price - old_price) / old_price * 100.0
            if abs(delta) >= self.alert_threshold_percent:
                last_ts = self._last_alert_ts.get(sym, 0.0)
                if now - last_ts >= cooldown:
                    direction = "▲" if delta > 0 else "▼"
                    msg = self._t("toast_price_moved", direction=direction, sym=sym, delta=delta)
                    self.toasts.show(msg, duration=3200)
                    self._last_alert_ts[sym] = now
                    try:
                        stamp = time.strftime("%H:%M:%S")
                        self._recent_alerts.appendleft(f"{stamp}  {direction} {sym}  {delta:+.2f}%  →  {CurrencyCardWidget._format_price(new_price)}")
                    except Exception:
                        pass

            self._last_seen_prices[sym] = new_price


# ==========================================================================
# ThemeMixin
# ==========================================================================

class ThemeMixin:
    """Theme switching. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # Theme
    # -------------------------------------------------------------------------

    def _normalize_theme_key(self, theme_key: str) -> str:
        key = str(theme_key or "").strip().lower()
        mapping = {
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
        return mapping.get(key, "paper_noir")

    def _get_theme_display_name(self, theme_key: str) -> str:
        mapping = {
            "liquid_glass": self._t("theme_name_liquid_glass"),
            "crystal": self._t("theme_name_crystal"),
            "paper": self._t("theme_name_paper"),
            "paper_noir": self._t("theme_name_paper_noir"),
        }
        return mapping.get(theme_key, str(theme_key))

    def _update_theme_button_states(self, active_theme_key: str) -> None:
        active = self._normalize_theme_key(active_theme_key)
        for key, btn in (self.theme_buttons or {}).items():
            try:
                if key == active:
                    btn.configure(
                        fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
                        hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
                        text_color="white",
                        border_width=0,
                    )
                else:
                    btn.configure(
                        fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                        hover_color=(theme_manager.colors.separator_light, theme_manager.colors.separator_dark),
                        text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                        border_width=1,
                        border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
                    )
            except Exception:
                pass

    def _apply_theme_with_feedback(
        self, theme_type: str, show_feedback: bool = True, save_preference: bool = True
    ) -> None:
        theme_key = self._normalize_theme_key(theme_type)
        if theme_key not in {"liquid_glass", "crystal", "paper", "paper_noir"}:
            return

        self.selected_theme = theme_key
        self._update_theme_button_states(theme_key)
        if save_preference:
            db_manager.save_preference("selected_theme", theme_key)

        if show_feedback:
            display_name = self._get_theme_display_name(theme_key)
            self.toasts.show(self._t("toast_applying_theme", name=display_name), duration=1400)

        try:
            # Appearance mode per theme (keeps themes distinct without slowing UI)
            if theme_key == "paper":
                try:
                    ctk.set_appearance_mode("Light")
                except Exception:
                    pass
                self.effects_manager.apply_paper_mode()

            elif theme_key == "paper_noir":
                try:
                    ctk.set_appearance_mode("Dark")
                except Exception:
                    pass
                self.effects_manager.apply_paper_noir_mode()

            else:
                # Default themes follow system appearance
                try:
                    ctk.set_appearance_mode("System")
                except Exception:
                    pass

                if theme_key == "liquid_glass":
                    self.effects_manager.apply_liquid_glass_effect()
                elif theme_key == "crystal":
                    self.effects_manager.apply_crystal_mode()

            try:
                apply_dark_titlebar(self, ctk.get_appearance_mode() == "Dark")
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Theme apply failed: {e}")

        # Ensure root-level and container colors update immediately
        try:
            try:
                self.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
            except Exception:
                pass

            if getattr(self, "main_container", None) is not None:
                try:
                    # main_container intentionally stays transparent but reconfigure if needed
                    self.main_container.configure(fg_color="transparent")
                except Exception:
                    pass

            if getattr(self, "scroll_frame", None) is not None:
                try:
                    self.scroll_frame.configure(
                        scrollbar_button_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
                        scrollbar_button_hover_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
                    )
                except Exception:
                    pass

            # Defensive re-sync for the same reason crypto_toggle_button was
            # given an explicit bg_color tuple in FabMixin._create_fab in the
            # first place: keep it locked to fab_dock's real fg_color rather
            # than ever falling back to an unresolved "transparent" mismatch.
            # fab_dock's own bg_color needs no re-sync on Windows — it's the
            # fixed chroma key, made transparent at the OS level once and for
            # all in _create_fab, not a per-theme flat-color guess.
            if getattr(self, "fab_dock", None) is not None and not IS_WINDOWS:
                try:
                    self.fab_dock.configure(bg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
                except Exception:
                    pass
            if getattr(self, "crypto_toggle_button", None) is not None:
                try:
                    self.crypto_toggle_button.configure(
                        bg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark)
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Theme apply - root reconfigure failed: {e}")

        # No manual rebuild needed here: every widget in the app is colored with
        # (light, dark) tuples, so ctk.set_appearance_mode() above already propagated
        # the new palette to the entire existing widget tree natively. Tearing down
        # and rebuilding the whole dashboard on every theme click was unnecessary and
        # caused visible flicker + state loss (scroll position, open menus, etc).

        # Widgets/menus might need a refresh after appearance change
        try:
            self._symbol_menu_sig = ""
            self._refresh_symbol_menus()
        except Exception:
            pass

        # Update persistent widgets (cards, widgets, toasts) to pick up new typography/colors
        try:
            # Update existing featured/portfolio cards
            try:
                for card in list(self.featured_cards.values()):
                    try:
                        card.set_typography(font_getter=self._ui_font, rtl=self.rtl)
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                for card in list(self.portfolio_cards.values()):
                    try:
                        card.set_typography(font_getter=self._ui_font, rtl=self.rtl)
                    except Exception:
                        pass
            except Exception:
                pass

            # Desktop widgets may be separate windows; refresh their typography/styles
            try:
                if getattr(self, "widget_manager", None) is not None:
                    try:
                        self.widget_manager.apply_typography()
                    except Exception:
                        pass
            except Exception:
                pass

            # Toast manager typography
            try:
                try:
                    self.toasts.set_typography(font_getter=self._ui_font, rtl=self.rtl)
                except Exception:
                    pass
            except Exception:
                pass

            try:
                self.update_idletasks()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Post-theme refresh failed: {e}")

        try:
            self._refresh_fab_texts()
        except Exception:
            pass

# =============================================================================
# Diagnostics / main
# =============================================================================
