"""
Application configuration for Gheymat Morabba Price Tracker.

Single source of truth for window sizing, API endpoints, refresh/cache
timing, and connection-state signalling. Import the module-level
``config`` singleton rather than instantiating ``AppConfiguration``
directly.
"""

from __future__ import annotations

import os
from typing import Dict, List
from dataclasses import dataclass, field
from enum import Enum


def _get_db_path() -> str:
    """مسیر استاندارد ذخیره دیتابیس در ویندوز (پوشه AppData)"""
    base_dir = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "GheymatMorabba")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "Gheymat_Morabba_data.db")


def _get_brsapi_key() -> str:
    """Your own BRSAPI key, read from the BRSAPI_KEY environment variable.
    Get one at https://brsapi.ir -- Normal-mode gold/currency/commodity
    data and Crypto-mode data both come from BRSAPI endpoints built with
    this key. Never hardcode a real key here: this returns an empty
    string until one is set, so a missing key fails loudly (empty/401
    responses, caught by the existing retry/circuit-breaker logic) rather
    than silently working off someone else's quota."""
    return os.environ.get("BRSAPI_KEY", "")


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CACHED = "cached"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class AppConfiguration:
    # App
    APP_NAME: str = "Gheymat Morabba Price Tracker"
    APP_VERSION: str = "5.0.0"
    APP_AUTHOR: str = "Local App"

    # Window
    WINDOW_WIDTH: int = 1200
    WINDOW_HEIGHT: int = 900
    MIN_WIDTH: int = 1000
    MIN_HEIGHT: int = 780

    # Layout
    GRID_COLUMNS: int = 4
    CARD_WIDTH: int = 240
    CARD_HEIGHT: int = 160
    CARD_PADDING: int = 8

    # Fonts
    PRIMARY_FONT: str = "SF Pro Display"
    FALLBACK_FONT: str = "Segoe UI"
    PERSIAN_FONT: str = "Vazirmatn"

    # API
    # BRSAPI_KEY is your own key from https://brsapi.ir, supplied as an
    # environment variable (see README.md > Configuration). Every request
    # below is built from it -- there is no key baked into this file.
    BRSAPI_KEY: str = _get_brsapi_key()
    PRIMARY_API_URL: str = f"https://api.brsapi.ir/Market/Gold_Currency.php?key={_get_brsapi_key()}"
    TETHERLAND_API_URL: str = "https://api.tetherland.com/currencies"
    COMMODITY_API_URL: str = f"https://api.brsapi.ir/Market/Commodity.php?key={_get_brsapi_key()}"
    CRYPTOCURRENCY_API_URL: str = f"https://api.brsapi.ir/Market/Cryptocurrency.php?key={_get_brsapi_key()}"
    BACKUP_API_ENDPOINTS: List[str] = field(default_factory=lambda: [
        f"https://brsapi.ir/Api/Market/Gold_Currency.php?key={_get_brsapi_key()}",
        "https://arz.zaringo.sbs/core/api.php",
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,binancecoin,cardano,solana,polkadot,dogecoin,avalanche-2,polygon,chainlink&vs_currencies=usd&include_24hr_change=true",
        "https://api.exchangerate-api.com/v4/latest/USD",
    ])
    API_TIMEOUT: int = 15
    API_RETRY_COUNT: int = 3
    API_RETRY_DELAY: float = 1.0  # base delay
    VERIFY_SSL: bool = True
    USER_AGENT: str = "GheymatMorabba/5.0 (Desktop)"

    # Optional: a free key from @navasan_contact_bot on Telegram enables a
    # real forward ("farda") USD rate in the forward-price popup. Set it
    # as the NAVASAN_API_KEY environment variable -- without one, the
    # popup falls back to a Tether-derived USD estimate instead.
    NAVASAN_API_KEY: str = os.environ.get("NAVASAN_API_KEY", "")

    # BRSAPI's three Market endpoints (above) share one API key and, from
    # the account's behavior, one combined daily quota. This budget is a
    # client-side safety net regardless of whose key is in use -- it
    # stops this install from retrying into 429s once its own daily
    # allowance is spent. Override via env var if your plan's actual
    # daily cap is different from 10,000.
    BRSAPI_DAILY_BUDGET: int = int(os.environ.get("BRSAPI_DAILY_BUDGET", "10000"))

    # Optional: base URL of a deployed cf-worker/ instance you control
    # (e.g. "https://your-project.your-subdomain.workers.dev"). When set,
    # APIManager and ForwardPriceService read from "<url>/prices" first
    # and only fall back to calling brsapi.ir / navasan.tech directly if
    # that fails -- see cf-worker/README.md. Left empty (the default),
    # the app always calls BRSAPI/Tetherland/Navasan directly using
    # BRSAPI_KEY / NAVASAN_API_KEY above, still protected by
    # BRSAPI_DAILY_BUDGET. Deliberately no default worker URL ships here:
    # every fork should point at a worker it deploys and pays for itself,
    # not silently ride on someone else's.
    WORKER_BASE_URL: str = os.environ.get("GHEYMAT_WORKER_URL", "")

    # Refresh
    DEFAULT_REFRESH_INTERVAL: int = 60  # seconds
    MIN_REFRESH_INTERVAL: int = 30
    MAX_REFRESH_INTERVAL: int = 3600

    # Cache
    CACHE_DURATION: int = 45  # in-memory seconds
    DATABASE_PATH: str = field(default_factory=_get_db_path)

    # Performance
    MAX_WORKER_THREADS: int = 4
    UI_UPDATE_BATCH_SIZE: int = 12

    # History / Widgets
    HISTORY_RETENTION_DAYS: int = 14
    HISTORY_MAX_POINTS: int = 240  # max points rendered in sparklines
    WIDGET_WIDTH: int = 280
    WIDGET_HEIGHT: int = 170
    WIDGET_MIN_WIDTH: int = 210
    WIDGET_MIN_HEIGHT: int = 130
    WIDGET_DEFAULT_OPACITY: float = 0.98

    # Single instance (loopback-only IPC used to focus an already-running window)
    SINGLE_INSTANCE_PORT: int = 47681
    SINGLE_INSTANCE_TOKEN: str = "GHEYMAT_MORABBA_SHOW"


config = AppConfiguration()


# Assets eligible for the forward ("fardaee") price popup. Deliberately
# scoped to metals/coins and fiat currencies only -- crypto has no
# meaningful "tomorrow" market and isn't included here on purpose, in
# either app mode.
FORWARD_PRICE_ASSETS: Dict[str, str] = {
    # Gold & coins
    "IR_GOLD_18K": "طلای ۱۸ عیار",
    "IR_GOLD_24K": "طلای ۲۴ عیار",
    "IR_GOLD_MELTED": "طلای آب‌شده نقدی",
    "XAUUSD": "انس طلا",
    "IR_COIN_1G": "سکه یک گرمی",
    "IR_COIN_QUARTER": "ربع سکه",
    "IR_COIN_HALF": "نیم سکه",
    "IR_COIN_EMAMI": "سکه امامی",
    "IR_COIN_BAHAR": "سکه بهار آزادی",
    # Fiat currencies
    "USD": "دلار آمریکا",
    "EUR": "یورو",
    "AED": "درهم امارات",
    "GBP": "پوند انگلیس",
    "JPY": "۱۰۰ ین ژاپن",
    "KWD": "دینار کویت",
    "AUD": "دلار استرالیا",
    "CAD": "دلار کانادا",
    "CNY": "یوآن چین",
    "TRY": "لیر ترکیه",
    "SAR": "ریال عربستان",
    "CHF": "فرانک سوئیس",
    "INR": "روپیه هند",
    "PKR": "روپیه پاکستان",
    "IQD": "دینار عراق",
    "SYP": "لیر سوریه",
    "SEK": "کرون سوئد",
    "QAR": "ریال قطر",
    "OMR": "ریال عمان",
    "BHD": "دینار بحرین",
    "AFN": "افغانی افغانستان",
    "MYR": "رینگیت مالزی",
    "THB": "بات تایلند",
    "RUB": "روبل روسیه",
    "AZN": "منات آذربایجان",
    "AMD": "درام ارمنستان",
    "GEL": "لاری گرجستان",
}