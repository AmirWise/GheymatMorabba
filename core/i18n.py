"""Lightweight i18n: translation table + helpers for English/Persian UI text."""

from __future__ import annotations

from typing import Dict


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "portfolio_items": "Items",
        "best": "Best",
        "worst": "Worst",
        "updated": "Updated",

        # Toolbar / hero
        "toolbar_title": "Gheymat Morabba",
        "btn_add_currency": "➕ Add Currency",
        "language_label": "Language",

        "hero_title": "💎 Gheymat Morabba",
        "hero_subtitle": "Real-time Currency • Crypto • Gold • Portfolio",
        "hero_version": "Version {version} • Cached startup • Smoother UI",

        # Sections
        "section_featured": "📈 Featured Markets",
        "section_insights": "⚡ Market Insights",
        "section_portfolio": "💼 Your Portfolio",
        "section_controls": "🎛️ Data Controls",
        "section_settings": "⚙️ Settings",
        "section_theme": "🎨 Theme",
        "section_history": "📉 Price History",
        "section_converter": "🧮 Converter",
        "section_widgets": "🧩 Desktop Widgets",
        "theme_liquid_glass": "💧 Liquid Glass",
        "theme_crystal": "💎 Crystal",
        "theme_paper": "📄 Paper",
        "theme_paper_noir": "⬛ Paper Noir",
        "theme_name_liquid_glass": "Liquid Glass",
        "theme_name_crystal": "Crystal",
        "theme_name_paper": "Paper",
        "theme_name_paper_noir": "Paper Noir",

        # Insights
        "top_gainers": "Top Gainers",
        "top_losers": "Top Losers",

        # History
        "history_symbol": "Symbol",
        "history_period": "Period",
        "history_loading": "Loading history…",
        "history_no_data": "No history yet",
        "history_change": "Change",
        "history_min": "Min",
        "history_max": "Max",
        "period_1h": "1h",
        "period_6h": "6h",
        "period_24h": "24h",
        "period_7d": "7d",

        # Converter
        "converter_amount": "Amount",
        "converter_from": "From",
        "converter_to": "To",
        "converter_result": "Result",
        "converter_need_usd": "USD price is needed for this conversion",

        # Widgets
        "widgets_add_title": "Add a widget",
        "widgets_active_title": "Active widgets",
        "widgets_type": "Type",
        "widgets_symbol": "Symbol",
        "widget_theme_label": "Widget Theme",
        "widget_theme_auto": "🔄 Auto (match app)",
        "widget_type_price": "Price card",
        "widget_type_movers": "Top movers",
        "widget_type_portfolio": "Portfolio mini",
        "btn_add_widget": "➕ Add Widget",
        "btn_remove_widget": "Remove",
        "toast_widget_added": "🧩 Widget added",
        "toast_widget_removed": "🧹 Widget removed",
        "toast_widget_not_supported": "⚠️ Desktop widgets are supported on Windows only",
        "toast_widget_add_failed": "Could not add widget",
        "widgets_persist_hint": "💡 To keep this widget visible while the app is minimized, enable \"Run in background\" in Settings.",

        # Background
        "run_in_background": "Run in background when closing",
        "toast_background_on": "🟣 Background mode enabled (close = minimize)",
        "toast_background_off": "⚪ Background mode disabled",

        # Controls / settings labels
        "api": "API",
        "data": "Data",
        "effects": "Effects",
        "sort": "Sort:",
        "auto_refresh": "Auto-refresh",
        "last_update": "Last Update: {time}",
        "refresh_interval": "Refresh interval",
        "alerts_title": "Price change alerts",
        "enable_alerts": "Enable alerts",
        "threshold": "Threshold: {value:.1f}%",
        "tools": "Tools",
        "window_options": "Window",
        "always_on_top": "Always on top",

        # Buttons
        "btn_refresh": "🔄 Refresh",
        "btn_test_api": "🧪 Test API",
        "btn_export_csv": "📄 Export CSV",
        "btn_copy": "📋 Copy",
        "btn_clear_cache": "🧹 Clear cache",
        "btn_performance": "📈 Performance",
        "btn_add": "Add",
        "btn_search": "Search",
        "btn_close": "Close",

        # Forward price modal
        "forward_price_title": "Forward Price",
        "forward_price_loading": "Fetching forward price…",
        "forward_price_spot": "Spot price",
        "forward_price_forward": "Forward (tomorrow) price",
        "forward_price_unavailable": "Forward price is unavailable right now.",

        # Placeholders
        "placeholder_search": "Search…",
        "placeholder_portfolio_filter": "Filter portfolio…",
        "portfolio_add_title": "➕ Add to portfolio",

        # Sort modes
        "sort_default": "Default",
        "sort_name": "Name",
        "sort_symbol": "Symbol",
        "sort_price": "Price",
        "sort_change": "Change",

        # Connection messages
        "status_connected": "🟢 Connected • {count} items",
        "status_cached": "🟠 Cached • {count} items",
        "status_connecting": "🔵 Connecting…",
        "status_rate_limited": "🟠 Rate limited",
        "status_error": "🔴 Offline / Error",

        # Data status
        "data_quality_excellent": "Excellent",
        "data_quality_cached": "Cached",
        "data_quality_connecting": "Connecting",
        "data_quality_limited": "Limited",
        "data_source_live": "Live API",
        "data_source_db": "Local DB",
        "data_source_offline": "Fallback/Offline",

        # Toasts / misc
        "toast_updated": "✅ Updated",
        "toast_loaded_cache": "🗃️ Loaded cached data (will refresh online)",
        "toast_added": "✅ Added {sym}",
        "toast_removed": "🗑️ Removed {sym}",
        "toast_interval_set": "⏱️ Interval set to {interval}",
        "toast_autorefresh_on": "▶️ Auto-refresh ON",
        "toast_autorefresh_off": "⏸️ Auto-refresh OFF",
        "toast_alerts_on": "🔔 Alerts ON",
        "toast_alerts_off": "🔕 Alerts OFF",
        "toast_cache_cleared": "🧹 Cache cleared",
        "toast_topmost_on": "📌 Always on top ON",
        "toast_topmost_off": "📌 Always on top OFF",
        "toast_copied": "📋 Copied to clipboard",
        "toast_csv_exported": "📄 CSV exported",
        "toast_refresh_failed": "❌ Could not refresh (offline?)",
        "toast_applying_theme": "🎨 Applying {name}…",
        "toast_price_moved": "{direction} {sym} moved {delta:+.2f}% since last update",
        "status_refreshing": "🔄 Refreshing…",

        # Dialogs / errors
        "dlg_add_currency_title": "Add Currency",
        "no_matches": "No matches",
        "api_test_title": "API Test",
        "api_test_ok": "✅ API Test Successful\n\nResponse time: {elapsed:.2f}s\nItems parsed: {count}\n",
        "api_test_fail": "❌ API Test Failed\n\nNo data received.",
        "export_title": "Export CSV",
        "filetype_csv": "CSV files",
        "filetype_all": "All files",
        "export_failed": "Failed:\n{error}",
        "clear_cache_title": "Clear cache",
        "performance_title": "Performance",
        "critical_error_title": "Critical Error",

        # Floating action menu
        "fab_menu_title": "Quick Access",
        "fab_language": "🌐 Language: {lang_name}",
        "fab_theme": "🎨 Theme: {name}",
        "fab_converter": "🧮 Converter",
        "fab_widgets": "🧩 Desktop Widgets",
        "fab_controls": "🎛️ Data Control",
        "fab_settings": "⚙️ Settings",
        "fab_layout": "📐 Manage Sections",
        "toast_section_revealed": "✅ {name} added to your dashboard — scroll down to view",
        "toast_already_on_dashboard": "{name} is already on your dashboard — scroll down to view",
        "layout_always_on": "always on",
        "fab_session": "📌 Session Tracker",
        "fab_alerts": "🔔 Alerts: {state}",
        "state_on": "On",
        "state_off": "Off",
        "alerts_enable_label": "Alert on ±{threshold}% moves",
        "alerts_empty": "No alerts yet — you'll see a log here once a watched price moves past your threshold.",
        "fab_refresh": "🔄 Refresh Now",
        "fab_mode": "🪙 Mode: {mode}",
        "mode_normal": "Normal",
        "mode_crypto": "Crypto",
        "mode_irr_short": "IRR",
        "toast_mode_switched": "Switched to {mode} mode",
        "toast_refreshing_now": "🔄 Refreshing prices…",
        "ctx_cut": "Cut",
        "ctx_copy": "Copy",
        "ctx_paste": "Paste",
        "ctx_select_all": "Select All",
        "portfolio_empty_hint": "Your portfolio is empty — use the panel above to add currencies you want to track.",
        "portfolio_empty_filtered": "No portfolio items match your filter.",
        "fab_export": "📄 Export CSV",
        "fab_cache": "🧹 Clear Cache",
        "fab_performance": "📈 Performance",
        "fab_api_test": "🧪 Test API",
        "session_tracker_title": "Session Tracker",
        "session_tracker_empty": "No session data yet — prices will appear here as they update.",
    },
    "fa": {
        "portfolio_items": "آیتم ها",
        "best": "بهترین",
        "worst": "بدترین",
        "updated": "آخرین بروزرسانی",

        # Toolbar / hero
        "toolbar_title": "قیمت مربا",
        "btn_add_currency": "➕ افزودن ارز",
        "language_label": "زبان",

        "hero_title": "💎 قیمت مربا",
        "hero_subtitle": "نمایش لحظه‌ای ارز • کریپتو • طلا • پورتفو",
        "hero_version": "نسخه {version} • اجرای سریع از کش • رابط نرم‌تر",

        # Sections
        "section_featured": "📈 بازارهای منتخب",
        "section_insights": "⚡ تحلیل بازار",
        "section_portfolio": "💼 پورتفوی شما",
        "section_controls": "🎛️ کنترل داده",
        "section_settings": "⚙️ تنظیمات",
        "section_theme": "🎨 تم",
        "section_history": "📉 تاریخچه قیمت",
        "section_converter": "🧮 تبدیل‌کننده",
        "section_widgets": "🧩 ویجت‌های دسکتاپ",
        "theme_liquid_glass": "💧 شیشه‌ای",
        "theme_crystal": "💎 کریستال",
        "theme_paper": "📄 کاغذی",
        "theme_paper_noir": "⬛ کاغذی نوآر",
        "theme_name_liquid_glass": "شیشه‌ای",
        "theme_name_crystal": "کریستال",
        "theme_name_paper": "کاغذی",
        "theme_name_paper_noir": "کاغذی نوآر",

        # Insights
        "top_gainers": "بیشترین رشد",
        "top_losers": "بیشترین افت",

        # History
        "history_symbol": "نماد",
        "history_period": "بازه",
        "history_loading": "در حال بارگذاری تاریخچه…",
        "history_no_data": "تاریخچه‌ای موجود نیست",
        "history_change": "تغییر",
        "history_min": "کمینه",
        "history_max": "بیشینه",
        "period_1h": "۱ ساعت",
        "period_6h": "۶ ساعت",
        "period_24h": "۲۴ ساعت",
        "period_7d": "۷ روز",

        # Converter
        "converter_amount": "مقدار",
        "converter_from": "از",
        "converter_to": "به",
        "converter_result": "نتیجه",
        "converter_need_usd": "برای این تبدیل، نرخ دلار لازم است",

        # Widgets
        "widgets_add_title": "افزودن ویجت",
        "widgets_active_title": "ویجت‌های فعال",
        "widgets_type": "نوع",
        "widgets_symbol": "نماد",
        "widget_theme_label": "تم ویجت",
        "widget_theme_auto": "🔄 خودکار (هم‌رنگ برنامه)",
        "widget_type_price": "کارت قیمت",
        "widget_type_movers": "تاپ‌موور",
        "widget_type_portfolio": "خلاصه پورتفو",
        "btn_add_widget": "➕ افزودن ویجت",
        "btn_remove_widget": "حذف",
        "toast_widget_added": "🧩 ویجت اضافه شد",
        "toast_widget_removed": "🧹 ویجت حذف شد",
        "toast_widget_not_supported": "⚠️ ویجت دسکتاپ فعلاً فقط ویندوز را پشتیبانی می‌کند",
        "toast_widget_add_failed": "افزودن ویجت ناموفق بود",
        "widgets_persist_hint": "💡 برای اینکه این ویجت در حالت مینیمایز هم فعال بمونه، از تنظیمات «اجرا در پس‌زمینه» را روشن کنید.",

        # Background
        "run_in_background": "اجرای پس‌زمینه هنگام بستن",
        "toast_background_on": "🟣 پس‌زمینه فعال شد (بستن = مینیمایز)",
        "toast_background_off": "⚪ پس‌زمینه غیرفعال شد",

        # Controls / settings labels
        "api": "API",
        "data": "داده",
        "effects": "افکت‌ها",
        "sort": "مرتب‌سازی:",
        "auto_refresh": "به‌روزرسانی خودکار",
        "last_update": "آخرین بروزرسانی: {time}",
        "refresh_interval": "فاصله بروزرسانی",
        "alerts_title": "هشدار تغییر قیمت",
        "enable_alerts": "فعال‌سازی هشدار",
        "threshold": "آستانه: {value:.1f}٪",
        "tools": "ابزارها",
        "window_options": "پنجره",
        "always_on_top": "همیشه روی صفحه",

        # Buttons
        "btn_refresh": "🔄 بروزرسانی",
        "btn_test_api": "🧪 تست API",
        "btn_export_csv": "📄 خروجی CSV",
        "btn_copy": "📋 کپی",
        "btn_clear_cache": "🧹 پاکسازی کش",
        "btn_performance": "📈 عملکرد",
        "btn_add": "افزودن",
        "btn_search": "جستجو",
        "btn_close": "بستن",

        # Forward price modal
        "forward_price_title": "قیمت فردایی",
        "forward_price_loading": "در حال دریافت قیمت فردایی…",
        "forward_price_spot": "قیمت نقدی",
        "forward_price_forward": "قیمت فردایی",
        "forward_price_unavailable": "قیمت فردایی در حال حاضر در دسترس نیست.",

        # Placeholders
        "placeholder_search": "جستجو…",
        "placeholder_portfolio_filter": "فیلتر پورتفو…",
        "portfolio_add_title": "➕ افزودن به پورتفو",

        # Sort modes
        "sort_default": "پیش‌فرض",
        "sort_name": "نام",
        "sort_symbol": "نماد",
        "sort_price": "قیمت",
        "sort_change": "تغییر",

        # Connection messages
        "status_connected": "🟢 متصل • {count} مورد",
        "status_cached": "🟠 کش • {count} مورد",
        "status_connecting": "🔵 در حال اتصال…",
        "status_rate_limited": "🟠 محدودیت درخواست",
        "status_error": "🔴 آفلاین / خطا",

        # Data status
        "data_quality_excellent": "عالی",
        "data_quality_cached": "کش",
        "data_quality_connecting": "در حال اتصال",
        "data_quality_limited": "محدود",
        "data_source_live": "API آنلاین",
        "data_source_db": "دیتابیس محلی",
        "data_source_offline": "آفلاین/پیش‌فرض",

        # Toasts / misc
        "toast_updated": "✅ بروزرسانی شد",
        "toast_loaded_cache": "🗃️ داده‌های کش بارگذاری شد (به‌زودی آنلاین بروزرسانی می‌شود)",
        "toast_added": "✅ {sym} اضافه شد",
        "toast_removed": "🗑️ {sym} حذف شد",
        "toast_interval_set": "⏱️ فاصله روی {interval} تنظیم شد",
        "toast_autorefresh_on": "▶️ بروزرسانی خودکار فعال",
        "toast_autorefresh_off": "⏸️ بروزرسانی خودکار غیرفعال",
        "toast_alerts_on": "🔔 هشدار فعال",
        "toast_alerts_off": "🔕 هشدار غیرفعال",
        "toast_cache_cleared": "🧹 کش پاک شد",
        "toast_topmost_on": "📌 همیشه روی صفحه فعال شد",
        "toast_topmost_off": "📌 همیشه روی صفحه غیرفعال شد",
        "toast_copied": "📋 کپی شد",
        "toast_csv_exported": "📄 CSV ذخیره شد",
        "toast_refresh_failed": "❌ امکان بروزرسانی نیست (آفلاین؟)",
        "toast_applying_theme": "🎨 در حال اعمال {name}…",
        "toast_price_moved": "{direction} {sym} نسبت به بروزرسانی قبل {delta:+.2f}٪ تغییر کرد",
        "status_refreshing": "🔄 در حال بروزرسانی…",

        # Dialogs / errors
        "dlg_add_currency_title": "افزودن ارز",
        "no_matches": "موردی پیدا نشد",
        "api_test_title": "تست API",
        "api_test_ok": "✅ تست API موفق بود\n\nزمان پاسخ: {elapsed:.2f} ثانیه\nتعداد آیتم: {count}\n",
        "api_test_fail": "❌ تست API ناموفق بود\n\nداده‌ای دریافت نشد.",
        "export_title": "خروجی CSV",
        "filetype_csv": "فایل‌های CSV",
        "filetype_all": "همه فایل‌ها",
        "export_failed": "ناموفق:\n{error}",
        "clear_cache_title": "پاکسازی کش",
        "performance_title": "عملکرد",
        "critical_error_title": "خطای بحرانی",

        # Floating action menu
        "fab_menu_title": "دسترسی سریع",
        "fab_language": "🌐 زبان: {lang_name}",
        "fab_theme": "🎨 تم: {name}",
        "fab_converter": "🧮 تبدیل‌کننده",
        "fab_widgets": "🧩 ویجت‌های دسکتاپ",
        "fab_controls": "🎛️ کنترل داده",
        "fab_settings": "⚙️ تنظیمات",
        "fab_layout": "📐 مدیریت بخش‌ها",
        "toast_section_revealed": "✅ {name} به داشبورد اضافه شد — برای مشاهده اسکرول کنید",
        "toast_already_on_dashboard": "{name} از قبل در داشبورد شماست — برای مشاهده اسکرول کنید",
        "layout_always_on": "همیشه فعال",
        "fab_session": "📌 ردیاب جلسه",
        "fab_alerts": "🔔 هشدارها: {state}",
        "state_on": "روشن",
        "state_off": "خاموش",
        "alerts_enable_label": "هشدار برای تغییرات ±{threshold}٪",
        "alerts_empty": "هنوز هشداری ثبت نشده — با عبور قیمت از آستانه تعیین‌شده، اینجا نمایش داده می‌شود.",
        "fab_refresh": "🔄 بروزرسانی",
        "fab_mode": "🪙 حالت: {mode}",
        "mode_normal": "عادی",
        "mode_crypto": "ارز دیجیتال",
        "mode_irr_short": "ریال",
        "toast_mode_switched": "به حالت {mode} تغییر یافت",
        "toast_refreshing_now": "🔄 در حال بروزرسانی قیمت‌ها…",
        "ctx_cut": "برش",
        "ctx_copy": "کپی",
        "ctx_paste": "چسباندن",
        "ctx_select_all": "انتخاب همه",
        "portfolio_empty_hint": "پرتفوی شما خالی است — از پنل بالا برای افزودن ارزهای مورد نظر استفاده کنید.",
        "portfolio_empty_filtered": "هیچ موردی با فیلتر شما مطابقت ندارد.",
        "fab_export": "📄 خروجی CSV",
        "fab_cache": "🧹 پاکسازی کش",
        "fab_performance": "📈 عملکرد",
        "fab_api_test": "🧪 تست API",
        "session_tracker_title": "ردیاب جلسه",
        "session_tracker_empty": "هنوز داده‌ای ثبت نشده — با بروزرسانی قیمت‌ها اینجا نمایش داده می‌شود.",
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    """Lightweight translation helper with safe fallback to English."""
    lang_key = str(lang or "en").lower()
    base = TRANSLATIONS.get(lang_key, TRANSLATIONS["en"])
    template = base.get(key) or TRANSLATIONS["en"].get(key) or key
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def is_rtl(lang: str) -> bool:
    return str(lang or "").lower().startswith("fa")

