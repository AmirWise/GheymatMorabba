"""The main application window.

LiquidGlassPriceTracker was originally one ~5,300-line class. It is now
MainWindow, composed from focused mixins (one per dashboard concern) so
each piece can be read, tested, and changed independently while still
sharing one instance's state via `self` -- the standard pattern for
splitting a large, tightly-coupled Tkinter class without a full rewrite.
"""

from __future__ import annotations

import queue
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import customtkinter as ctk

from core.config import config, ConnectionStatus
from core.i18n import is_rtl
from core.utils import logger, apply_dark_titlebar
from data.api import APIManager
from core.theme import theme_manager
from ui.desktop_widgets import DesktopWidgetManager
from ui.ui_support import VisualEffectsManager, ToastManager
from ui.mixin_foundation import WindowMixin, StartupMixin, LocalizationMixin, PreferencesMixin
from ui.mixin_layout import LayoutMixin, FabMixin, SectionCustomizationMixin
from ui.mixin_sections import HistoryConverterMixin, DesktopWidgetsSectionMixin
from ui.mixin_actions import PortfolioActionsMixin, SettingsActionsMixin, ThemeMixin
from ui.widgets import CurrencyCardWidget, SparklineCanvas


class MainWindow(
    WindowMixin,
    LocalizationMixin,
    StartupMixin,
    LayoutMixin,
    FabMixin,
    SectionCustomizationMixin,
    HistoryConverterMixin,
    DesktopWidgetsSectionMixin,
    PreferencesMixin,
    PortfolioActionsMixin,
    SettingsActionsMixin,
    ThemeMixin,
    ctk.CTk,
):
    """The dashboard window. Mixin order matches the original file's own
    section order; none of them depend on Python MRO beyond sharing
    ``self``, so the order is cosmetic."""

    def __init__(self):
        super().__init__()

        # ---------------------------------------------------------------------
        # Language / layout defaults
        # ---------------------------------------------------------------------
        self.language: str = "en"
        self.rtl: bool = True

        # Responsive grid (featured + portfolio)
        self.grid_columns: int = int(max(2, min(config.GRID_COLUMNS, 8)))
        self._resize_after_id: Optional[str] = None

        # Managers
        self.api_manager = APIManager()
        self.effects_manager = VisualEffectsManager(self)
        self.executor = ThreadPoolExecutor(max_workers=config.MAX_WORKER_THREADS)
        self.toasts = ToastManager(self, font_getter=self._ui_font, rtl=self.rtl)
        self.widget_manager = DesktopWidgetManager(self)

        # State
        self.currencies: Dict[str, Dict[str, Any]] = {}
        self._portfolios: Dict[str, Set[str]] = {"normal": set(), "crypto": set()}
        self.featured_symbols: List[str] = []

        self.connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self.last_update: str = "—"

        # Preferences (defaults)
        self.selected_theme: str = "paper_noir"
        self.widget_theme: str = "auto"
        self.app_mode: str = "normal"
        self.crypto_price_basis: str = "usdt"
        self.normal_price_basis: str = "irr"
        self._tether_irr_rate: Optional[float] = None
        self.auto_refresh_active: bool = True
        self.refresh_interval_seconds: int = config.DEFAULT_REFRESH_INTERVAL
        self.alerts_enabled: bool = True
        self.alert_threshold_percent: float = 2.5
        self.always_on_top: bool = False
        self.run_in_background: bool = False
        # Portfolio sort key: default | name | symbol | price | change
        self.portfolio_sort_mode_key: str = "default"

        # Internals
        self._auto_refresh_after_id: Optional[str] = None
        self._selector_update_after_id: Optional[str] = None
        self._last_seen_prices: Dict[str, float] = {}
        # Session tracking (for "Session Tracker" section)
        self._session_open: Dict[str, float] = {}
        self._session_min: Dict[str, float] = {}
        self._session_max: Dict[str, float] = {}
        self._last_alert_ts: Dict[str, float] = {}
        self._recent_alerts: deque = deque(maxlen=30)
        self._history_points: deque[Tuple[float, float]] = deque(maxlen=config.HISTORY_MAX_POINTS)
        self._history_symbol: str = "USD"
        self._history_period_seconds: int = 24 * 3600
        self._history_last_loaded: float = 0.0
        self._last_history_prune: float = 0.0

        self._converter_symbol_map: Dict[str, str] = {}
        self._converter_last_update: float = 0.0
        self._symbol_menu_sig: str = ""

        self._portfolio_filter_after_id: Optional[str] = None

        # UI refs
        self.ui_elements: Dict[str, Any] = {}
        self.theme_buttons: Dict[str, ctk.CTkButton] = {}
        self.featured_cards: Dict[str, CurrencyCardWidget] = {}
        self.portfolio_cards: Dict[str, CurrencyCardWidget] = {}
        self.portfolio_empty_label: Optional[ctk.CTkLabel] = None

        # Extra UI refs (localization-friendly)
        self.toolbar_title_label: Optional[ctk.CTkLabel] = None
        self.language_var: Optional[ctk.StringVar] = None
        self.language_menu: Optional[ctk.CTkOptionMenu] = None
        self.always_on_top_var: Optional[ctk.BooleanVar] = None
        self.always_on_top_cb: Optional[ctk.CTkCheckBox] = None
        self.background_var: Optional[ctk.BooleanVar] = None
        self.background_cb: Optional[ctk.CTkCheckBox] = None
        self.window_options_label: Optional[ctk.CTkLabel] = None

        self.hero_title_label: Optional[ctk.CTkLabel] = None
        self.hero_subtitle_label: Optional[ctk.CTkLabel] = None
        self.hero_version_label: Optional[ctk.CTkLabel] = None

        self.featured_title_label: Optional[ctk.CTkLabel] = None
        self.insights_title_label: Optional[ctk.CTkLabel] = None
        self.portfolio_title_label: Optional[ctk.CTkLabel] = None
        self.history_title_label: Optional[ctk.CTkLabel] = None
        self.converter_title_label: Optional[ctk.CTkLabel] = None
        self.widgets_title_label: Optional[ctk.CTkLabel] = None
        self.controls_title_label: Optional[ctk.CTkLabel] = None
        self.settings_title_label: Optional[ctk.CTkLabel] = None
        self.theme_title_label: Optional[ctk.CTkLabel] = None

        self.gainers_title_label: Optional[ctk.CTkLabel] = None
        self.losers_title_label: Optional[ctk.CTkLabel] = None

        self.sort_label: Optional[ctk.CTkLabel] = None

        # New: portfolio filter
        self.portfolio_filter_var: Optional[ctk.StringVar] = None
        self.portfolio_filter_entry: Optional[ctk.CTkEntry] = None

        # New: history section
        self.history_symbol_var: Optional[ctk.StringVar] = None
        self.history_period_var: Optional[ctk.StringVar] = None
        self.history_symbol_menu: Optional[ctk.CTkOptionMenu] = None
        self.history_period_menu: Optional[ctk.CTkOptionMenu] = None
        self.history_sparkline: Optional[SparklineCanvas] = None
        self.history_stats_label: Optional[ctk.CTkLabel] = None

        # New: converter section
        self.converter_amount_var: Optional[ctk.StringVar] = None
        self.converter_from_var: Optional[ctk.StringVar] = None
        self.converter_to_var: Optional[ctk.StringVar] = None
        self.converter_result_label: Optional[ctk.CTkLabel] = None
        self.converter_from_btn: Optional[ctk.CTkButton] = None
        self.converter_to_btn: Optional[ctk.CTkButton] = None
        self.converter_inline_picker_frame: Optional[ctk.CTkFrame] = None
        self._converter_picker_target: Optional[str] = None
        self._converter_picker_search_var: Optional[ctk.StringVar] = None

        # New: widgets section
        self.widgets_type_var: Optional[ctk.StringVar] = None
        self.widgets_symbol_var: Optional[ctk.StringVar] = None
        self.widgets_type_menu: Optional[ctk.CTkOptionMenu] = None
        self.widgets_symbol_menu: Optional[ctk.CTkOptionMenu] = None  # unused now
        self.widgets_symbol_btn: Optional[ctk.CTkButton] = None
        self.widgets_inline_picker_frame: Optional[ctk.CTkFrame] = None
        self._widgets_picker_search_var: Optional[ctk.StringVar] = None
        self._widgets_picker_trace_id: Optional[str] = None
        self.widgets_active_list: Optional[ctk.CTkFrame] = None
        self.widget_theme_var: Optional[ctk.StringVar] = None
        self.widget_theme_menu: Optional[ctk.CTkOptionMenu] = None
        self.featured_container: Optional[ctk.CTkFrame] = None
        self.portfolio_container: Optional[ctk.CTkFrame] = None

        # Floating action button / quick-access menu
        self.fab_button: Optional[ctk.CTkButton] = None
        self.crypto_toggle_button: Optional[ctk.CTkButton] = None
        self.fab_window: Optional[ctk.CTkToplevel] = None
        self._fab_hovering: bool = False
        self._fab_pressed: bool = False
        self._fab_visible: bool = True
        self.fab_menu_frame: Optional[ctk.CTkToplevel] = None
        self._fab_menu_open: bool = False
        self._fab_closing: bool = False
        self._fab_anim_job: Optional[str] = None
        self._fab_close_anim_job: Optional[str] = None
        self._fab_menu_buttons: Dict[str, ctk.CTkButton] = {}

        self._fab_base_size: int = 58
        self._fab_hover_size: int = 62
        self._fab_press_delta: int = 5
        self._fab_target_size: int = 58
        self._fab_current_size_f: float = 58.0
        self._fab_size_job: Optional[str] = None

        self._crypto_pressed: bool = False
        self._crypto_base_w: int = 84
        self._crypto_base_h: int = 38
        self._crypto_press_delta: int = 4
        self._crypto_target_w: int = 84
        self._crypto_target_h: int = 38
        self._crypto_current_w_f: float = 84.0
        self._crypto_current_h_f: float = 38.0
        self._crypto_size_job: Optional[str] = None

        self._fab_panel_geom: Optional[Tuple[int, int, int, int, float]] = None

        # Price-basis pill dock (collapsed by default, expands with the FAB menu)
        self._fab_dock_solo_width: int = 0
        self._fab_dock_expanded_width: int = 0
        self._fab_dock_anim_job: Optional[str] = None


        # Build
        self._setup_window()
        self._load_resources()

        # Load preferences early so the initial layout/text matches (language, RTL, interval, theme)
        self._load_saved_preferences()
        self.rtl = is_rtl(self.language)

        # Apply the correct appearance mode *before* building widgets so the
        # dashboard is never briefly painted in the wrong Light/Dark mode.
        try:
            startup_theme = self._normalize_theme_key(self.selected_theme)
            if startup_theme == "paper":
                ctk.set_appearance_mode("Light")
            elif startup_theme == "paper_noir":
                ctk.set_appearance_mode("Dark")
            else:
                ctk.set_appearance_mode("System")
            self.configure(fg_color=(theme_manager.colors.bg_light, theme_manager.colors.bg_dark))
            apply_dark_titlebar(self, ctk.get_appearance_mode() == "Dark")
        except Exception:
            pass

        self._create_user_interface()
        self._bind_shortcuts()

        # Responsive layout
        try:
            self.bind("<Configure>", self._on_window_resize)
        except Exception:
            pass

        # Cached data (fast first paint) + apply language now that widgets exist
        self._apply_language()
        self._recalculate_layout()
        self._load_cached_first_paint()

        # Apply theme + start data systems
        self.after(120, lambda: self._apply_theme_with_feedback(self.selected_theme, show_feedback=False, save_preference=False))
        # Thread-safe UI dispatch queue (used by worker threads)
        self._ui_task_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._ui_queue_running = True
        self.after(50, self._drain_ui_task_queue)

        self._start_data_systems()

        # Restore desktop widgets (if any)
        self.after(950, self.widget_manager.restore)

        logger.info("App initialized.")

    # -------------------------------------------------------------------------
    # Portfolio storage (isolated per app mode)
    # -------------------------------------------------------------------------

    @property
    def user_portfolio(self) -> Set[str]:
        """The portfolio for the *current* app mode. Normal and crypto each
        have their own backing set, so adding a symbol in one mode can never
        leak into the other."""
        return self._portfolios.setdefault(self.app_mode, set())

    @user_portfolio.setter
    def user_portfolio(self, value: Iterable[str]) -> None:
        self._portfolios[self.app_mode] = set(value or [])
