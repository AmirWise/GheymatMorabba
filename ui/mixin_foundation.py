"""MainWindow mixins: window/resource setup, startup + refresh loop, localization, preferences."""


from __future__ import annotations

import customtkinter as ctk
import socket
import threading
import queue
import time
import json

from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from core.config import config, ConnectionStatus
from core.utils import IS_WINDOWS, resource_manager, logger
from core.theme import theme_manager
from ui.desktop_widgets import WinTrayIcon
from data.db import db_manager
from ui.ui_support import performance_monitor
from core.i18n import is_rtl, tr


# ==========================================================================
# WindowMixin
# ==========================================================================

class WindowMixin:
    """Window/resource setup. Composed onto MainWindow in app.py."""


    # -------------------------------------------------------------------------
    # Window / resources
    # -------------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.title(f"{config.APP_NAME} v{config.APP_VERSION}")

        self._apply_display_scaling()
        win_w, win_h = self._compute_responsive_window_size()
        self._target_window_w, self._target_window_h = win_w, win_h
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(config.MIN_WIDTH, config.MIN_HEIGHT)
        self.resizable(True, True)

        # Theme baseline
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))

        # Icon
        icon_path = resource_manager.load_icon("assets/icons/icon.ico")
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        try:
            self.protocol("WM_DELETE_WINDOW", self._on_close_requested)
            self.bind("<Unmap>", self._on_window_unmap)
            self.bind("<Map>", self._on_window_map)
            self._tray_icon = None
            if IS_WINDOWS:
                self._ensure_tray()
        except Exception:
            pass

        self.after(50, self._center_window)

    def _apply_display_scaling(self) -> None:
        """Scale fonts/widget sizes to the monitor's actual pixel density.
        A 4K/HiDPI display and a small low-res laptop panel both report the
        same logical pixel sizes to Tk by default, which is why fonts looked
        the same (often too small or too large) regardless of the screen."""
        self._ui_scale = 1.0
        try:
            raw_dpi = self.winfo_fpixels("1i")
            if raw_dpi and raw_dpi > 0:
                scale = raw_dpi / 96.0
                scale = max(0.85, min(1.6, scale))
                ctk.set_widget_scaling(scale)
                self._ui_scale = scale
        except Exception:
            pass

    def _compute_responsive_window_size(self) -> Tuple[int, int]:
        """Size the window as a proportion of the actual screen, instead of a
        fixed 1200x900 that could dwarf a small laptop screen or look tiny
        on a large monitor."""
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w = int(sw * 0.72)
            h = int(sh * 0.82)
            w = max(config.MIN_WIDTH, min(1680, w))
            h = max(config.MIN_HEIGHT, min(1150, h))
            # Never exceed the usable screen area
            w = min(w, sw - 40)
            h = min(h, sh - 60)
            return w, h
        except Exception:
            return config.WINDOW_WIDTH, config.WINDOW_HEIGHT

    def _center_window(self) -> None:
        try:
            self.update_idletasks()
            w = int(getattr(self, "_target_window_w", 0) or self.winfo_width())
            h = int(getattr(self, "_target_window_h", 0) or self.winfo_height())
            x = (self.winfo_screenwidth() // 2) - (w // 2)
            y = (self.winfo_screenheight() // 2) - (h // 2)
            self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def start_single_instance_listener(self, lock_socket: socket.socket) -> None:
        """Watch the single-instance lock socket for a wake-up signal sent by
        a second launch of the app, and restore/focus this window when one
        arrives. Runs on a daemon thread; all UI work is dispatched back to
        the Tk thread via the existing UI task queue."""
        self._single_instance_socket = lock_socket
        self._single_instance_running = True

        def _listen() -> None:
            while self._single_instance_running:
                try:
                    conn, _addr = lock_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                except Exception:
                    continue
                try:
                    conn.settimeout(1.0)
                    conn.recv(64)
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
                self._enqueue_ui(self._restore_and_focus)

        self._single_instance_thread = threading.Thread(
            target=_listen, name="SingleInstanceListener", daemon=True
        )
        self._single_instance_thread.start()

    def _stop_single_instance_listener(self) -> None:
        self._single_instance_running = False

    def _restore_and_focus(self) -> None:
        """Bring the already-running window to the foreground, whether it's
        currently minimized, hidden in the tray, or just behind other windows."""
        try:
            if getattr(self, "_tray_icon", None) is not None and getattr(self._tray_icon, "_icon_added", False):
                self._show_from_tray()
                return
        except Exception:
            pass
        try:
            if str(self.state()) == "iconic":
                self.deiconify()
        except Exception:
            pass
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _ensure_tray(self) -> None:
        if not IS_WINDOWS:
            return
        try:
            if getattr(self, "_tray_icon", None) is None:
                self._tray_icon = WinTrayIcon(self)
                self._tray_icon.start()
        except Exception:
            pass

    def _hide_to_tray(self) -> None:
        self._set_fab_visible(False)
        if not IS_WINDOWS:
            try:
                self.iconify()
            except Exception:
                pass
            return
        self._ensure_tray()
        try:
            if getattr(self, "_tray_icon", None) is not None:
                self._tray_icon.show_icon()
                try:
                    self.after(200, self._tray_icon.show_icon)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.withdraw()
        except Exception:
            pass

    def _show_from_tray(self) -> None:
        try:
            self.deiconify()
        except Exception:
            pass
        self._set_fab_visible(True)
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass
        try:
            if getattr(self, "_tray_icon", None) is not None:
                self._tray_icon.hide_icon()
        except Exception:
            pass

    def _exit_from_tray(self) -> None:
        try:
            self._stop_single_instance_listener()
        except Exception:
            pass
        try:
            if getattr(self, "_tray_icon", None) is not None:
                self._tray_icon.hide_icon()
        except Exception:
            pass
        try:
            self.widget_manager.shutdown()
        except Exception:
            pass
        try:
            if self.fab_window is not None:
                self.fab_window.destroy()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _on_window_unmap(self, event: Any = None) -> None:
        # Minimizing the window (taskbar minimize button) always behaves like
        # a normal OS minimize now — it never auto-drops to the tray. Tray
        # mode is only entered deliberately, via the close button when
        # "run in background" is on (see _on_close_requested).
        try:
            if str(self.state()) == "iconic":
                self._set_fab_visible(False)
        except Exception:
            pass

    def _on_window_map(self, event: Any = None) -> None:
        try:
            if str(self.state()) != "iconic":
                self._set_fab_visible(True)
        except Exception:
            pass


    def _on_close_requested(self) -> None:
        """Close button behavior: either exit, or keep running (tray) for background updates + widgets."""
        try:
            if self._fab_menu_open:
                self._fab_close_menu()
        except Exception:
            pass

        if self.run_in_background:
            try:
                if IS_WINDOWS:
                    self._hide_to_tray()
                else:
                    self.iconify()
                self.toasts.show(self._t("toast_background_on"), duration=2200)
            except Exception:
                pass
            return

        try:
            try:
                self._stop_single_instance_listener()
            except Exception:
                pass
            try:
                if getattr(self, "_tray_icon", None) is not None:
                    self._tray_icon.hide_icon()
            except Exception:
                pass
            try:
                self.widget_manager.shutdown()
            except Exception:
                pass

            # Stop background loops deterministically instead of letting them
            # fail silently against a destroyed window.
            try:
                self._ui_queue_running = False
            except Exception:
                pass
            try:
                if self._auto_refresh_after_id:
                    self.after_cancel(self._auto_refresh_after_id)
                    self._auto_refresh_after_id = None
            except Exception:
                pass
            try:
                if self._resize_after_id:
                    self.after_cancel(self._resize_after_id)
                    self._resize_after_id = None
            except Exception:
                pass
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                # cancel_futures not available on very old Python versions
                try:
                    self.executor.shutdown(wait=False)
                except Exception:
                    pass
            except Exception:
                pass

            try:
                if self.fab_window is not None:
                    self.fab_window.destroy()
            except Exception:
                pass

            self.destroy()
        except Exception:
            pass

    def _load_resources(self) -> None:
        for fp in (
            "assets/fonts/Vazirmatn-Regular.ttf",
            "assets/fonts/SF-Pro-Display-Regular.ttf",
            "assets/fonts/Inter-Regular.ttf",
        ):
            resource_manager.load_font(fp)


# ==========================================================================
# StartupMixin
# ==========================================================================

class StartupMixin:
    """Startup helpers (first paint, refresh loop). Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # Startup helpers (missing in earlier builds)
    # -------------------------------------------------------------------------

    def _bind_shortcuts(self) -> None:
        """Keyboard shortcuts (safe to call even if some widgets aren't ready)."""
        try:
            self.bind("<Control-r>", lambda _e: self._manual_refresh())
            self.bind("<F5>", lambda _e: self._manual_refresh())
        except Exception:
            pass

        # Quick focus helpers
        try:
            self.bind("<Control-f>", lambda _e: self._focus_portfolio_filter())
        except Exception:
            pass

        # Exit / hide
        try:
            self.bind("<Control-q>", lambda _e: self._on_close_requested())
            self.bind("<Escape>", lambda _e: self._maybe_close_transient())
        except Exception:
            pass

    def _focus_portfolio_filter(self) -> None:
        try:
            if self.portfolio_filter_entry is not None:
                if not self._portfolio_search_visible:
                    self._toggle_portfolio_search()
                self.portfolio_filter_entry.focus_set()
                self.portfolio_filter_entry.select_range(0, "end")
        except Exception:
            pass

    def _maybe_close_transient(self) -> None:
        """Close transient dialogs/popups if any; otherwise do nothing."""
        # Keep intentionally conservative; the main window should not close on Escape.
        try:
            if hasattr(self, "toasts"):
                self.toasts.clear_all()
        except Exception:
            pass

    def _refresh_featured_symbols(self) -> None:
        """Pick a stable set of featured symbols (top row)."""
        if self.app_mode == "crypto":
            priority = [
                "BTC", "ETH", "USDT", "BNB", "USDC", "XRP",
                "SOL", "ADA", "DOGE", "DOT", "AVAX", "TRX",
            ]
        else:
            priority = [
                "USD", "EUR", "GBP", "AED", "TRY",
                "BTC", "ETH", "USDT_IRT",
                "IR_GOLD_18K", "IR_COIN_EMAMI", "XAUUSD",
            ]

        out: List[str] = []
        seen: Set[str] = set()

        for sym in priority:
            s = str(sym).upper().strip()
            if s in self.currencies and s not in seen:
                out.append(s)
                seen.add(s)

        # Fill remaining slots with whatever is available (deterministic)
        try:
            for sym in sorted(self.currencies.keys()):
                s = str(sym).upper().strip()
                if s and s not in seen:
                    out.append(s)
                    seen.add(s)
                if len(out) >= 12:
                    break
        except Exception:
            pass

        self.featured_symbols = out

    def _load_cached_first_paint(self) -> None:
        """Use DB cache to render something instantly on startup."""
        try:
            cached = db_manager.load_cached_currencies(max_age_seconds=6 * 3600)
        except Exception:
            cached = {}

        if not cached:
            return

        try:
            performance_monitor.inc("cache_loads")
        except Exception:
            pass

        self.currencies = dict(cached)

        # Populate featured + refresh UI
        self._refresh_featured_symbols()
        self._render_featured_cards()
        self._render_portfolio_cards()
        self._update_currency_selector()
        self._refresh_symbol_menus()
        self._update_insights()

        self._update_connection_status(ConnectionStatus.CACHED)
        self._update_status_displays()

        # Update desktop widgets
        try:
            self.widget_manager.update_all(self.currencies)
        except Exception:
            pass

        # Alerts should compare live updates only, not cache load
        try:
            self._last_seen_prices.clear()
            for sym, d in self.currencies.items():
                try:
                    self._last_seen_prices[str(sym).upper().strip()] = float(d.get("price", 0) or 0)
                except Exception:
                    continue
        except Exception:
            pass

    def _enqueue_ui(self, fn: Callable[[], None]) -> None:
        """Enqueue a callable to run on the Tk/UI thread.
        This avoids calling Tk methods from worker threads.
        """
        try:
            q = getattr(self, "_ui_task_queue", None)
            if q is not None:
                q.put(fn)
        except Exception:
            pass

    def _drain_ui_task_queue(self) -> None:
        """Run queued UI tasks on the main thread."""
        processed = False
        try:
            if not getattr(self, "_ui_queue_running", True):
                return
            q = getattr(self, "_ui_task_queue", None)
            if q is not None:
                while True:
                    try:
                        fn = q.get_nowait()
                    except queue.Empty:
                        break
                    processed = True
                    try:
                        fn()
                    except Exception:
                        try:
                            logger.exception("UI task failed")
                        except Exception:
                            pass
        finally:
            try:
                # Poll quickly right after activity, back off while idle.
                self.after(30 if processed else 150, self._drain_ui_task_queue)
            except Exception:
                pass

    def _start_data_systems(self) -> None:
        """Kick off networking and periodic refresh."""
        # First live refresh
        self._update_connection_status(ConnectionStatus.CONNECTING)
        try:
            self.executor.submit(self._initial_refresh_worker)
        except Exception:
            # Fallback: try sync (should still be safe)
            self._enqueue_ui(self._manual_refresh)

        # Auto refresh scheduler
        self._schedule_auto_refresh()

        # Small periodic tasks (history UI smoothness)
        try:
            self.after(20_000, self._periodic_light_tasks)
        except Exception:
            pass

    def _periodic_light_tasks(self) -> None:
        try:
            self._history_live_append()
        except Exception:
            pass
        try:
            self._update_converter_result()
        except Exception:
            pass

        # Re-arm
        try:
            self.after(20_000, self._periodic_light_tasks)
        except Exception:
            pass

    def _fetch_currencies_for_current_mode(self, force: bool) -> Optional[Dict[str, Dict[str, Any]]]:
        """Route to the correct API source set for the active mode. Crypto mode
        uses only the dedicated cryptocurrency feed; normal mode uses only the
        primary/commodity/Tetherland merge. The two never call each other's
        endpoints, so a failure or slowdown in one mode's APIs can't affect
        the other."""
        if self.app_mode == "crypto":
            result = self.api_manager.fetch_crypto_currencies_sync(force=force)
            try:
                rate = self.api_manager.fetch_tether_irr_rate_sync()
                if rate:
                    self._tether_irr_rate = rate
            except Exception:
                pass
            return result
        return self.api_manager.fetch_all_currencies_sync(force=force)

    def _initial_refresh_worker(self) -> None:
        try:
            performance_monitor.inc("api_calls")
            currencies = self._fetch_currencies_for_current_mode(force=True)
            if currencies:
                self._enqueue_ui(lambda: self._update_ui_with_data(currencies, ConnectionStatus.CONNECTED, quiet=True))
                return

            # Backup endpoints are normal-mode only (CoinGecko, exchange-rate
            # fallbacks, etc.) — crypto mode has its own single dedicated feed
            # and must never fall through to these.
            if self.app_mode != "crypto":
                data2 = self.api_manager.fetch_data_sync(force=True, skip_primary=True)
                if data2:
                    currencies2 = self.api_manager.process_currency_data(data2)
                    if currencies2:
                        self._enqueue_ui(lambda: self._update_ui_with_data(currencies2, ConnectionStatus.CONNECTED, quiet=True))
                        return

            self._enqueue_ui(lambda: self._update_connection_status(ConnectionStatus.ERROR))
        except Exception as e:
            try:
                logger.warning(f"Initial refresh failed: {e}")
            except Exception:
                pass
            self._enqueue_ui(lambda: self._update_connection_status(ConnectionStatus.ERROR))

    def _schedule_auto_refresh(self) -> None:
        """(Re)Schedule auto refresh based on current settings."""
        # Cancel previous
        try:
            if self._auto_refresh_after_id:
                try:
                    self.after_cancel(self._auto_refresh_after_id)
                except Exception:
                    pass
                self._auto_refresh_after_id = None
        except Exception:
            pass

        if not self.auto_refresh_active:
            return

        try:
            interval_ms = int(max(config.MIN_REFRESH_INTERVAL, min(config.MAX_REFRESH_INTERVAL, int(self.refresh_interval_seconds)))) * 1000
        except Exception:
            interval_ms = int(config.DEFAULT_REFRESH_INTERVAL) * 1000

        try:
            self._auto_refresh_after_id = self.after(interval_ms, self._auto_refresh_tick)
        except Exception:
            self._auto_refresh_after_id = None

    def _auto_refresh_tick(self) -> None:
        # Re-arm first (so failures don't stop the loop)
        self._schedule_auto_refresh()

        # Don't stack refreshes
        if getattr(self, "_refresh_inflight", False):
            return

        self._refresh_inflight = True
        try:
            self.executor.submit(self._auto_refresh_worker)
        except Exception:
            self._refresh_inflight = False

    def _auto_refresh_worker(self) -> None:
        try:
            performance_monitor.inc("api_calls")
            currencies = self._fetch_currencies_for_current_mode(force=False)
            if currencies:
                self._enqueue_ui(lambda: self._update_ui_with_data(currencies, ConnectionStatus.CONNECTED, quiet=True))
                return
            self._enqueue_ui(lambda: self._update_connection_status(ConnectionStatus.ERROR))
        except Exception:
            self._enqueue_ui(lambda: self._update_connection_status(ConnectionStatus.ERROR))
        finally:
            self._refresh_inflight = False

    def _update_ui_with_data(self, currencies: Dict[str, Dict[str, Any]], status: ConnectionStatus, *, quiet: bool = True) -> None:
        """Apply fresh currency data to the app state + UI."""
        performance_monitor.inc("ui_updates")

        old = dict(self.currencies)
        self.currencies = dict(currencies or {})

        # Update featured selections first (affects portfolio view)
        self._refresh_featured_symbols()

        # UI updates
        self._render_featured_cards()
        self._render_portfolio_cards()
        self._update_currency_selector()
        self._refresh_symbol_menus()
        self._update_insights()

        # Status text
        try:
            self.last_update = time.strftime("%H:%M:%S")
        except Exception:
            self.last_update = "—"

        self._update_connection_status(status)
        self._update_status_displays()

        # Alerts (compare to previous snapshot)
        try:
            self._maybe_emit_price_alerts(old, self.currencies)
        except Exception:
            pass

        # Desktop widgets
        try:
            self.widget_manager.update_all(self.currencies)
        except Exception:
            pass

        # Cache write (async)
        try:
            self.executor.submit(db_manager.cache_bulk_currency_data, dict(self.currencies))
        except Exception:
            pass

        # Session tracker (no chart)
        try:
            self._update_session_tracker()
        except Exception:
            pass

        if not quiet:
            try:
                self.toasts.show(self._t("toast_updated"), duration=1800)
            except Exception:
                pass


# ==========================================================================
# LocalizationMixin
# ==========================================================================

class LocalizationMixin:
    """Language/typography/responsive layout. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # Language / typography / responsive layout
    # -------------------------------------------------------------------------

    def _t(self, key: str, **kwargs) -> str:
        return tr(self.language, key, **kwargs)

    @staticmethod
    def _normalize_language(value: str) -> str:
        v = str(value or "").strip().lower()
        if v.startswith("fa") or v in {"فارسی", "persian", "farsi"}:
            return "fa"
        return "en"
    def _language_display(self, lang_key: str) -> str:
        """Return the display label for a language code, in the CURRENT UI language."""
        key = self._normalize_language(lang_key)
        if self.language == "fa":
            mapping = {"fa": "فارسی", "en": "انگلیسی"}
        else:
            mapping = {"fa": "Persian", "en": "English"}
        return mapping.get(key, "English")

    def _language_menu_values(self) -> List[str]:
        return [self._language_display("fa"), self._language_display("en")]

    def _display_to_language(self, display: str) -> str:
        d = str(display or "").strip().lower()
        # Accept both Persian and English labels (and tolerate minor variations)
        if d in {"fa", "فارسی", "farsi", "persian"}:
            return "fa"
        if d in {"en", "english", "انگلیسی"}:
            return "en"
        if d.startswith("fa") or "فارسی" in d:
            return "fa"
        if d.startswith("en") or "english" in d or "انگلیسی" in d:
            return "en"
        return "en"

    def _font_family(self) -> str:
        if self.language == "fa":
            return config.PERSIAN_FONT or config.FALLBACK_FONT
        # English
        return config.PRIMARY_FONT or config.FALLBACK_FONT

    def _ui_font(self, size: int, bold: bool = False) -> Tuple[Any, ...]:
        family = self._font_family()
        if bold:
            return (family, int(size), "bold")
        return (family, int(size))

    def _widget_palette(self) -> Dict[str, str]:
        """Colors for desktop widgets, taken from the app's own theme
        palette. "auto" tracks whichever of the 4 app themes is active."""
        key = str(getattr(self, "widget_theme", "auto") or "auto").strip().lower()
        key = self._normalize_theme_key(self.selected_theme) if key == "auto" else self._normalize_theme_key(key)

        if key == "paper":
            dark = False
        elif key == "paper_noir":
            dark = True
        else:
            try:
                dark = "dark" in str(ctk.get_appearance_mode() or "").lower()
            except Exception:
                dark = True

        c = theme_manager.colors
        if dark:
            return {
                "bg": c.bg_dark,
                "fill": c.glass_overlay_dark,
                "border": c.border_dark,
                "txt": c.text_primary_dark,
                "sub": c.text_secondary_dark,
                "dot": c.separator_dark,
                "shine": c.accent_blue,
                "up": c.accent_green,
                "down": c.accent_red,
            }
        return {
            "bg": c.bg_light,
            "fill": c.glass_overlay_light,
            "border": c.border_light,
            "txt": c.text_primary_light,
            "sub": c.text_secondary_light,
            "dot": c.separator_light,
            "shine": "#ffffff",
            "up": c.accent_green,
            "down": c.accent_red,
        }


    # ----- currency localization -----

    _CURRENCY_NAME_MAP: Dict[str, Dict[str, str]] = {
        "USD": {"fa": "دلار آمریکا", "en": "US Dollar"},
        "EUR": {"fa": "یورو", "en": "Euro"},
        "GBP": {"fa": "پوند انگلیس", "en": "British Pound"},
        "AED": {"fa": "درهم امارات", "en": "UAE Dirham"},
        "TRY": {"fa": "لیر ترکیه", "en": "Turkish Lira"},
        "CNY": {"fa": "یوان چین", "en": "Chinese Yuan"},
        "JPY": {"fa": "ین ژاپن", "en": "Japanese Yen"},
        "RUB": {"fa": "روبل روسیه", "en": "Russian Ruble"},
        "CAD": {"fa": "دلار کانادا", "en": "Canadian Dollar"},
        "AUD": {"fa": "دلار استرالیا", "en": "Australian Dollar"},
        "CHF": {"fa": "فرانک سوئیس", "en": "Swiss Franc"},
        "USDT": {"fa": "تتر", "en": "Tether"},
        "BTC": {"fa": "بیت‌کوین", "en": "Bitcoin"},
        "ETH": {"fa": "اتریوم", "en": "Ethereum"},
        "BNB": {"fa": "بایننس‌کوین", "en": "BNB"},
        "SOL": {"fa": "سولانا", "en": "Solana"},
        "DOGE": {"fa": "دوج‌کوین", "en": "Dogecoin"},
        "ADA": {"fa": "کاردانو", "en": "Cardano"},
        "DOT": {"fa": "پولکادات", "en": "Polkadot"},
        "AVAX": {"fa": "آوالانچ", "en": "Avalanche"},
        "MATIC": {"fa": "پالیگان", "en": "Polygon"},
        "TRX": {"fa": "ترون", "en": "TRON"},
        "LTC": {"fa": "لایت‌کوین", "en": "Litecoin"},
        "XRP": {"fa": "ریپل", "en": "XRP"},
        "TON": {"fa": "تون", "en": "Toncoin"},
        # Commodity API (metals / energy) — no name_en in the raw feed
        "XAUUSD": {"fa": "انس طلا", "en": "Gold Ounce"},
        "XAGUSD": {"fa": "انس نقره", "en": "Silver Ounce"},
        "XPTUSD": {"fa": "انس پلاتین", "en": "Platinum Ounce"},
        "XPDUSD": {"fa": "انس پالادیوم", "en": "Palladium Ounce"},
        "CU": {"fa": "مس", "en": "Copper"},
        "AL": {"fa": "آلومینیوم", "en": "Aluminum"},
        "ZN": {"fa": "روی", "en": "Zinc"},
        "PB": {"fa": "سرب", "en": "Lead"},
        "NI": {"fa": "نیکل", "en": "Nickel"},
        "BRENT": {"fa": "نفت برنت", "en": "Brent Crude Oil"},
        "WTI": {"fa": "نفت سبک", "en": "WTI Crude Oil"},
        "GAS": {"fa": "گاز طبیعی", "en": "Natural Gas"},
        "RBOB": {"fa": "بنزین", "en": "Gasoline (RBOB)"},
        "GASOIL": {"fa": "گازوییل", "en": "Gasoil"},
    }

    _UNIT_MAP_EN: Dict[str, str] = {
        "تومان": "Toman",
        "ریال": "Rial",
        "دلار": "Dollar",
        "یورو": "Euro",
        "پوند": "Pound",
        "درهم": "Dirham",
        "لیر": "Lira",
    }

    _UNIT_MAP_FA: Dict[str, str] = {
        "toman": "تومان",
        "rial": "ریال",
        "dollar": "دلار",
        "euro": "یورو",
        "pound": "پوند",
        "dirham": "درهم",
        "lira": "لیر",
    }

    @staticmethod
    def _has_persian_letters(text: str) -> bool:
        s = str(text or "")
        ranges = [
            ("؀", "ۿ"),
            ("ݐ", "ݿ"),
            ("ࢠ", "ࣿ"),
            ("ﭐ", "﷿"),
            ("ﹰ", "﻿"),
        ]
        for ch in s:
            for a, b in ranges:
                if a <= ch <= b:
                    return True
        return False

    @staticmethod
    def _has_latin_letters(text: str) -> bool:
        s = str(text or "")
        return any(("A" <= ch <= "Z") or ("a" <= ch <= "z") for ch in s)

    def _currency_display_name(self, sym: str, data: Optional[Dict[str, Any]] = None) -> str:
        symbol = str(sym or "").upper().strip()
        data = data or {}
        mapping = self._CURRENCY_NAME_MAP.get(symbol, {})

        if self.language == "fa":
            for k in ("name_fa", "name_farsi", "fa_name"):
                v = data.get(k)
                if v and self._has_persian_letters(str(v)):
                    return str(v).strip()
            if mapping.get("fa"):
                return mapping["fa"]

            v = str(data.get("name", "") or "").strip()
            if v and self._has_persian_letters(v) and not self._has_latin_letters(v):
                return v
            return symbol

        # English
        for k in ("name_en", "name_english", "en_name"):
            v = data.get(k)
            if v and not self._has_persian_letters(str(v)):
                return str(v).strip()
        if mapping.get("en"):
            return mapping["en"]

        v = str(data.get("name", "") or "").strip()
        if v and not self._has_persian_letters(v):
            return v
        return symbol

    def _unit_display(self, unit: Any) -> str:
        u = str(unit or "").strip()
        if not u:
            return ""

        if self.language == "fa":
            if self._has_persian_letters(u):
                return u
            key = u.strip().lower()
            return self._UNIT_MAP_FA.get(key, u)

        # English
        if self._has_persian_letters(u):
            return self._UNIT_MAP_EN.get(u, u)
        return u

    def _display_currency_data(self, sym: str, data: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(data or {})
        d["symbol"] = str(sym or "").upper().strip()
        d["name"] = self._currency_display_name(sym, d)

        if self.app_mode == "crypto" and d.get("category") == "crypto" and self.crypto_price_basis == "usdt":
            try:
                toman_price = float(d.get("price", 0) or 0)
                rate = self._tether_irr_rate
                if rate and rate > 0 and toman_price > 0:
                    d["price"] = str(toman_price / rate)
                    d["unit"] = "دلار" if self.language == "fa" else "USD"
                else:
                    # No rate available yet — fall back to the API's own USD
                    # price rather than showing nothing.
                    usd_price = d.get("price_usd")
                    if usd_price:
                        d["price"] = str(usd_price)
                        d["unit"] = "دلار" if self.language == "fa" else "USD"
            except Exception:
                pass

        elif self.app_mode == "normal" and getattr(self, "normal_price_basis", "irr") == "usd":
            # Toman/Rial items -> USD equivalent via the USD record's own rate.
            # Items already in a foreign currency (e.g. XAUUSD) stay as-is.
            try:
                unit_raw = str(d.get("unit", "")).lower()
                is_toman = "تومان" in unit_raw or "toman" in unit_raw
                is_rial = "ریال" in unit_raw or "rial" in unit_raw
                if is_toman or is_rial:
                    toman_price = float(d.get("price", 0) or 0)
                    if is_rial and not is_toman:
                        toman_price = toman_price / 10.0
                    rate = self._usd_toman_rate()
                    if rate and rate > 0 and toman_price > 0:
                        d["price"] = str(toman_price / rate)
                        d["unit"] = "دلار" if self.language == "fa" else "USD"
            except Exception:
                pass

        d["unit"] = self._unit_display(d.get("unit", ""))
        return d

# ----- sort helpers -----

    @staticmethod
    def _normalize_sort_key(value: str) -> str:
        v = str(value or "").strip().lower()
        mapping = {
            # English (legacy)
            "default": "default",
            "name": "name",
            "symbol": "symbol",
            "price": "price",
            "change": "change",
            # Capitalized legacy values
            "Default".lower(): "default",
            "Name".lower(): "name",
            "Symbol".lower(): "symbol",
            "Price".lower(): "price",
            "Change".lower(): "change",
            # Persian display (if saved accidentally)
            "پیش‌فرض": "default",
            "پیش فرض": "default",
            "نام": "name",
            "نماد": "symbol",
            "قیمت": "price",
            "تغییر": "change",
        }
        return mapping.get(v, "default")

    def _sort_key_to_display(self, key: str) -> str:
        k = self._normalize_sort_key(key)
        tr_key = {
            "default": "sort_default",
            "name": "sort_name",
            "symbol": "sort_symbol",
            "price": "sort_price",
            "change": "sort_change",
        }.get(k, "sort_default")
        return self._t(tr_key)

    def _sort_display_to_key(self, display: str) -> str:
        d = str(display or "").strip()
        for k in ("default", "name", "symbol", "price", "change"):
            if d == self._sort_key_to_display(k):
                return k
        return self._normalize_sort_key(d)

    def _get_sort_display_values(self) -> List[str]:
        return [self._sort_key_to_display(k) for k in ("default", "name", "symbol", "price", "change")]

    # ----- language apply -----

    def _apply_language(self) -> None:
        self.language = self._normalize_language(self.language)
        self.rtl = is_rtl(self.language)

        # Update toast typography
        try:
            self.toasts.set_typography(font_getter=self._ui_font, rtl=self.rtl)
        except Exception:
            pass

        # Window title
        try:
            self.title(f"{self._t('toolbar_title')} v{config.APP_VERSION}")
        except Exception:
            pass

        # Toolbar title
        try:
            if self.toolbar_title_label is not None:
                self.toolbar_title_label.configure(
                    text=self._t("toolbar_title"),
                    font=self._ui_font(16, True),
                    anchor="e" if self.rtl else "w",
                )
        except Exception:
            pass

        # Status indicator titles
        try:
            if "api_status" in self.ui_elements:
                self.ui_elements["api_status"]["title_label"].configure(
                    text=self._t("api"),
                    font=self._ui_font(12, True),
                    anchor="e" if self.rtl else "w",
                    justify="right" if self.rtl else "left",
                )
            if "data_status" in self.ui_elements:
                self.ui_elements["data_status"]["title_label"].configure(
                    text=self._t("data"),
                    font=self._ui_font(12, True),
                    anchor="e" if self.rtl else "w",
                    justify="right" if self.rtl else "left",
                )
            if "effects_status" in self.ui_elements:
                self.ui_elements["effects_status"]["title_label"].configure(
                    text=self._t("effects"),
                    font=self._ui_font(12, True),
                    anchor="e" if self.rtl else "w",
                    justify="right" if self.rtl else "left",
                )
        except Exception:
            pass

        # Hero
        try:
            if self.hero_title_label is not None:
                self.hero_title_label.configure(text=self._t("hero_title"), font=self._ui_font(40, True), anchor="e" if self.rtl else "w")
            if self.hero_subtitle_label is not None:
                self.hero_subtitle_label.configure(text=self._t("hero_subtitle"), font=self._ui_font(18, False), anchor="e" if self.rtl else "w")
            if self.hero_version_label is not None:
                ver = str(config.APP_VERSION)
                if self.language == "fa":
                    ver = ver.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
                else:
                    ver = ver.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
                self.hero_version_label.configure(text=self._t("hero_version", version=ver), font=self._ui_font(14, False), anchor="e" if self.rtl else "w")
        except Exception:
            pass

        # Section titles
        for attr, key, size in (
            ("featured_title_label", "section_featured", 24),
            ("insights_title_label", "section_insights", 18),
            ("portfolio_title_label", "section_portfolio", 24),
            ("history_title_label", "section_history", 18),
            ("converter_title_label", "section_converter", 18),
            ("widgets_title_label", "section_widgets", 18),
            ("controls_title_label", "section_controls", 18),
            ("settings_title_label", "section_settings", 18),
            ("theme_title_label", "section_theme", 18),
        ):
            try:
                w = getattr(self, attr, None)
                if w is not None:
                    w.configure(
                        text=self._t(key),
                        font=self._ui_font(size, True),
                        anchor="e" if self.rtl else "w",
                        justify="right" if self.rtl else "left",
                    )
            except Exception:
                continue

        # Insights titles
        try:
            if self.gainers_title_label is not None:
                self.gainers_title_label.configure(text=self._t("top_gainers"), font=self._ui_font(13, True))
            if self.losers_title_label is not None:
                self.losers_title_label.configure(text=self._t("top_losers"), font=self._ui_font(13, True))
        except Exception:
            pass

        # Buttons / checkboxes / misc labels
        try:
            if hasattr(self, "refresh_btn"):
                self.refresh_btn.configure(text=self._t("btn_refresh"), font=self._ui_font(13, False))
            if hasattr(self, "test_btn"):
                self.test_btn.configure(text=self._t("btn_test_api"), font=self._ui_font(13, False))
            if hasattr(self, "export_btn"):
                self.export_btn.configure(text=self._t("btn_export_csv"), font=self._ui_font(13, False))
            if hasattr(self, "copy_btn"):
                self.copy_btn.configure(text=self._t("btn_copy"), font=self._ui_font(13, False))
        except Exception:
            pass

        try:
            if hasattr(self, "auto_refresh_checkbox"):
                self.auto_refresh_checkbox.configure(text=self._t("auto_refresh"), font=self._ui_font(13, False))
        except Exception:
            pass

        # Settings controls
        try:
            if hasattr(self, "language_menu") and hasattr(self, "language_var"):
                try:
                    self.language_menu.configure(dropdown_font=self._ui_font(13, False))
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if getattr(self, "language_setting_label", None) is not None:
                self.language_setting_label.configure(text=self._t("language_label"), font=self._ui_font(12, True))
            if self.language_var is not None and self.language_menu is not None:
                self.language_menu.configure(values=self._language_menu_values(), font=self._ui_font(13, False))
                self.language_var.set(self._language_display(self.language))
                try:
                    self.language_menu.configure(dropdown_font=self._ui_font(13, False))
                except Exception:
                    pass
        except Exception:
            pass

        # Window options
        try:
            if getattr(self, "window_options_label", None) is not None:
                self.window_options_label.configure(text=self._t("window_options"), font=self._ui_font(12, True), anchor="e" if self.rtl else "w")
            if getattr(self, "always_on_top_cb", None) is not None:
                self.always_on_top_cb.configure(text=self._t("always_on_top"), font=self._ui_font(13, False))
            if getattr(self, "background_cb", None) is not None:
                self.background_cb.configure(text=self._t("run_in_background"), font=self._ui_font(13, False))
        except Exception:
            pass

        # Alerts
        try:
            if hasattr(self, "alerts_title_label"):
                self.alerts_title_label.configure(text=self._t("alerts_title"), font=self._ui_font(12, True))
            if hasattr(self, "alerts_cb"):
                self.alerts_cb.configure(text=self._t("enable_alerts"), font=self._ui_font(13, False))
        except Exception:
            pass

        try:
            if hasattr(self, "alert_threshold_label"):
                self.alert_threshold_label.configure(text=self._t("threshold", value=float(self.alert_threshold_percent)), font=self._ui_font(12, False))
        except Exception:
            pass

        # Tools
        try:
            if hasattr(self, "tools_title_label"):
                self.tools_title_label.configure(text=self._t("tools"), font=self._ui_font(12, True))
            if hasattr(self, "clear_cache_btn"):
                self.clear_cache_btn.configure(text=self._t("btn_clear_cache"), font=self._ui_font(13, False))
            if hasattr(self, "perf_btn"):
                self.perf_btn.configure(text=self._t("btn_performance"), font=self._ui_font(13, False))
        except Exception:
            pass

        # Portfolio action buttons + filter
        try:
            if getattr(self, "portfolio_filter_entry", None) is not None:
                self.portfolio_filter_entry.configure(
                    placeholder_text=self._t("placeholder_portfolio_filter"),
                    font=self._ui_font(12, False),
                    justify="right" if self.rtl else "left",
                )
            if getattr(self, "portfolio_search_toggle_btn", None) is not None:
                self.portfolio_search_toggle_btn.configure(font=self._ui_font(15, False))
            if getattr(self, "portfolio_add_btn", None) is not None:
                self.portfolio_add_btn.configure(text=self._t("portfolio_add_title"), font=self._ui_font(13, False))
        except Exception:
            pass

        # Sort menu text + values
        try:
            if self.sort_label is not None:
                self.sort_label.configure(text=self._t("sort"), font=self._ui_font(12, True))
            if hasattr(self, "portfolio_sort_menu"):
                self.portfolio_sort_menu.configure(values=self._get_sort_display_values(), font=self._ui_font(13, False))
                try:
                    self.portfolio_sort_menu.configure(dropdown_font=self._ui_font(13, False))
                except Exception:
                    pass
            if hasattr(self, "portfolio_sort_var"):
                self.portfolio_sort_var.set(self._sort_key_to_display(self.portfolio_sort_mode_key))
        except Exception:
            pass

        # Theme buttons
        try:
            if "liquid_glass" in self.theme_buttons:
                self.theme_buttons["liquid_glass"].configure(text=self._t("theme_liquid_glass"), font=self._ui_font(13, False))
            if "crystal" in self.theme_buttons:
                self.theme_buttons["crystal"].configure(text=self._t("theme_crystal"), font=self._ui_font(13, False))
            if "paper" in self.theme_buttons:
                self.theme_buttons["paper"].configure(text=self._t("theme_paper"), font=self._ui_font(13, False))
            if "paper_noir" in self.theme_buttons:
                self.theme_buttons["paper_noir"].configure(text=self._t("theme_paper_noir"), font=self._ui_font(13, False))
        except Exception:
            pass

        # Last update label
        try:
            if hasattr(self, "last_update_label"):
                tval = str(self.last_update)
                if self.language == "fa":
                    tval = tval.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
                else:
                    tval = tval.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
                self.last_update_label.configure(text=self._t("last_update", time=tval), font=self._ui_font(12, False))
        except Exception:
            pass

        # Update cards typography
        try:
            for card in list(self.featured_cards.values()) + list(self.portfolio_cards.values()):
                card.set_typography(font_getter=self._ui_font, rtl=self.rtl)
        except Exception:
            pass

        # Re-render text-heavy UI pieces so names/units switch cleanly
        try:
            self._render_featured_cards()
            self._render_portfolio_cards()
            self._update_insights()
        except Exception:
            pass

        # Update status strings in the current language
        try:
            self._update_connection_status(self.connection_status)
            self._update_status_displays()
        except Exception:
            pass


        # Refresh translated menus + desktop widgets
        try:
            self.widget_manager.apply_typography()
        except Exception:
            pass

        try:
            # Force rebuild because display strings depend on language
            self._symbol_menu_sig = ""
            self._refresh_symbol_menus()
        except Exception:
            pass

        # History period values are language-dependent
        try:
            if self.history_period_menu is not None:
                old_seconds = int(getattr(self, "_history_period_seconds", 24 * 3600))
                vals, self._history_period_map = self._history_period_options()
                self.history_period_menu.configure(values=vals)

                # Keep selection by seconds
                best = vals[0] if vals else self._t("period_24h")
                sec_map = {
                    1 * 3600: self._t("period_1h"),
                    6 * 3600: self._t("period_6h"),
                    24 * 3600: self._t("period_24h"),
                    7 * 86400: self._t("period_7d"),
                }
                best = sec_map.get(old_seconds, best)
                if self.history_period_var is not None:
                    self.history_period_var.set(best)
        except Exception:
            pass

        # Widget type values are language-dependent
        try:
            if self.widgets_type_menu is not None and self.widgets_type_var is not None:
                old_disp = self.widgets_type_var.get()
                old_map = getattr(self, "_widget_type_map", {}) or {}
                internal = old_map.get(old_disp, "price")

                vals, self._widget_type_map = self._widget_type_options()
                self.widgets_type_menu.configure(values=vals)

                rev = {v: k for k, v in self._widget_type_map.items()}
                self.widgets_type_var.set(rev.get(internal, vals[0] if vals else old_disp))
                self._on_widget_type_changed()
        except Exception:
            pass

        try:
            self._update_converter_result()
        except Exception:
            pass

        # Update selector (strings like "No matches")
        try:
            self._update_currency_selector()
        except Exception:
            pass

        try:
            self._update_price_basis_toggle()
        except Exception:
            pass

        try:
            self._refresh_fab_texts()
        except Exception:
            pass


    def _on_language_changed(self, *_: Any) -> None:
        try:
            if self.language_var is None:
                return
            new_lang = self._display_to_language(self.language_var.get())
            if new_lang == self.language:
                return
            self.language = new_lang
            self.rtl = is_rtl(self.language)
            db_manager.save_preference("language", self.language)
            self._rebuild_main_sections()
        except Exception:
            pass

    # ----- selector helpers -----

    def _open_symbol_menu_picker(self, var: Optional[ctk.StringVar], title: str, on_change: Callable[[], None], include_toman: bool = True) -> None:
        if var is None:
            return
        options: List[Tuple[str, str]] = []
        for disp, sym in self._converter_symbol_map.items():
            if not include_toman and sym == "TOMAN":
                continue
            options.append((sym, disp))
        options.sort(key=lambda t: t[1].lower())

        current_disp = var.get()
        current_sym = self._converter_symbol_map.get(current_disp)

        def on_select(symbol: str) -> None:
            for sym, disp in options:
                if sym == symbol:
                    var.set(disp)
                    break
            try:
                on_change()
            except Exception:
                pass

        self._open_currency_picker(options, on_select, title, current=current_sym)

    def _open_portfolio_currency_picker(self) -> None:
        excluded = set(self.user_portfolio)
        options: List[Tuple[str, str]] = []
        for sym, data in self.currencies.items():
            if sym in excluded:
                continue
            name = self._currency_display_name(sym, data)
            options.append((sym, f"{name} ({sym})"))
        options.sort(key=lambda t: t[1].lower())

        self._open_currency_picker(
            options,
            self._add_currency_to_portfolio,
            self._t("portfolio_add_title"),
            current=None,
            stay_open=True,
        )

    def _get_selector_values(self, *, search: str, excluded: Set[str]) -> List[str]:
        search = (search or "").strip().lower()
        options: List[str] = []
        for sym, data in self.currencies.items():
            if sym in excluded:
                continue
            name = self._currency_display_name(sym, data)
            display = f"{name} ({sym})"
            if search:
                if search not in sym.lower() and search not in name.lower() and search not in display.lower():
                    continue
            options.append(display)

        if not options:
            return [self._t("no_matches")]

        return sorted(options, key=lambda s: s.lower())

    # ----- responsive layout -----

    def _on_window_resize(self, event: Any) -> None:
        try:
            if event.widget is not self:
                return
            if self._resize_after_id:
                self.after_cancel(self._resize_after_id)
        except Exception:
            pass

        try:
            if self._fab_menu_open:
                self._fab_close_menu()
        except Exception:
            pass

        try:
            self._reposition_fab()
        except Exception:
            pass

        try:
            self._resize_after_id = self.after(180, self._on_resize_settled)
        except Exception:
            pass

    def _on_resize_settled(self) -> None:
        if getattr(self, "_resize_settle_running", False):
            return
        self._resize_settle_running = True
        try:
            self._recalculate_layout()
        except Exception:
            pass
        try:
            self._reposition_fab()
        except Exception:
            pass
        finally:
            self._resize_settle_running = False

    def _recalculate_layout(self) -> None:
        try:
            w = int(self.winfo_width())
        except Exception:
            return

        # Approximate available width inside the scroll frame
        available = max(400, w - 120)
        card_total = int(config.CARD_WIDTH + config.CARD_PADDING * 2)
        new_cols = int(max(2, min(8, available // max(1, card_total))))

        if new_cols != self.grid_columns:
            self.grid_columns = new_cols
            self._apply_grid_columns()
            self._refresh_featured_symbols()
            self._render_featured_cards()
            self._render_portfolio_cards()

    def _apply_grid_columns(self) -> None:
        try:
            max_cols = 8
            for container in (getattr(self, "featured_container", None), getattr(self, "portfolio_container", None)):
                if container is None:
                    continue
                for i in range(max_cols):
                    container.grid_columnconfigure(i, weight=1 if i < self.grid_columns else 0)
        except Exception:
            pass


# ==========================================================================
# PreferencesMixin
# ==========================================================================

class PreferencesMixin:
    """Preference load/save. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # Preferences
    # -------------------------------------------------------------------------

    def _load_saved_preferences(self) -> None:
        """Load persisted user preferences from the local DB.

        Note: This runs BEFORE UI widgets are created, so it must only populate state.
        """
        # App mode (normal vs crypto) — controls which API sources are used.
        # Loaded before the portfolios below, since portfolio storage is keyed by mode.
        saved_mode = str(db_manager.load_preference("app_mode", "normal") or "normal").strip().lower()
        self.app_mode = saved_mode if saved_mode in ("normal", "crypto") else "normal"

        saved_basis = str(db_manager.load_preference("crypto_price_basis", "usdt") or "usdt").strip().lower()
        self.crypto_price_basis = saved_basis if saved_basis in ("usdt", "irr") else "usdt"

        saved_normal_basis = str(db_manager.load_preference("normal_price_basis", "irr") or "irr").strip().lower()
        self.normal_price_basis = saved_normal_basis if saved_normal_basis in ("irr", "usd") else "irr"

        # Portfolio — normal and crypto each have their own storage, loaded
        # independently so items added under one mode never appear in the other.
        self._portfolios["normal"] = db_manager.load_selected_currencies(mode="normal")
        self._portfolios["crypto"] = db_manager.load_selected_currencies(mode="crypto")

        # Legacy cleanup: older versions used to auto-save featured items in the portfolio table
        legacy_auto_featured = {"USD", "EUR", "GBP", "BTC", "ETH", "SEKEH", "GOLD", "GERAM18", "AED", "TRY"}
        if self._portfolios["normal"] & legacy_auto_featured:
            self._portfolios["normal"] -= legacy_auto_featured
            db_manager.save_selected_currencies(self._portfolios["normal"], mode="normal")

        # Language
        saved_lang = db_manager.load_preference("language", "en")
        self.language = self._normalize_language(str(saved_lang))

        # Theme
        saved_theme = db_manager.load_preference("selected_theme", "paper_noir")
        self.selected_theme = self._normalize_theme_key(str(saved_theme))

        saved_widget_theme = str(db_manager.load_preference("widget_theme", "auto") or "auto").strip().lower()
        self.widget_theme = saved_widget_theme if saved_widget_theme == "auto" else self._normalize_theme_key(saved_widget_theme)

        # Settings
        self.auto_refresh_active = bool(db_manager.load_preference("auto_refresh", True))

        raw_interval = db_manager.load_preference("refresh_interval_seconds", config.DEFAULT_REFRESH_INTERVAL)
        try:
            self.refresh_interval_seconds = int(raw_interval or config.DEFAULT_REFRESH_INTERVAL)
        except Exception:
            self.refresh_interval_seconds = int(config.DEFAULT_REFRESH_INTERVAL)
        self.refresh_interval_seconds = int(max(config.MIN_REFRESH_INTERVAL, min(config.MAX_REFRESH_INTERVAL, self.refresh_interval_seconds)))

        self.alerts_enabled = bool(db_manager.load_preference("alerts_enabled", True))
        try:
            self.alert_threshold_percent = float(db_manager.load_preference("alert_threshold_percent", 2.5) or 2.5)
        except Exception:
            self.alert_threshold_percent = 2.5
        self.alert_threshold_percent = float(max(0.5, min(10.0, self.alert_threshold_percent)))

        self.always_on_top = bool(db_manager.load_preference("always_on_top", False))
        try:
            self.attributes("-topmost", bool(self.always_on_top))
        except Exception:
            pass

        self.run_in_background = bool(db_manager.load_preference("run_in_background", True))
        raw_sort = db_manager.load_preference("portfolio_sort_mode", "default")
        self.portfolio_sort_mode_key = self._normalize_sort_key(str(raw_sort))

        # Layout (sections order + visibility)
        # Primary dashboard focus: Featured Market -> Your Portfolio -> Market Insights.
        # Everything else is secondary and now lives behind the floating action menu
        # instead of cluttering the main screen (still reachable/toggleable from there).
        default_order = [
            "hero",
            "featured",
            "portfolio",
            "insights",
            "status",
            "history",
            "converter",
            "widgets",
            "controls",
            "settings",
            "theme",
        ]

        try:
            raw_order = db_manager.load_preference("section_order_json", "")
            order = json.loads(raw_order) if raw_order else []
            if isinstance(order, list) and order:
                # keep only known keys, preserve defaults for missing ones
                cleaned = [k for k in order if k in default_order]
                for k in default_order:
                    if k not in cleaned:
                        cleaned.append(k)
                self.section_order = cleaned
            else:
                self.section_order = list(default_order)
        except Exception:
            self.section_order = list(default_order)

        primary_sections = {"hero", "featured", "portfolio", "insights", "status"}
        default_enabled = {k: (k in primary_sections) for k in default_order}

        # These sections are load-bearing: core widgets (the "add to portfolio"
        # selector, the featured/portfolio card containers) only get built when
        # their section runs, and other code assumes they exist. Disabling them
        # previously broke API status updates, portfolio saving, and more —
        # so they can never be turned off, and any previously-saved "off" state
        # is repaired automatically here.
        mandatory_sections = {"hero", "featured", "portfolio"}

        try:
            raw_enabled = db_manager.load_preference("section_enabled_json", "")
            enabled = json.loads(raw_enabled) if raw_enabled else {}
            if isinstance(enabled, dict) and enabled:
                self.section_enabled = {k: bool(enabled.get(k, default_enabled[k])) for k in default_order}
            else:
                self.section_enabled = dict(default_enabled)
        except Exception:
            self.section_enabled = dict(default_enabled)

        for k in mandatory_sections:
            self.section_enabled[k] = True
