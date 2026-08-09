"""MainWindow mixins: the History/Converter sections and the Featured/Insights/Widgets sections."""


from __future__ import annotations

import customtkinter as ctk
import time

from typing import Any, Dict, List, Optional, Set, Tuple
from core.config import config, ConnectionStatus, FORWARD_PRICE_ASSETS
from data.api import forward_price_service, CRYPTO_SYMBOLS
from data.db import db_manager
from core.theme import theme_manager
from core.utils import apply_dark_titlebar, logger
from ui.widgets import CurrencyCardWidget


# ==========================================================================
# HistoryConverterMixin
# ==========================================================================

class HistoryConverterMixin:
    """History + Converter sections. Composed onto MainWindow."""


    # -------------------------------------------------------------------------
    # New Sections: History / Converter / Widgets
    # -------------------------------------------------------------------------

    def _symbol_to_display(self, sym: str, data: Optional[Dict[str, Any]] = None) -> str:
        s = str(sym or "").upper().strip()
        if s == "TOMAN":
            return "TOMAN • تومان" if self.language == "fa" else "Toman (IRR)"

        d = data or self.currencies.get(s, {}) or {}
        name = self._currency_display_name(s, d) if d else s
        if self.language == "fa":
            return f"{s} • {name}"
        return f"{name} ({s})"

    def _display_to_symbol_value(self, display: str) -> str:
        raw = str(display or "").strip()
        if raw in self._converter_symbol_map:
            return self._converter_symbol_map[raw]

        # Fallback parsing (in case of old saved UI values)
        if "(" in raw and raw.endswith(")"):
            inside = raw.split("(")[-1].rstrip(")").strip()
            if inside:
                return inside.upper()
        if "•" in raw:
            left = raw.split("•", 1)[0].strip()
            if left:
                return left.upper()
        return raw.upper()

    def _refresh_symbol_menus(self, force: bool = False) -> None:
        # Build signature to avoid reconfiguring menus every refresh
        try:
            keys = sorted([k for k in self.currencies.keys() if k])
            sig = "|".join(keys[:2000])
            if not force and sig == self._symbol_menu_sig:
                return
            self._symbol_menu_sig = sig
        except Exception:
            keys = sorted(list(self.currencies.keys()))

        # Build display list
        display_values: List[str] = []
        mapping: Dict[str, str] = {}

        # Converter gets a pseudo TOMAN unit
        toman_display = self._symbol_to_display("TOMAN", None)
        display_values.append(toman_display)
        mapping[toman_display] = "TOMAN"

        for sym in keys:
            d = self.currencies.get(sym, {})
            disp = self._symbol_to_display(sym, d)
            display_values.append(disp)
            mapping[disp] = str(sym).upper().strip()

        self._converter_symbol_map = mapping

        # Update menus safely
        try:
            # History menu only -- no TOMAN pseudo-unit here. Widgets'
            # symbol picker builds its own list live when opened.
            hw_values = [v for v in display_values if mapping.get(v) != "TOMAN"]

            if self.history_symbol_menu is not None:
                self.history_symbol_menu.configure(values=hw_values)
                try:
                    self.history_symbol_menu.configure(dropdown_font=self._ui_font(13, False))
                except Exception:
                    pass
        except Exception:
            pass

        # Ensure vars are valid — preserve the underlying symbol across a
        # refresh (e.g. a language switch changes display text format, not
        # the selected currency) rather than jumping to an unrelated default.
        try:
            changed = False

            def _resolve_or_default(var: Optional[ctk.StringVar], fallback_index: int) -> None:
                nonlocal changed
                if var is None:
                    return
                current = var.get()
                if current in display_values:
                    return
                prior_symbol = self._display_to_symbol_value(current)
                for disp, sym in mapping.items():
                    if sym == prior_symbol:
                        var.set(disp)
                        changed = True
                        return
                var.set(display_values[fallback_index] if len(display_values) > fallback_index else display_values[0])
                changed = True

            _resolve_or_default(self.converter_from_var, 1)
            _resolve_or_default(self.converter_to_var, 2)
            if changed:
                self._update_converter_result()
            if self.history_symbol_var is not None:
                # Keep previously selected symbol if possible
                cur = self.history_symbol_var.get()
                if cur not in display_values:
                    # pick USD if exists
                    pick = None
                    for v, s in mapping.items():
                        if s == "USD":
                            pick = v
                            break
                    self.history_symbol_var.set(pick or (display_values[1] if len(display_values) > 1 else display_values[0]))
            if self.widgets_symbol_var is not None and self.widgets_symbol_var.get() not in display_values:
                self.widgets_symbol_var.set(display_values[1] if len(display_values) > 1 else display_values[0])
        except Exception:
            pass

    # ----- History -----

    def _history_period_options(self) -> Tuple[List[str], Dict[str, int]]:
        opts = [
            ("period_1h", 1 * 3600),
            ("period_6h", 6 * 3600),
            ("period_24h", 24 * 3600),
            ("period_7d", 7 * 86400),
        ]
        display = [self._t(k) for k, _ in opts]
        mapping = {self._t(k): int(sec) for k, sec in opts}
        return display, mapping

    
    def _create_history_section(self) -> None:
        """Session Tracker (replaces chart)."""
        row = self._next_row()
        card = self._create_glass_card(self.scroll_frame, glass_level=2)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 20))

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=18)

        title_txt = ("📌 ردیاب جلسه" if self.language == "fa" else "📌 Session Tracker")
        title = ctk.CTkLabel(
            content,
            text=title_txt,
            font=self._ui_font(18, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        title.pack(fill="x")

        hint = ctk.CTkLabel(
            content,
            text=("این بخش فقط از زمان باز بودن برنامه داده جمع میکند." if self.language == "fa" else "Tracks changes only while the app is running."),
            font=self._ui_font(12, False),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
            justify="right" if self.rtl else "left",
            wraplength=640,
        )
        hint.pack(fill="x", pady=(8, 0))

        self.session_tracker_label = ctk.CTkLabel(
            content,
            text="—",
            font=self._ui_font(13, False),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
            justify="right" if self.rtl else "left",
        )
        self.session_tracker_label.pack(fill="x", pady=(12, 0))

        # Disable old history controls for safety
        self.history_symbol_menu = None
        self.history_period_menu = None
        self.history_sparkline = None
        self.history_stats_label = None

    def _build_session_summary_text(self) -> Optional[str]:
        try:
            watch: List[str] = []
            watch.extend([str(s).upper().strip() for s in (self.featured_symbols or []) if s])
            watch.extend([str(s).upper().strip() for s in (self.user_portfolio or set()) if s])
            watch = [s for s in watch if s and s in self.currencies]
            if not watch:
                return None

            # Update session maps
            for sym in watch:
                d = self.currencies.get(sym) or {}
                try:
                    price = float(d.get("price", 0) or 0)
                except Exception:
                    continue
                if price <= 0:
                    continue

                if sym not in self._session_open:
                    self._session_open[sym] = price
                    self._session_min[sym] = price
                    self._session_max[sym] = price
                else:
                    self._session_min[sym] = min(self._session_min.get(sym, price), price)
                    self._session_max[sym] = max(self._session_max.get(sym, price), price)

            # Build summary lines (top movers in this session)
            items = []
            for sym in watch:
                if sym not in self._session_open:
                    continue
                open_p = float(self._session_open.get(sym, 0) or 0)
                cur_p = float(self.currencies.get(sym, {}).get("price", 0) or 0)
                if open_p <= 0 or cur_p <= 0:
                    continue
                ch_pct = (cur_p - open_p) / open_p * 100.0
                items.append((sym, ch_pct, cur_p))

            items.sort(key=lambda x: x[1], reverse=True)
            top = items[:5]
            bottom = list(reversed(items[-5:])) if len(items) > 5 else items[-5:]

            lines: List[str] = []
            hdr = ("از شروع جلسه" if self.language == "fa" else "Since session start")
            lines.append(hdr + f" • {self._t('last_update', time=getattr(self, 'last_update', '—'))}")
            lines.append("")

            if top:
                lines.append(("بیشترین رشد:" if self.language == "fa" else "Top gainers:"))
                for sym, ch_pct, cur_p in top:
                    lines.append(f"  ▲ {sym}: {ch_pct:+.2f}%  •  {CurrencyCardWidget._format_price(cur_p)}")
                lines.append("")

            if bottom:
                lines.append(("بیشترین افت:" if self.language == "fa" else "Top losers:"))
                for sym, ch_pct, cur_p in bottom:
                    lines.append(f"  ▼ {sym}: {ch_pct:+.2f}%  •  {CurrencyCardWidget._format_price(cur_p)}")

            return "\n".join(lines).strip()
        except Exception:
            return None

    def _update_session_tracker(self) -> None:
        try:
            txt = self._build_session_summary_text()
            if getattr(self, "session_tracker_label", None) is not None:
                self.session_tracker_label.configure(text=txt if txt else "—")
        except Exception:
            pass


    def _on_history_selection_changed(self) -> None:
        try:
            if self.history_symbol_var is None or self.history_period_var is None:
                return
            sym = self._display_to_symbol_value(self.history_symbol_var.get())
            period_seconds = int(self._history_period_map.get(self.history_period_var.get(), 24 * 3600))
            self._history_symbol = sym
            self._history_period_seconds = period_seconds
            self._load_history_async(sym, period_seconds)
        except Exception:
            pass

    def _load_history_async(self, sym: str, period_seconds: int) -> None:
        if self.history_stats_label is not None:
            self.history_stats_label.configure(text=self._t("history_loading"))
        if self.history_sparkline is not None:
            self.history_sparkline.clear()

        since_ts = time.time() - float(max(60, period_seconds))
        self._history_last_loaded = time.time()

        def worker():
            points = db_manager.load_price_history(sym, since_ts=since_ts, limit=2000)

            # If we do not have enough cached data and the symbol is a supported crypto,
            # fetch a real market chart once and persist it for future sessions.
            if len(points) < 10:
                try:
                    if str(sym).upper().strip() in getattr(self.api_manager, "_COINGECKO_ID_MAP", {}):
                        fetched = self.api_manager.fetch_crypto_history(str(sym).upper().strip(), period_seconds=period_seconds)
                        if fetched:
                            db_manager.insert_price_history_bulk([(str(sym).upper().strip(), ts, price) for ts, price in fetched])
                            points = db_manager.load_price_history(sym, since_ts=since_ts, limit=2000)
                except Exception:
                    pass

            return points

        fut = None
        try:
            fut = self.executor.submit(worker)
        except Exception:
            return

        def done(_):
            try:
                points = fut.result() if fut else []
            except Exception:
                points = []
            self._enqueue_ui(lambda: self._apply_history_points(sym, points))

        try:
            fut.add_done_callback(done)  # type: ignore[union-attr]
        except Exception:
            self._enqueue_ui(lambda: done(None))

    def _apply_history_points(self, sym: str, points: List[Tuple[float, float]]) -> None:
        try:
            self._history_points.clear()
            for ts, price in points[-config.HISTORY_MAX_POINTS :]:
                self._history_points.append((float(ts), float(price)))
            self._update_history_chart()
        except Exception:
            pass

    def _update_history_chart(self) -> None:
        if self.history_sparkline is None or self.history_stats_label is None:
            return
        if not self._history_points:
            self.history_sparkline.clear()
            self.history_stats_label.configure(text=self._t("history_no_data"))
            return

        values = [p for _, p in self._history_points]
        self.history_sparkline.set_values(values)

        first = values[0]
        last = values[-1]
        mn = min(values)
        mx = max(values)
        ch = last - first
        ch_pct = (ch / first * 100.0) if abs(first) > 1e-9 else 0.0

        stats = f"{self._t('history_change')}: {ch_pct:+.2f}%   •   {self._t('history_min')}: {CurrencyCardWidget._format_price(mn)}   •   {self._t('history_max')}: {CurrencyCardWidget._format_price(mx)}"
        self.history_stats_label.configure(text=stats)

    def _history_live_append(self) -> None:
        """Append the latest point for the selected symbol and redraw quickly."""
        sym = str(self._history_symbol or "").upper().strip()
        if not sym or sym not in self.currencies:
            return
        data = self.currencies.get(sym, {})
        try:
            price = float(data.get("price", 0) or 0)
        except Exception:
            return
        if price <= 0:
            return
        self._history_points.append((time.time(), float(price)))
        self._update_history_chart()

    # ----- Converter -----


    def _record_history_snapshots(self) -> None:
        """Persist snapshots to SQLite (fast, async)."""
        now = time.time()

        watch: Set[str] = set()
        try:
            watch.update([str(s).upper().strip() for s in self.featured_symbols])
            watch.update([str(s).upper().strip() for s in self.user_portfolio])
        except Exception:
            pass

        # Ensure converter + selected history symbol work well
        watch.add("USD")
        try:
            if self._history_symbol:
                watch.add(str(self._history_symbol).upper().strip())
        except Exception:
            pass

        rows: List[Tuple[str, float, float]] = []
        for sym in watch:
            d = self.currencies.get(sym)
            if not d:
                continue
            try:
                price = float(d.get("price", 0) or 0)
            except Exception:
                continue
            if price <= 0:
                continue
            rows.append((sym, float(now), float(price)))

        if rows:
            try:
                self.executor.submit(db_manager.insert_price_history_bulk, rows)
            except Exception:
                pass

        # Prune occasionally (every ~6 hours)
        try:
            if now - float(getattr(self, "_last_history_prune", 0.0)) > 6 * 3600:
                self._last_history_prune = float(now)
                self.executor.submit(db_manager.prune_price_history, int(config.HISTORY_RETENTION_DAYS))
        except Exception:
            pass

    def _create_converter_section(self, parent: Optional[ctk.CTkBaseClass] = None) -> None:
        target = parent if parent is not None else self.scroll_frame
        card = self._create_glass_card(target, glass_level=2)
        if parent is None:
            row = self._next_row()
            card.grid(row=row, column=0, sticky="ew", pady=(0, 20))
        else:
            card.pack(fill="both", expand=True)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=18)

        title = ctk.CTkLabel(
            content,
            text=self._t("section_converter"),
            font=self._ui_font(18, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        title.pack(fill="x")
        self.converter_title_label = title

        rowf = ctk.CTkFrame(content, fg_color="transparent")
        rowf.pack(fill="x", pady=(12, 0))
        rowf.grid_columnconfigure((0, 1, 2), weight=1)

        # Amount
        amount_block = ctk.CTkFrame(rowf, fg_color="transparent")
        amount_block.grid(row=0, column=0, sticky="ew", padx=(0, 12) if not self.rtl else (12, 0))

        amount_label = ctk.CTkLabel(
            amount_block,
            text=self._t("converter_amount"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        amount_label.pack(fill="x")

        self.converter_amount_var = ctk.StringVar(value="1")
        amount_entry = ctk.CTkEntry(
            amount_block,
            textvariable=self.converter_amount_var,
            height=36,
            corner_radius=10,
            fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            font=self._ui_font(13, False),
            justify="right" if self.rtl else "left",
        )
        amount_entry.pack(fill="x", pady=(6, 0))
        self._add_entry_context_menu(amount_entry)
        try:
            self.converter_amount_var.trace_add("write", lambda *args: self._update_converter_result())
        except Exception:
            pass

        # From
        from_block = ctk.CTkFrame(rowf, fg_color="transparent")
        from_block.grid(row=0, column=1, sticky="ew", padx=12)

        from_label = ctk.CTkLabel(
            from_block,
            text=self._t("converter_from"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        from_label.pack(fill="x")

        self.converter_from_var = ctk.StringVar(value="USD")
        self.converter_from_btn = self._create_button(
            from_block,
            text=self.converter_from_var.get(),
            command=lambda: self._toggle_converter_inline_picker("from"),
            style="secondary",
            width=220,
        )
        self.converter_from_btn.pack(fill="x", pady=(6, 0))
        try:
            self.converter_from_var.trace_add("write", lambda *_: self._sync_converter_button_text("from"))
        except Exception:
            pass

        # To
        to_block = ctk.CTkFrame(rowf, fg_color="transparent")
        to_block.grid(row=0, column=2, sticky="ew")

        to_label = ctk.CTkLabel(
            to_block,
            text=self._t("converter_to"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        to_label.pack(fill="x")

        self.converter_to_var = ctk.StringVar(value="EUR")
        self.converter_to_btn = self._create_button(
            to_block,
            text=self.converter_to_var.get(),
            command=lambda: self._toggle_converter_inline_picker("to"),
            style="secondary",
            width=220,
        )
        self.converter_to_btn.pack(fill="x", pady=(6, 0))
        try:
            self.converter_to_var.trace_add("write", lambda *_: self._sync_converter_button_text("to"))
        except Exception:
            pass

        self.converter_result_label = ctk.CTkLabel(
            content,
            text="—",
            font=self._ui_font(16, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.converter_result_label.pack(fill="x", pady=(12, 0))

        # Embedded currency picker (replaces the old nested popup) — hidden
        # until a From/To button is clicked, then expands in place.
        self.converter_inline_picker_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._converter_picker_target = None
        self._converter_picker_search_var = ctk.StringVar(value="")
        self._converter_picker_trace_id: Optional[str] = None

        # Menu values are filled in once the first data load completes
        self.after(100, lambda: self._refresh_symbol_menus(force=True))

    def _sync_converter_button_text(self, which: str) -> None:
        try:
            if which == "from" and self.converter_from_btn is not None:
                self.converter_from_btn.configure(text=self.converter_from_var.get())
            elif which == "to" and self.converter_to_btn is not None:
                self.converter_to_btn.configure(text=self.converter_to_var.get())
        except Exception:
            pass

    def _toggle_converter_inline_picker(self, which: str) -> None:
        frame = self.converter_inline_picker_frame
        if frame is None or not frame.winfo_exists():
            return

        if self._converter_picker_target == which and frame.winfo_ismapped():
            frame.pack_forget()
            self._converter_picker_target = None
            return

        self._converter_picker_target = which
        for child in list(frame.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        var = self.converter_from_var if which == "from" else self.converter_to_var
        current_disp = var.get() if var is not None else ""

        search_var = self._converter_picker_search_var
        if self._converter_picker_trace_id is not None:
            try:
                search_var.trace_remove("write", self._converter_picker_trace_id)
            except Exception:
                pass
            self._converter_picker_trace_id = None
        search_var.set("")
        search_entry = ctk.CTkEntry(
            frame,
            textvariable=search_var,
            placeholder_text=self._t("placeholder_search"),
            height=34,
            corner_radius=10,
            fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            font=self._ui_font(13, False),
            justify="right" if self.rtl else "left",
        )
        search_entry.pack(fill="x", pady=(10, 6))
        self._add_entry_context_menu(search_entry)

        list_holder = ctk.CTkScrollableFrame(frame, fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark), height=200, corner_radius=10)
        list_holder.pack(fill="x")

        options: List[Tuple[str, str]] = [(sym, disp) for disp, sym in self._converter_symbol_map.items()]
        options.sort(key=lambda t: t[1].lower())

        def choose(disp: str) -> None:
            var.set(disp)
            self._update_converter_result()
            frame.pack_forget()
            self._converter_picker_target = None

        def rebuild(*_args) -> None:
            for child in list(list_holder.winfo_children()):
                try:
                    child.destroy()
                except Exception:
                    pass
            term = search_var.get().strip().lower()
            shown = 0
            for sym, disp in options:
                if term and term not in disp.lower() and term not in sym.lower():
                    continue
                is_current = disp == current_disp
                btn = ctk.CTkButton(
                    list_holder,
                    text=disp,
                    anchor="e" if self.rtl else "w",
                    height=32,
                    corner_radius=8,
                    fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue) if is_current else "transparent",
                    hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover) if is_current else (theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                    text_color="white" if is_current else (theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                    font=self._ui_font(12, False),
                    command=lambda d=disp: choose(d),
                )
                btn.pack(fill="x", pady=1)
                shown += 1
                if shown >= 300:
                    break

        self._converter_picker_trace_id = search_var.trace_add("write", rebuild)
        rebuild()

        frame.pack(fill="x", pady=(12, 0))
        try:
            search_entry.focus_set()
        except Exception:
            pass


    def _usd_toman_rate(self) -> Optional[float]:
        d = self.currencies.get("USD")
        if not d:
            return None
        try:
            unit = str(d.get("unit", "")).lower()
            price = float(d.get("price", 0) or 0)
        except Exception:
            return None
        if price <= 0:
            return None
        # If USD itself is already in toman/rial, treat it as toman
        if "ریال" in unit and "تومان" not in unit:
            return price / 10.0
        return price

    def _value_in_toman(self, sym: str) -> Optional[float]:
        s = str(sym or "").upper().strip()
        if s == "TOMAN":
            return 1.0
        if s == "USDT" and self.app_mode == "crypto":
            # Crypto mode's explicit conversion basis: 1 USDT = the Tetherland
            # rate, in Toman. Same source the price-basis toggle uses, so
            # converter results stay consistent with what the cards show.
            return self._tether_irr_rate

        data = self.currencies.get(s)
        if not data:
            return None

        try:
            price = float(data.get("price", 0) or 0)
        except Exception:
            return None
        if price <= 0:
            return None

        unit = str(data.get("unit", "")).lower()

        # Toman / Rial
        if "تومان" in unit or "toman" in unit:
            return price
        if "ریال" in unit or "rial" in unit:
            return price / 10.0

        # Assume USD-priced
        usd_toman = self._usd_toman_rate()
        if usd_toman is None:
            return None
        return price * usd_toman

    def _update_converter_result(self) -> None:
        if self.converter_result_label is None:
            return

        try:
            amount_raw = (self.converter_amount_var.get() if self.converter_amount_var is not None else "1").strip()
            amount_raw = amount_raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
            amount_raw = amount_raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
            amount = float(amount_raw)
        except Exception:
            self.converter_result_label.configure(text="—")
            return

        from_sym = self._display_to_symbol_value(self.converter_from_var.get() if self.converter_from_var is not None else "USD")
        to_sym = self._display_to_symbol_value(self.converter_to_var.get() if self.converter_to_var is not None else "EUR")

        v_from = self._value_in_toman(from_sym)
        v_to = self._value_in_toman(to_sym)

        if v_from is None or v_to is None or v_to == 0:
            self.converter_result_label.configure(text=self._t("converter_need_usd"))
            return

        out = amount * v_from / v_to

        # Pretty output
        out_s = CurrencyCardWidget._format_price(out)
        self.converter_result_label.configure(text=f"{out_s}  →  {to_sym}")


# ==========================================================================
# DesktopWidgetsSectionMixin
# ==========================================================================

class DesktopWidgetsSectionMixin:
    """Featured/Insights grids + the Widgets section. Composed onto MainWindow."""


    # ----- Widgets -----

    def _widget_type_options(self) -> Tuple[List[str], Dict[str, str]]:
        opts = [
            ("widget_type_price", "price"),
            ("widget_type_movers", "movers"),
            ("widget_type_portfolio", "portfolio"),
        ]
        values = [self._t(k) for k, _ in opts]
        mapping = {self._t(k): t for k, t in opts}
        return values, mapping

    def _widget_theme_options(self) -> Tuple[List[str], Dict[str, str]]:
        opts = [
            ("widget_theme_auto", "auto"),
            ("theme_liquid_glass", "liquid_glass"),
            ("theme_crystal", "crystal"),
            ("theme_paper", "paper"),
            ("theme_paper_noir", "paper_noir"),
        ]
        values = [self._t(k) for k, _ in opts]
        mapping = {self._t(k): key for k, key in opts}
        return values, mapping

    def _on_widget_theme_changed(self, _selection: Optional[str] = None) -> None:
        try:
            display = self.widget_theme_var.get() if self.widget_theme_var is not None else ""
            self.widget_theme = self._widget_theme_map.get(display, "auto")
            db_manager.save_preference("widget_theme", self.widget_theme)
            self.widget_manager.apply_typography()
        except Exception:
            pass

    def _create_widgets_section(self, parent: Optional[ctk.CTkBaseClass] = None) -> None:
        target = parent if parent is not None else self.scroll_frame
        card = self._create_glass_card(target, glass_level=2)
        if parent is None:
            row = self._next_row()
            card.grid(row=row, column=0, sticky="ew", pady=(0, 20))
        else:
            card.pack(fill="both", expand=True)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=18)

        title = ctk.CTkLabel(
            content,
            text=self._t("section_widgets"),
            font=self._ui_font(18, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        title.pack(fill="x")
        self.widgets_title_label = title

        theme_lbl = ctk.CTkLabel(
            content,
            text=self._t("widget_theme_label"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        theme_lbl.pack(fill="x", pady=(10, 0))

        theme_values, self._widget_theme_map = self._widget_theme_options()
        rev_theme_map = {v: k for k, v in self._widget_theme_map.items()}
        current_theme_disp = rev_theme_map.get(getattr(self, "widget_theme", "auto"), theme_values[0])
        self.widget_theme_var = ctk.StringVar(value=current_theme_disp)
        self.widget_theme_menu = ctk.CTkOptionMenu(
            content,
            variable=self.widget_theme_var,
            values=theme_values,
            width=220,
            height=36,
            corner_radius=10,
            fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            button_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            button_hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            dropdown_fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            dropdown_text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            font=self._ui_font(13, False),
            command=self._on_widget_theme_changed,
        )
        self.widget_theme_menu.pack(fill="x", pady=(6, 0), anchor="e" if self.rtl else "w")

        add_title = ctk.CTkLabel(
            content,
            text=self._t("widgets_add_title"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        add_title.pack(fill="x", pady=(10, 0))

        rowf = ctk.CTkFrame(content, fg_color="transparent")
        rowf.pack(fill="x", pady=(8, 0))
        rowf.grid_columnconfigure((0, 1, 2), weight=1)

        # Type
        type_block = ctk.CTkFrame(rowf, fg_color="transparent")
        type_block.grid(row=0, column=0, sticky="ew", padx=(0, 12) if not self.rtl else (12, 0))

        type_lbl = ctk.CTkLabel(
            type_block,
            text=self._t("widgets_type"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        type_lbl.pack(fill="x")

        type_values, self._widget_type_map = self._widget_type_options()
        self.widgets_type_var = ctk.StringVar(value=type_values[0])
        self.widgets_type_menu = ctk.CTkOptionMenu(
            type_block,
            variable=self.widgets_type_var,
            values=type_values,
            width=220,
            height=36,
            corner_radius=10,
            fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            button_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            button_hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            dropdown_fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            dropdown_text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            font=self._ui_font(13, False),
            command=lambda _: self._on_widget_type_changed(),
        )
        self.widgets_type_menu.pack(fill="x", pady=(6, 0))

        # Symbol (only for price widget) -- inline searchable picker, same
        # pattern as the Converter section's From/To pickers.
        sym_block = ctk.CTkFrame(rowf, fg_color="transparent")
        sym_block.grid(row=0, column=1, sticky="ew", padx=12)

        sym_lbl = ctk.CTkLabel(
            sym_block,
            text=self._t("widgets_symbol"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        sym_lbl.pack(fill="x")

        self.widgets_symbol_var = ctk.StringVar(value=self._symbol_to_display("USD"))
        self.widgets_symbol_menu = None  # unused now
        self.widgets_symbol_btn = self._create_button(
            sym_block,
            text=self.widgets_symbol_var.get(),
            command=self._toggle_widgets_inline_picker,
            style="secondary",
            width=220,
        )
        self.widgets_symbol_btn.pack(fill="x", pady=(6, 0))
        try:
            self.widgets_symbol_var.trace_add("write", lambda *_: self._sync_widgets_symbol_button_text())
        except Exception:
            pass

        # Add button
        btn_block = ctk.CTkFrame(rowf, fg_color="transparent")
        btn_block.grid(row=0, column=2, sticky="ew")

        btn_dummy = ctk.CTkLabel(btn_block, text="", fg_color="transparent")
        btn_dummy.pack(fill="x")  # spacing line

        add_btn = self._create_button(
            btn_block,
            text=self._t("btn_add_widget"),
            command=self._add_desktop_widget,
            style="primary",
            width=180,
        )
        add_btn.pack(anchor="e" if self.rtl else "w", pady=(6, 0))

        # Hidden until the symbol button is clicked, then expands in place.
        self.widgets_inline_picker_frame = ctk.CTkFrame(content, fg_color="transparent")

        # Active list
        active_title = ctk.CTkLabel(
            content,
            text=self._t("widgets_active_title"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        active_title.pack(fill="x", pady=(16, 0))

        self.widgets_active_list = ctk.CTkFrame(content, fg_color="transparent")
        self.widgets_active_list.pack(fill="x", pady=(8, 0))

        self._refresh_widgets_ui()
        self.after(100, lambda: self._refresh_symbol_menus(force=True))

    def _on_widget_type_changed(self) -> None:
        # Disable the symbol picker for non-price widgets
        try:
            t_disp = self.widgets_type_var.get() if self.widgets_type_var is not None else ""
            t = self._widget_type_map.get(t_disp, "price")
            if getattr(self, "widgets_symbol_btn", None) is None:
                return
            if t == "price":
                self.widgets_symbol_btn.configure(state="normal")
            else:
                self.widgets_symbol_btn.configure(state="disabled")
                # Collapse the inline picker too, if it happened to be open
                # for a widget type that no longer has a symbol to pick.
                try:
                    frame = self.widgets_inline_picker_frame
                    if frame is not None and frame.winfo_ismapped():
                        frame.pack_forget()
                except Exception:
                    pass
        except Exception:
            pass

    def _sync_widgets_symbol_button_text(self) -> None:
        try:
            if getattr(self, "widgets_symbol_btn", None) is not None:
                self.widgets_symbol_btn.configure(text=self.widgets_symbol_var.get())
        except Exception:
            pass

    def _toggle_widgets_inline_picker(self) -> None:
        """Same pattern as _toggle_converter_inline_picker, bound to
        widgets_symbol_var instead."""
        frame = self.widgets_inline_picker_frame
        if frame is None or not frame.winfo_exists():
            return

        if frame.winfo_ismapped():
            frame.pack_forget()
            return

        for child in list(frame.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        var = self.widgets_symbol_var
        current_disp = var.get() if var is not None else ""

        if self._widgets_picker_search_var is None:
            self._widgets_picker_search_var = ctk.StringVar(value="")
        search_var = self._widgets_picker_search_var
        if self._widgets_picker_trace_id is not None:
            try:
                search_var.trace_remove("write", self._widgets_picker_trace_id)
            except Exception:
                pass
            self._widgets_picker_trace_id = None
        search_var.set("")

        search_entry = ctk.CTkEntry(
            frame,
            textvariable=search_var,
            placeholder_text=self._t("placeholder_search"),
            height=34,
            corner_radius=10,
            fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            font=self._ui_font(13, False),
            justify="right" if self.rtl else "left",
        )
        search_entry.pack(fill="x", pady=(10, 6))
        self._add_entry_context_menu(search_entry)

        list_holder = ctk.CTkScrollableFrame(frame, fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark), height=200, corner_radius=10)
        list_holder.pack(fill="x")

        # No TOMAN here -- a pseudo-unit only the Converter needs.
        options: List[Tuple[str, str]] = [(sym, disp) for disp, sym in self._converter_symbol_map.items() if sym != "TOMAN"]
        options.sort(key=lambda t: t[1].lower())

        def choose(disp: str) -> None:
            var.set(disp)  # triggers _sync_widgets_symbol_button_text via the trace
            frame.pack_forget()

        def rebuild(*_args) -> None:
            for child in list(list_holder.winfo_children()):
                try:
                    child.destroy()
                except Exception:
                    pass
            term = search_var.get().strip().lower()
            shown = 0
            for sym, disp in options:
                if term and term not in disp.lower() and term not in sym.lower():
                    continue
                is_current = disp == current_disp
                btn = ctk.CTkButton(
                    list_holder,
                    text=disp,
                    anchor="e" if self.rtl else "w",
                    height=32,
                    corner_radius=8,
                    fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue) if is_current else "transparent",
                    hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover) if is_current else (theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                    text_color="white" if is_current else (theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                    font=self._ui_font(12, False),
                    command=lambda d=disp: choose(d),
                )
                btn.pack(fill="x", pady=1)
                shown += 1
                if shown >= 300:
                    break

        self._widgets_picker_trace_id = search_var.trace_add("write", rebuild)
        rebuild()

        frame.pack(fill="x", pady=(10, 0))
        try:
            search_entry.focus_set()
        except Exception:
            pass

    def _add_desktop_widget(self) -> None:
        try:
            t_disp = self.widgets_type_var.get() if self.widgets_type_var is not None else ""
            w_type = self._widget_type_map.get(t_disp, "price")

            sym = "USD"
            if w_type == "price":
                sym = self._display_to_symbol_value(self.widgets_symbol_var.get() if self.widgets_symbol_var is not None else "USD")

            self.widget_manager.add(w_type, sym)
            self._refresh_widgets_ui()
        except Exception as e:
            logger.warning(f"Add desktop widget failed: {e}")

    def _refresh_widgets_ui(self) -> None:
        if self.widgets_active_list is None:
            return

        for child in list(self.widgets_active_list.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        items = list(self.widget_manager.widgets.items())
        if not items:
            empty = ctk.CTkLabel(
                self.widgets_active_list,
                text="—",
                font=self._ui_font(12, False),
                text_color=(theme_manager.colors.text_tertiary_light, theme_manager.colors.text_tertiary_dark),
                anchor="e" if self.rtl else "w",
            )
            empty.pack(fill="x")
            return

        for wid, win in items:
            row = ctk.CTkFrame(self.widgets_active_list, fg_color="transparent")
            row.pack(fill="x", pady=4)

            label_text = wid
            try:
                if win.cfg.widget_type == "price":
                    label_text = f"{wid} • {win.cfg.symbol}"
                elif win.cfg.widget_type == "movers":
                    label_text = f"{wid} • {self._t('widget_type_movers')}"
                elif win.cfg.widget_type == "portfolio":
                    label_text = f"{wid} • {self._t('widget_type_portfolio')}"
                else:
                    label_text = f"{wid} • {win.cfg.widget_type}"
            except Exception:
                pass

            lbl = ctk.CTkLabel(
                row,
                text=label_text,
                font=self._ui_font(12, False),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                anchor="e" if self.rtl else "w",
            )
            lbl.pack(side="right" if self.rtl else "left", fill="x", expand=True)

            btn = self._create_button(
                row,
                text=self._t("btn_remove_widget"),
                command=lambda _wid=wid: self.widget_manager.remove(_wid),
                style="secondary",
                width=100,
            )
            btn.pack(side="left" if self.rtl else "right")


    def _create_portfolio_section(self) -> None:
        # Header + compact action buttons + portfolio cards
        row = self._next_row(2)

        header = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        header.grid(row=row, column=0, sticky="ew", pady=(0, 8))

        title_col = 1 if self.rtl else 0
        actions_col = 0 if self.rtl else 1
        header.grid_columnconfigure(title_col, weight=1)
        header.grid_columnconfigure(actions_col, weight=0)

        self.portfolio_title_label = ctk.CTkLabel(
            header,
            text=self._t("section_portfolio"),
            font=self._ui_font(24, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.portfolio_title_label.grid(row=0, column=title_col, sticky="ew")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=actions_col, sticky="w" if self.rtl else "e")

        sort_controls = self._create_portfolio_sort_controls(actions)
        sort_controls.pack(side="right" if self.rtl else "left", padx=(8, 0) if self.rtl else (0, 8))

        self.portfolio_add_btn = self._create_button(
            actions,
            text=self._t("portfolio_add_title"),
            command=self._open_portfolio_currency_picker,
            style="primary",
            width=150,
        )
        self.portfolio_add_btn.pack(side="right" if self.rtl else "left")

        # Search: a slightly larger icon-style button that reveals a compact,
        # proportionally sized field right next to it — not a full-width row.
        self.portfolio_search_toggle_btn = self._create_button(
            actions,
            text="🔍",
            command=self._toggle_portfolio_search,
            style="secondary",
            width=44,
        )
        self.portfolio_search_toggle_btn.configure(height=40, font=self._ui_font(15, False))
        self.portfolio_search_toggle_btn.pack(side="right" if self.rtl else "left", padx=(8, 8) if self.rtl else (8, 8))

        # Quick filter (doesn't affect saved portfolio; only filters the view).
        # Hidden by default, toggled on via the search button; sized to fit
        # its content rather than spanning the whole header.
        self.portfolio_filter_var = ctk.StringVar(value="")
        self.portfolio_filter_entry = ctk.CTkEntry(
            actions,
            textvariable=self.portfolio_filter_var,
            placeholder_text=self._t("placeholder_portfolio_filter"),
            width=170,
            height=40,
            corner_radius=10,
            fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            font=self._ui_font(12, False),
            justify="right" if self.rtl else "left",
        )
        self._add_entry_context_menu(self.portfolio_filter_entry)
        try:
            self.portfolio_filter_var.trace_add("write", lambda *args: self._debounced_portfolio_filter())
        except Exception:
            pass
        self._portfolio_search_visible = False
        # Not packed yet — _toggle_portfolio_search shows/hides it next to the search button

        self.portfolio_container = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        self.portfolio_container.grid(row=row + 1, column=0, sticky="ew", pady=(0, 26))
        for i in range(8):
            self.portfolio_container.grid_columnconfigure(i, weight=1 if i < self.grid_columns else 0)

    def _toggle_portfolio_search(self) -> None:
        try:
            if self.portfolio_filter_entry is None or not self.portfolio_filter_entry.winfo_exists():
                return
            self._portfolio_search_visible = not self._portfolio_search_visible
            if self._portfolio_search_visible:
                self.portfolio_filter_entry.pack(
                    side="right" if self.rtl else "left",
                    padx=(8, 0) if self.rtl else (0, 8),
                    before=self.portfolio_search_toggle_btn,
                )
                self.portfolio_filter_entry.focus_set()
            else:
                self.portfolio_filter_entry.pack_forget()
                self.portfolio_filter_var.set("")
        except Exception:
            pass

    def _regrid_add_currency_panel(self) -> None:
        """No longer needed — the old inline Add panel was replaced by a
        compact button + popup. Kept as a safe no-op since other refresh
        paths still call it."""
        return

    def _add_currency_to_portfolio(self, sym: str) -> bool:
        """Add a currency directly by its ticker symbol (used by the
        Add-to-Portfolio popup, which adds immediately on click rather than
        requiring a separate Add button)."""
        sym = str(sym or "").upper().strip()
        if not sym:
            return False
        if sym in self.currencies and sym not in self.user_portfolio:
            self.user_portfolio.add(sym)
            db_manager.save_selected_currencies(self.user_portfolio, mode=self.app_mode)
            self._render_portfolio_cards()
            self.toasts.show(self._t("toast_added", sym=sym), duration=1500)
            return True
        return False


    def _create_portfolio_sort_controls(self, parent: ctk.CTkBaseClass) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent,
            fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
            corner_radius=12,
            border_width=1,
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            height=50,
        )
        frame.pack_propagate(False)

        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=8)

        self.sort_label = ctk.CTkLabel(
            content,
            text=self._t("sort"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
        )
        self.sort_label.pack(side="left", padx=(0, 8))

        self.portfolio_sort_var = ctk.StringVar(value=self._sort_key_to_display(self.portfolio_sort_mode_key))

        self.portfolio_sort_menu = ctk.CTkOptionMenu(
            content,
            variable=self.portfolio_sort_var,
            values=self._get_sort_display_values(),
            command=self._on_portfolio_sort_changed,
            width=135,
            height=34,
            corner_radius=8,
            fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            button_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            button_hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            dropdown_fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            dropdown_text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            font=self._ui_font(13, False),
        )
        self.portfolio_sort_menu.pack(side="left")

        return frame


    def _create_controls_section(self, parent: Optional[ctk.CTkBaseClass] = None) -> None:
        target = parent if parent is not None else self.scroll_frame
        card = self._create_glass_card(target, height=165, glass_level=2)
        if parent is None:
            row = self._next_row()
            card.grid(row=row, column=0, sticky="ew", pady=(0, 20))
        else:
            card.pack(fill="both", expand=True)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=18)

        self.controls_title_label = ctk.CTkLabel(
            content,
            text=self._t("section_controls"),
            font=self._ui_font(18, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.controls_title_label.pack(fill="x")

        btn_row = ctk.CTkFrame(content, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(12, 6))

        self.refresh_btn = self._create_button(btn_row, text=self._t("btn_refresh"), command=self._manual_refresh, style="primary", width=130)
        self.refresh_btn.pack(side="left", padx=(0, 10))

        self.test_btn = self._create_button(btn_row, text=self._t("btn_test_api"), command=self._test_api_connection, style="secondary", width=120)
        self.test_btn.pack(side="left", padx=(0, 10))

        self.export_btn = self._create_button(btn_row, text=self._t("btn_export_csv"), command=self._export_csv, style="secondary", width=130)
        self.export_btn.pack(side="left", padx=(0, 10))

        self.copy_btn = self._create_button(btn_row, text=self._t("btn_copy"), command=self._copy_to_clipboard, style="secondary", width=100)
        self.copy_btn.pack(side="left", padx=(0, 14))

        self.auto_refresh_var = ctk.BooleanVar(value=True)
        self.auto_refresh_checkbox = ctk.CTkCheckBox(
            btn_row,
            text=self._t("auto_refresh"),
            variable=self.auto_refresh_var,
            command=self._toggle_auto_refresh,
            font=self._ui_font(13, False),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
        )
        self.auto_refresh_checkbox.pack(side="left")

        self.last_update_label = ctk.CTkLabel(
            content,
            text=self._t("last_update", time=self.last_update),
            font=self._ui_font(12, False),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.last_update_label.pack(fill="x", pady=(8, 0))


    def _create_settings_section(self, parent: Optional[ctk.CTkBaseClass] = None) -> None:
        target = parent if parent is not None else self.scroll_frame
        # Let the card size itself (avoids cramped/overlapping controls)
        card = self._create_glass_card(target, glass_level=2)
        if parent is None:
            row = self._next_row()
            card.grid(row=row, column=0, sticky="ew", pady=(0, 20))
        else:
            card.pack(fill="both", expand=True)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=18)

        self.settings_title_label = ctk.CTkLabel(
            content,
            text=self._t("section_settings"),
            font=self._ui_font(18, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.settings_title_label.pack(fill="x")

        # Row 1: language + window options
        top = ctk.CTkFrame(content, fg_color="transparent")
        top.pack(fill="x", pady=(12, 0))
        top.grid_columnconfigure((0, 1), weight=1, uniform="settings_row1")

        # Language (moved into settings) — takes the space the removed
        # auto-refresh control used to occupy.
        lang_block = ctk.CTkFrame(top, fg_color="transparent")
        lang_block.grid(row=0, column=0, sticky="ew", padx=(0, 14) if not self.rtl else (14, 0))

        self.language_setting_label = ctk.CTkLabel(
            lang_block,
            text=self._t("language_label"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.language_setting_label.pack(fill="x")

        self.language_var = ctk.StringVar(value=self._language_display(self.language))
        self.language_menu = ctk.CTkOptionMenu(
            lang_block,
            variable=self.language_var,
            values=self._language_menu_values(),
            height=36,
            corner_radius=10,
            fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            button_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            button_hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            dropdown_fg_color=(theme_manager.colors.glass_light, theme_manager.colors.glass_dark),
            dropdown_text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            font=self._ui_font(13, False),
            command=self._on_language_changed,
        )
        self.language_menu.pack(fill="x", pady=(6, 0))
        try:
            self.language_menu.configure(dropdown_font=self._ui_font(13, False))
        except Exception:
            pass

        # Window options
        window_block = ctk.CTkFrame(top, fg_color="transparent")
        window_block.grid(row=0, column=1, sticky="ew")

        self.window_options_label = ctk.CTkLabel(
            window_block,
            text=self._t("window_options"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.window_options_label.pack(fill="x")

        self.always_on_top_var = ctk.BooleanVar(value=self.always_on_top)
        self.always_on_top_cb = ctk.CTkCheckBox(
            window_block,
            text=self._t("always_on_top"),
            variable=self.always_on_top_var,
            command=self._on_always_on_top_toggle,
            font=self._ui_font(13, False),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
        )
        self.always_on_top_cb.pack(anchor="e" if self.rtl else "w", pady=(6, 0))

        self.background_var = ctk.BooleanVar(value=self.run_in_background)
        self.background_cb = ctk.CTkCheckBox(
            window_block,
            text=self._t("run_in_background"),
            variable=self.background_var,
            command=self._on_background_toggle,
            font=self._ui_font(13, False),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
        )
        self.background_cb.pack(anchor="e" if self.rtl else "w", pady=(8, 0))

        # Row 2: alerts (full width)
        alerts_block = ctk.CTkFrame(content, fg_color="transparent")
        alerts_block.pack(fill="x", pady=(16, 0))

        self.alerts_title_label = ctk.CTkLabel(
            alerts_block,
            text=self._t("alerts_title"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.alerts_title_label.pack(fill="x")

        self.alerts_var = ctk.BooleanVar(value=self.alerts_enabled)
        self.alerts_cb = ctk.CTkCheckBox(
            alerts_block,
            text=self._t("enable_alerts"),
            variable=self.alerts_var,
            command=self._on_alerts_toggle,
            font=self._ui_font(13, False),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            fg_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
            hover_color=(theme_manager.colors.accent_blue_hover, theme_manager.colors.accent_blue_hover),
            border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
        )
        self.alerts_cb.pack(anchor="e" if self.rtl else "w", pady=(6, 0))

        self.alert_threshold_label = ctk.CTkLabel(
            alerts_block,
            text=self._t("threshold", value=float(self.alert_threshold_percent)),
            font=self._ui_font(12, False),
            text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.alert_threshold_label.pack(fill="x", pady=(10, 0))

        self.alert_threshold_slider = ctk.CTkSlider(
            alerts_block,
            from_=0.5,
            to=10.0,
            number_of_steps=95,
            command=self._on_threshold_changed,
        )
        self.alert_threshold_slider.set(self.alert_threshold_percent)
        self.alert_threshold_slider.pack(fill="x", pady=(6, 0))

        # Row 3: tools
        tools_block = ctk.CTkFrame(content, fg_color="transparent")
        tools_block.pack(fill="x", pady=(16, 0))

        self.tools_title_label = ctk.CTkLabel(
            tools_block,
            text=self._t("tools"),
            font=self._ui_font(12, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        self.tools_title_label.pack(fill="x")

        tools_row = ctk.CTkFrame(tools_block, fg_color="transparent")
        tools_row.pack(anchor="e" if self.rtl else "w", pady=(8, 0))

        self.clear_cache_btn = self._create_button(tools_row, text=self._t("btn_clear_cache"), command=self._clear_cache, style="secondary", width=160)
        self.perf_btn = self._create_button(tools_row, text=self._t("btn_performance"), command=self._show_performance_report, style="secondary", width=140)
        self.layout_btn = self._create_button(
            tools_row,
            text=("🧩 چیدمان" if self.language == "fa" else "🧩 Layout"),
            command=self._open_layout_popup,
            style="secondary",
            width=140,
        )

        if self.rtl:
            self.layout_btn.pack(side="left", padx=(0, 10))
            self.perf_btn.pack(side="left", padx=(0, 10))
            self.clear_cache_btn.pack(side="left")
        else:
            self.clear_cache_btn.pack(side="left", padx=(0, 10))
            self.perf_btn.pack(side="left", padx=(0, 10))
            self.layout_btn.pack(side="left")

    def _create_theme_section(self, parent: Optional[ctk.CTkBaseClass] = None) -> None:
        target = parent if parent is not None else self.scroll_frame
        card = self._create_glass_card(target)
        if parent is None:
            row = self._next_row()
            card.grid(row=row, column=0, sticky="ew", pady=(0, 20))
        else:
            card.pack(fill="both", expand=True)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=18)

        title = ctk.CTkLabel(
            content,
            text=self._t("section_theme"),
            font=self._ui_font(18, True),
            text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
            anchor="e" if self.rtl else "w",
        )
        title.pack(fill="x")

        themes = [
            ("liquid_glass", self._t("theme_liquid_glass")),
            ("crystal", self._t("theme_crystal")),
            ("paper", self._t("theme_paper")),
            ("paper_noir", self._t("theme_paper_noir")),
        ]

        button_grid = ctk.CTkFrame(content, fg_color="transparent")
        button_grid.pack(fill="x", pady=(14, 0))
        button_grid.grid_columnconfigure((0, 1), weight=1)

        self.theme_buttons = {}

        for i, (key, label) in enumerate(themes):
            r = i // 2
            c = i % 2

            # RTL-safe column mirroring (prevents negative column index)
            if self.rtl:
                c = 1 - c

            # Absolute safety clamp (never allow negative column)
            c = max(0, c)

            btn = self._create_button(
                button_grid,
                text=label,
                command=lambda k=key: self._apply_theme_with_feedback(k),
                style="secondary",
                width=220,
            )
            btn.grid(row=r, column=c, sticky="ew", padx=6, pady=6)
            self.theme_buttons[key] = btn

        self._update_theme_button_states(self.selected_theme)


    def _render_featured_cards(self) -> None:
        if self.featured_container is None or not self.featured_container.winfo_exists():
            return
        desired = self.featured_symbols[: self.grid_columns]
        desired_set = set(desired)

        # Remove unused cards
        for sym in list(self.featured_cards.keys()):
            if sym not in desired_set:
                try:
                    self.featured_cards[sym].destroy()
                except Exception:
                    pass
                self.featured_cards.pop(sym, None)

        # Create/update cards
        for idx, sym in enumerate(desired):
            data = self.currencies.get(sym)
            if not data:
                continue
            card = self.featured_cards.get(sym)
            if card is not None:
                try:
                    if not card.winfo_exists():
                        self.featured_cards.pop(sym, None)
                        card = None
                except Exception:
                    self.featured_cards.pop(sym, None)
                    card = None

            if card is None:
                card = CurrencyCardWidget(self.featured_container, show_remove=False, font_getter=self._ui_font, rtl=self.rtl, on_open_detail=self._open_forward_price_modal)
                self.featured_cards[sym] = card
                card.grid(row=0, column=idx, padx=config.CARD_PADDING, pady=config.CARD_PADDING, sticky="nsew")
            else:
                try:
                    card.grid_configure(row=0, column=idx)
                except Exception:
                    try:
                        card.grid(row=0, column=idx, padx=config.CARD_PADDING, pady=config.CARD_PADDING, sticky="nsew")
                    except Exception:
                        try:
                            self.featured_cards.pop(sym, None)
                            card.destroy()
                        except Exception:
                            pass
                        card = CurrencyCardWidget(self.featured_container, show_remove=False, font_getter=self._ui_font, rtl=self.rtl, on_open_detail=self._open_forward_price_modal)
                        self.featured_cards[sym] = card
                        card.grid(row=0, column=idx, padx=config.CARD_PADDING, pady=config.CARD_PADDING, sticky="nsew")

            try:
                card.update_data(self._display_currency_data(sym, data))
            except Exception:
                pass

        # Fill empty slots (to keep layout stable)
        for idx in range(len(desired), self.grid_columns):
            pass


    def _debounced_portfolio_filter(self) -> None:
        try:
            if self._portfolio_filter_after_id:
                try:
                    self.after_cancel(self._portfolio_filter_after_id)
                except Exception:
                    pass
            self._portfolio_filter_after_id = self.after(220, self._render_portfolio_cards)
        except Exception:
            pass

    def _render_portfolio_cards(self) -> None:
        if self.portfolio_container is None or not self.portfolio_container.winfo_exists():
            return
        # Every currency you explicitly add to your portfolio shows up here —
        # even if it's also currently Featured. Your portfolio is your explicit
        # choice; it shouldn't silently vanish because it happens to overlap
        # with the (rotating) featured picks.
        raw_symbols = [s for s in self.user_portfolio if s in self.currencies]

        # Hide the quick-filter box entirely when there's nothing to filter —
        # showing an empty filter bar above an empty portfolio was wasted space.
        try:
            if self.portfolio_filter_entry is not None and self.portfolio_filter_entry.winfo_exists():
                if not raw_symbols and self._portfolio_search_visible:
                    self._toggle_portfolio_search()
        except Exception:
            pass

        symbols = self._sort_portfolio_symbols(raw_symbols)

        # Apply quick filter (UI-only)
        try:
            ft = (self.portfolio_filter_var.get() if self.portfolio_filter_var is not None else "").strip().lower()
        except Exception:
            ft = ""
        if ft:
            filtered: List[str] = []
            for sym in symbols:
                d = self.currencies.get(sym, {})
                name = self._currency_display_name(sym, d)
                if ft in sym.lower() or (name and ft in str(name).lower()):
                    filtered.append(sym)
            symbols = filtered

        desired_set = set(symbols)

        for sym in list(self.portfolio_cards.keys()):
            if sym not in desired_set:
                try:
                    self.portfolio_cards[sym].destroy()
                except Exception:
                    pass
                self.portfolio_cards.pop(sym, None)

        # Empty state: a real, compact message instead of dead blank space
        try:
            if not symbols:
                if self.portfolio_empty_label is None or not self.portfolio_empty_label.winfo_exists():
                    self.portfolio_empty_label = ctk.CTkLabel(
                        self.portfolio_container,
                        text=self._t("portfolio_empty_filtered") if (raw_symbols and ft) else self._t("portfolio_empty_hint"),
                        font=self._ui_font(13, False),
                        text_color=(theme_manager.colors.text_tertiary_light, theme_manager.colors.text_tertiary_dark),
                        anchor="center",
                        justify="center",
                    )
                self.portfolio_empty_label.configure(
                    text=self._t("portfolio_empty_filtered") if (raw_symbols and ft) else self._t("portfolio_empty_hint")
                )
                self.portfolio_empty_label.grid(row=0, column=0, columnspan=max(1, self.grid_columns), sticky="ew", pady=24)
                return
            elif self.portfolio_empty_label is not None:
                try:
                    self.portfolio_empty_label.grid_remove()
                except Exception:
                    pass
        except Exception:
            pass

        row = 0
        col = 0
        for sym in symbols:
            data = self.currencies.get(sym)
            if not data:
                continue
            card = self.portfolio_cards.get(sym)
            if card is None:
                card = CurrencyCardWidget(self.portfolio_container, on_remove=self._remove_currency, show_remove=True, font_getter=self._ui_font, rtl=self.rtl, on_open_detail=self._open_forward_price_modal)
                self.portfolio_cards[sym] = card
            card.grid(row=row, column=col, padx=config.CARD_PADDING, pady=config.CARD_PADDING, sticky="nsew")
            card.update_data(self._display_currency_data(sym, data))

            col += 1
            if col >= self.grid_columns:
                col = 0
                row += 1

    def _update_currency_selector(self) -> None:
        """No longer needed — Add to Portfolio is a picker popup now, built
        fresh with current data each time it opens. Kept as a safe no-op
        since several refresh paths still call it."""
        return

    def _debounced_update_currency_selector(self) -> None:
        """No longer needed for the same reason as _update_currency_selector."""
        return

    def _update_insights(self) -> None:
        try:
            movers: List[Tuple[float, str]] = []
            for sym, data in self.currencies.items():
                try:
                    ch = float(data.get("change_percent", 0) or 0)
                except Exception:
                    ch = 0.0
                movers.append((ch, sym))

            movers.sort(key=lambda x: x[0], reverse=True)
            top_gainers = [m for m in movers if m[0] > 0][:3]
            top_losers = sorted([m for m in movers if m[0] < 0], key=lambda x: x[0])[:3]

            gain_labels: List[ctk.CTkLabel] = self.ui_elements.get("top_gainers", [])
            loss_labels: List[ctk.CTkLabel] = self.ui_elements.get("top_losers", [])

            for i in range(3):
                if i < len(top_gainers):
                    ch, sym = top_gainers[i]
                    name = self._currency_display_name(sym, self.currencies.get(sym, {}))
                    gain_labels[i].configure(text=f"{sym} • {name} • +{ch:.2f}%")
                else:
                    gain_labels[i].configure(text="—")

                if i < len(top_losers):
                    ch, sym = top_losers[i]
                    name = self._currency_display_name(sym, self.currencies.get(sym, {}))
                    loss_labels[i].configure(text=f"{sym} • {name} • {ch:.2f}%")
                else:
                    loss_labels[i].configure(text="—")
        except Exception:
            pass

    def _update_status_displays(self) -> None:
        # Data status
        try:
            if "data_status" in self.ui_elements:
                if self.connection_status == ConnectionStatus.CONNECTED:
                    quality = self._t("data_quality_excellent")
                    source = self._t("data_source_live")
                elif self.connection_status == ConnectionStatus.CACHED:
                    quality = self._t("data_quality_cached")
                    source = self._t("data_source_db")
                elif self.connection_status == ConnectionStatus.CONNECTING:
                    quality = self._t("data_quality_connecting")
                    source = "—"
                elif self.connection_status == ConnectionStatus.RATE_LIMITED:
                    quality = self._t("data_quality_limited")
                    source = self._t("data_source_live")
                else:
                    quality = self._t("data_quality_limited")
                    source = self._t("data_source_offline")

                suffix = "مورد" if self.language == "fa" else "items"
                self.ui_elements["data_status"]["status_label"].configure(
                    text=f"📊 {quality} • {source} • {len(self.currencies)} {suffix}"
                )
        except Exception:
            pass

        # Effects status
        self._update_effects_status()

        # Last update
        try:
            self.last_update_label.configure(text=self._t("last_update", time=self.last_update))
        except Exception:
            pass


    def _update_connection_status(self, status: ConnectionStatus, message: Optional[str] = None) -> None:
        self.connection_status = status

        if status == ConnectionStatus.CONNECTED:
            color = theme_manager.colors.status_success
            msg = message or self._t("status_connected", count=len(self.currencies))
        elif status == ConnectionStatus.CACHED:
            color = theme_manager.colors.status_warning
            msg = message or self._t("status_cached", count=len(self.currencies))
        elif status == ConnectionStatus.CONNECTING:
            color = theme_manager.colors.status_info
            msg = message or self._t("status_connecting")
        elif status == ConnectionStatus.RATE_LIMITED:
            color = theme_manager.colors.status_warning
            msg = message or self._t("status_rate_limited")
        else:
            color = theme_manager.colors.status_error
            msg = message or self._t("status_error")

        try:
            if "api_status" in self.ui_elements:
                self.ui_elements["api_status"]["status_label"].configure(text=msg, text_color=color)
        except Exception:
            pass


    def _update_effects_status(self) -> None:
        try:
            info = self.effects_manager.get_current_effect_info()
            effect = str(info.get("effect", "normal") or "normal").lower()

            if "liquid" in effect:
                name = self._t("theme_name_liquid_glass")
            elif "crystal" in effect:
                name = self._t("theme_name_crystal")
            else:
                name = "نرمال" if self.language == "fa" else "Normal"

            if "simulation" in effect:
                name += " (شبیه‌سازی)" if self.language == "fa" else " (Simulation)"

            if "effects_status" in self.ui_elements:
                self.ui_elements["effects_status"]["status_label"].configure(text=f"✨ {name}")
        except Exception:
            pass

    def _open_forward_price_modal(self, symbol: str) -> None:
        """Card click handler: opens a themed popup showing either the
        forward ("fardaee") price (fiat/gold, FORWARD_PRICE_ASSETS) or a
        real-time market rate (crypto, CRYPTO_SYMBOLS -- there's no
        "tomorrow" market for crypto, so it gets its own label instead of
        ever being called a forward price). Anything in neither set is a
        silent no-op, styled the same way as every other popup in this
        app (see FabMixin._show_themed_message).
        """
        sym = str(symbol or "").upper().strip()
        is_crypto = sym in CRYPTO_SYMBOLS
        if not sym or (sym not in FORWARD_PRICE_ASSETS and not is_crypto):
            return

        record = dict(self.currencies.get(sym, {})) if isinstance(getattr(self, "currencies", None), dict) else {}
        name = FORWARD_PRICE_ASSETS.get(sym, record.get("name", sym))
        spot_price = record.get("price")
        unit = record.get("unit", "")

        if is_crypto:
            result_label = "نرخ لحظه‌ای بازار (نوبیتکس/تترلند)"
        else:
            result_label = self._t("forward_price_forward")

        try:
            win = ctk.CTkToplevel(self)
            win.title(self._t("forward_price_title"))
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

            head = ctk.CTkLabel(
                card,
                text=f"📈  {name} ({sym})",
                font=self._ui_font(15, True),
                text_color=(theme_manager.colors.accent_blue, theme_manager.colors.accent_blue),
                anchor="e" if self.rtl else "w",
            )
            head.pack(fill="x", padx=20, pady=(18, 6))

            if spot_price is not None:
                spot_row = ctk.CTkLabel(
                    card,
                    text=f"{self._t('forward_price_spot')}: {CurrencyCardWidget._format_price(spot_price)} {unit}".strip(),
                    font=self._ui_font(13, False),
                    text_color=(theme_manager.colors.text_secondary_light, theme_manager.colors.text_secondary_dark),
                    anchor="e" if self.rtl else "w",
                )
                spot_row.pack(fill="x", padx=20, pady=(0, 4))

            result_row = ctk.CTkLabel(
                card,
                text="⏳ در حال ارتباط با هسته معاملات...",
                font=self._ui_font(14, True),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                anchor="e" if self.rtl else "w",
                wraplength=340,
                justify="right" if self.rtl else "left",
            )
            result_row.pack(fill="x", padx=20, pady=(10, 14))

            close_btn = self._create_button(win, text=self._t("btn_close"), command=win.destroy, style="secondary", width=140)
            close_btn.pack(pady=(0, 16))

            win.update_idletasks()
            w, h = max(380, win.winfo_reqwidth()), max(190, win.winfo_reqheight())
            win.geometry(f"{w}x{h}")
            win.minsize(w, h)
        except Exception as e:
            logger.debug(f"Forward price modal failed to open: {e}")
            return

        def worker() -> Tuple[Optional[float], str]:
            try:
                if sym == "USDT":
                    return forward_price_service.get_usdt_irt_rate(), result_label
                if is_crypto:
                    return spot_price, result_label  # already-fetched live spot price; no extra network call needed
                if sym == "USD":
                    price, is_real_farda = forward_price_service.get_usd_forward_price()
                    label = "نرخ فردایی دلار" if is_real_farda else "نرخ لحظه‌ای تتر (جایگزین فردایی)"
                    return price, label
                return forward_price_service.compute_forward_price(sym), result_label
            except Exception as e:
                logger.debug(f"Price fetch failed for {sym}: {e}")
                return None, result_label

        def apply_result(result: Tuple[Optional[float], str]) -> None:
            value, label = result
            try:
                if not result_row.winfo_exists():
                    return
            except Exception:
                return
            if value is None:
                result_row.configure(
                    text="⚠️ دریافت اطلاعات با خطا مواجه شد.",
                    text_color=(theme_manager.colors.status_error, theme_manager.colors.status_error),
                )
            else:
                result_row.configure(
                    text=f"{label}: {CurrencyCardWidget._format_price(value)} تومان",
                )

        try:
            future = self.executor.submit(worker)
        except Exception:
            self._enqueue_ui(lambda: apply_result((None, result_label)))
            return

        def done(fut) -> None:
            try:
                result = fut.result()
            except Exception:
                result = (None, result_label)
            self._enqueue_ui(lambda: apply_result(result))

        future.add_done_callback(done)
