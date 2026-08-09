"""Market-data access: primary + fallback endpoints, retries, a simple
circuit breaker, and response normalization into one common currency
record shape."""

from __future__ import annotations

import json
import math
import re
import time
import requests

from bs4 import BeautifulSoup

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from core.config import config, FORWARD_PRICE_ASSETS
from core.utils import logger
from data.db import db_manager


class BrsApiBudget:
    """Local, per-install daily call budget for the three brsapi.ir Market
    endpoints, which all share one key (see config.py) and, apparently,
    one combined daily quota.

    This app ships the same key with every install, so the real problem
    was never "one process is too chatty" -- it's that every copy of the
    app in the wild hits the same account. A budget tracked in this one
    process can't fix that on its own (see cf-worker/ for the actual
    fix), but it stops this install from being the one that tips the
    account over, and it means a spent-out day fails fast into cache
    instead of burning retries against a wall of 429s.

    Split: in normal mode, Gold_Currency and Commodity each get half the
    daily total, since they're always called together once per refresh
    and there's no reason one should starve the other. Crypto mode isn't
    split -- while it's the only one drawing from the pool, it can use
    all of it. Switching modes doesn't reset anything; each category
    just keeps checking its own half-of-total cap against whatever's
    left in the day.
    """

    CATEGORIES = ("gold_currency", "commodity", "crypto")

    def __init__(self, daily_total: Optional[int] = None):
        self.daily_total = int(daily_total or getattr(config, "BRSAPI_DAILY_BUDGET", 10000))

    def _day_key(self, category: str) -> str:
        return f"brsapi_calls_{category}_{time.strftime('%Y-%m-%d')}"

    def _used(self, category: str) -> int:
        return int(db_manager.load_preference(self._day_key(category), 0) or 0)

    def allow(self, category: str) -> bool:
        total_used = sum(self._used(c) for c in self.CATEGORIES)
        if total_used >= self.daily_total:
            return False
        if category in ("gold_currency", "commodity") and self._used(category) >= self.daily_total // 2:
            return False
        return True

    def record(self, category: str) -> None:
        key = self._day_key(category)
        db_manager.save_preference(key, self._used(category) + 1)

    def status(self) -> Dict[str, int]:
        return {c: self._used(c) for c in self.CATEGORIES}


class APIManager:
    """Robust API access (primary + fallbacks, retries, circuit breaker, cache)."""

    # How long a fetched worker snapshot is reused locally before asking
    # again. Kept short enough that one refresh cycle (primary, then
    # commodity, then crypto if the mode switches) collapses into a
    # single HTTP call to the worker, but shorter than the worker's own
    # cron interval so a new app refresh tick still sees fresh data.
    WORKER_CACHE_SECONDS = 20

    def __init__(self):
        self.session = self._create_session()
        self._last_data: Optional[Dict[str, Any]] = None
        self._last_data_ts: float = 0.0

        self.last_request_time = 0.0
        self.rate_limit_delay = 1.0

        self.failure_count = 0
        self.circuit_breaker_until = 0.0  # epoch seconds
        self.circuit_breaker_base = 15.0  # seconds

        self.budget = BrsApiBudget()
        self._worker_envelope: Optional[Dict[str, Any]] = None
        self._worker_envelope_ts: float = 0.0

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        })

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0,  # manual retries
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _circuit_open(self) -> bool:
        return time.time() < self.circuit_breaker_until

    def _trip_circuit(self) -> None:
        self.failure_count += 1
        backoff = min(self.circuit_breaker_base * (2 ** (self.failure_count - 1)), 300.0)
        self.circuit_breaker_until = time.time() + backoff

    def _fetch_worker_envelope(self, force: bool = False) -> Optional[Dict[str, Any]]:
        """Pull the latest cached snapshot from the shared Cloudflare Worker,
        when one's configured (config.WORKER_BASE_URL). This is what actually
        fixes the shared-key problem instead of just managing it: every
        install reads from one small, cheap cache instead of each one
        hitting brsapi.ir directly with the same key. See cf-worker/ for
        what runs on the other end of this.

        Returns None (never raises) whenever no worker is configured or
        the call fails, so the direct-fetch path in each method below
        still carries the app on its own for anyone running without one."""
        base = str(getattr(config, "WORKER_BASE_URL", "") or "").strip().rstrip("/")
        if not base:
            return None
        if not force and self._worker_envelope is not None:
            if time.time() - self._worker_envelope_ts < self.WORKER_CACHE_SECONDS:
                return self._worker_envelope
        try:
            resp = self.session.get(f"{base}/prices", timeout=config.API_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                self._worker_envelope = data
                self._worker_envelope_ts = time.time()
                return data
        except Exception as e:
            logger.debug(f"Worker fetch failed, falling back to direct calls: {e}")
        return None

    def fetch_tether_irr_rate_sync(self) -> Optional[float]:
        """Crypto mode's USDT/IRR toggle needs this one rate from Tetherland
        to convert each coin's Toman price to a consistent USDT-equivalent
        price. This is a narrow exception: it fetches only the rate itself,
        never merges Tetherland's data into the crypto currency list."""
        try:
            raw = self._request_with_retries(config.TETHERLAND_API_URL, is_primary=False)
            if not raw:
                return None
            parsed = self._process_tetherland_format(raw)
            entry = parsed.get("USDT_IRT")
            if not entry:
                return None
            rate = self._safe_float(entry.get("price"))
            return rate if rate and rate > 0 else None
        except Exception as e:
            logger.debug(f"Tether rate fetch failed: {e}")
            return None

    def fetch_crypto_currencies_sync(self, force: bool = False) -> Optional[Dict[str, Dict[str, Any]]]:
        """Crypto-mode fetch: only the dedicated cryptocurrency feed, completely
        independent of the normal-mode sources. Deliberately never touches the
        primary/commodity/Tetherland endpoints."""
        envelope = self._fetch_worker_envelope(force=force)
        if envelope and envelope.get("crypto"):
            try:
                return self.process_currency_data(envelope["crypto"])
            except Exception as e:
                logger.debug(f"Crypto (worker) processing failed: {e}")

        if not self.budget.allow("crypto"):
            logger.debug("Crypto daily budget exhausted; skipping call, cards keep last-known values.")
            return None
        try:
            raw = self._request_with_retries(config.CRYPTOCURRENCY_API_URL, is_primary=False)
            if not raw:
                return None
            self.budget.record("crypto")
            return self.process_currency_data(raw)
        except Exception as e:
            logger.debug(f"Crypto-mode fetch failed: {e}")
            return None

    def fetch_all_currencies_sync(self, force: bool = False) -> Optional[Dict[str, Dict[str, Any]]]:
        """Fetch and merge all three configured data sources into one unified
        currency dict. The primary feed (gold/currency/crypto) is required;
        Commodity (metals/energy) and Tetherland (Tether) are best-effort
        enrichments — if either is unreachable, the app still works with
        whatever the primary feed provided, it just won't have that extra data
        for this cycle."""
        primary_raw = self.fetch_data_sync(force=force)
        if not primary_raw:
            return None

        merged = self.process_currency_data(primary_raw)

        # Commodity: additive metals/energy. Where a symbol overlaps with the
        # primary feed (e.g. XAUUSD), the dedicated Commodity feed wins.
        # Worker's already-cached copy first (see _fetch_worker_envelope);
        # this call is nearly free since fetch_data_sync above just warmed
        # the same 20s cache.
        envelope = self._fetch_worker_envelope()
        if envelope and envelope.get("commodity"):
            try:
                merged.update(self.process_currency_data(envelope["commodity"]))
            except Exception as e:
                logger.debug(f"Commodity (worker) merge failed: {e}")
        elif self.budget.allow("commodity"):
            try:
                commodity_raw = self._request_with_retries(config.COMMODITY_API_URL, is_primary=False)
                if commodity_raw:
                    self.budget.record("commodity")
                    merged.update(self.process_currency_data(commodity_raw))
            except Exception as e:
                logger.debug(f"Commodity fetch/merge failed: {e}")
        else:
            logger.debug("Commodity daily budget exhausted; skipping this cycle, cards keep last-known values.")

        # Tetherland: authoritative Toman-priced Tether feed, overrides the
        # primary feed's own USDT_IRT entry when available.
        try:
            tether_raw = self._request_with_retries(config.TETHERLAND_API_URL, is_primary=False)
            if tether_raw:
                merged.update(self.process_currency_data(tether_raw))
        except Exception as e:
            logger.debug(f"Tetherland fetch/merge failed: {e}")

        return merged

    def fetch_data_sync(self, force: bool = False, skip_primary: bool = False) -> Optional[Dict[str, Any]]:
        # In-memory cache for very frequent calls
        if not force and self._last_data is not None:
            if time.time() - self._last_data_ts < config.CACHE_DURATION:
                return self._last_data

        envelope = self._fetch_worker_envelope(force=force)
        if envelope and envelope.get("primary"):
            self._last_data = envelope["primary"]
            self._last_data_ts = time.time()
            self.failure_count = 0
            return self._last_data

        if self._circuit_open():
            logger.warning("Circuit breaker open — skipping network call.")
            return None

        # 1) Primary API
        if not skip_primary:
            if self.budget.allow("gold_currency"):
                data = self._request_with_retries(config.PRIMARY_API_URL, is_primary=True)
                if data:
                    self.budget.record("gold_currency")
                    self._last_data = data
                    self._last_data_ts = time.time()
                    self.failure_count = 0
                    return data
            else:
                logger.debug("Gold_Currency daily budget exhausted; falling through to backups/cache.")

        # 2) Backups (different providers -- not brsapi, not budget-gated;
        # the one brsapi mirror in this list is only reached this rarely,
        # so it isn't worth tracking separately)
        for url in config.BACKUP_API_ENDPOINTS:
            data = self._request_with_retries(url, is_primary=False)
            if data:
                self._last_data = data
                self._last_data_ts = time.time()
                self.failure_count = 0
                return data

        self._trip_circuit()
        return None

    def _request_with_retries(self, url: str, is_primary: bool) -> Optional[Dict[str, Any]]:
        delay = config.API_RETRY_DELAY
        last_err: str = ""
        for attempt in range(1, config.API_RETRY_COUNT + 1):
            try:
                self._respect_rate_limit()
                resp = self.session.get(url, timeout=config.API_TIMEOUT, verify=config.VERIFY_SSL)
                if resp.status_code == 429:
                    logger.warning("Rate limited (429).")
                    self.rate_limit_delay = min(max(self.rate_limit_delay, 1.0) * 1.5, 10.0)
                    time.sleep(min(delay * attempt, 10.0))
                    continue

                resp.raise_for_status()
                try:
                    data = resp.json()
                except Exception:
                    raw = (resp.text or "").strip()
                    raw = raw.lstrip("\ufeff").strip()
                    data = json.loads(raw) if raw else None
                if not data:
                    raise ValueError("Empty response")
                return data

            except requests.exceptions.Timeout as e:
                last_err = f"Timeout: {e}"
                logger.debug(f"Timeout ({attempt}/{config.API_RETRY_COUNT}) for {url}")
            except requests.exceptions.RequestException as e:
                last_err = f"RequestException: {e}"
                logger.debug(f"Request failed ({attempt}/{config.API_RETRY_COUNT}) for {url}: {e}")
            except (ValueError, json.JSONDecodeError) as e:
                last_err = f"ParseError: {e}"
                logger.debug(f"Parse failed ({attempt}/{config.API_RETRY_COUNT}) for {url}: {e}")
            except Exception as e:
                last_err = f"Unexpected: {e}"
                logger.debug(f"Unexpected error ({attempt}/{config.API_RETRY_COUNT}) for {url}: {e}")

            time.sleep(min(delay * attempt, 6.0))

        if last_err:
            logger.warning(f"API request failed for {url} (verify_ssl={config.VERIFY_SSL}): {last_err}")
        return None


    # ----- number helpers -----

    @staticmethod
    def _digits_to_en(s: str) -> str:
        if not s:
            return s
        trans = str.maketrans({
            "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
            "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
            "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
            "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
            "٬": ",", "،": ",", "٫": ".",  # Arabic/Persian separators
        })
        return s.translate(trans)

    @classmethod
    def _clean_number_str(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v).strip()
        s = cls._digits_to_en(s)
        # keep digits, sign and separators only
        # remove common tokens
        for tok in ("%", "٪", "ریال", "تومان", "USD", "USDT"):
            s = s.replace(tok, "")
        s = s.strip()
        # normalize separators
        s = s.replace(" ", "")
        s = s.replace("_", "")
        # remove thousands separators
        s = s.replace(",", "")
        return s

    @classmethod
    def _safe_float(cls, v: Any) -> Optional[float]:
        s = cls._clean_number_str(v)
        if not s:
            return None
        # handle leading/trailing junk
        try:
            return float(s)
        except Exception:
            # last attempt: keep only valid characters
            filtered = "".join(ch for ch in s if ch.isdigit() or ch in ".-+")
            try:
                return float(filtered) if filtered else None
            except Exception as e:
                try:
                    logger.warning(f"API request error: {e}")
                except Exception:
                    pass
                return None


    # ----- data processing -----

    def process_currency_data(self, raw_data: Any) -> Dict[str, Dict[str, Any]]:
        try:
            if self._is_tetherland_format(raw_data):
                return self._process_tetherland_format(raw_data)

            if self._is_crypto_api_format(raw_data):
                return self._process_crypto_api_format(raw_data)

            if self._is_primary_api_format(raw_data):
                return self._process_primary_api_format(raw_data)

            # CoinGecko "simple/price" format (backup endpoint)
            if isinstance(raw_data, dict) and self._looks_like_coingecko_simple_price(raw_data):
                return self._process_coingecko_simple_price(raw_data)

            # exchangerate-api format (backup endpoint)
            if isinstance(raw_data, dict) and isinstance(raw_data.get("rates"), dict):
                return self._process_exchangerate_api(raw_data)

            # Other backups (explicit format)
            if isinstance(raw_data, dict) and ("crypto" in raw_data or "fiat" in raw_data):
                return self._process_backup_api_format(raw_data)

            return self._process_generic_format(raw_data)
        except Exception as e:
            logger.debug(f"Currency processing failed: {e}")
            return {}

    # Well-known coins get their real ticker; everything else gets a symbol
    # derived from its name (this API doesn't provide tickers at all, only names).
    _CRYPTO_TICKER_MAP: Dict[str, str] = {
        "Bitcoin": "BTC", "Ethereum": "ETH", "Tether": "USDT", "Binance Coin": "BNB",
        "USD Coin": "USDC", "XRP": "XRP", "Solana": "SOL", "Cardano": "ADA",
        "Dogecoin": "DOGE", "Polkadot": "DOT", "Avalanche": "AVAX", "Polygon": "MATIC",
        "Litecoin": "LTC", "TRON": "TRX", "Toncoin": "TON", "Shiba Inu": "SHIB",
        "Chainlink": "LINK", "Uniswap": "UNI", "Cosmos": "ATOM", "Stellar": "XLM",
        "Filecoin": "FIL", "Monero": "XMR", "Aptos": "APT", "Arbitrum": "ARB",
        "Optimism": "OP", "NEAR Protocol": "NEAR", "Internet Computer": "ICP",
        "Hedera": "HBAR", "VeChain": "VET", "Algorand": "ALGO", "Fantom": "FTM",
        "The Graph": "GRT", "Aave": "AAVE", "Maker": "MKR", "Ethereum Classic": "ETC",
        "Bitcoin Cash": "BCH", "Dai": "DAI", "Sui": "SUI", "Injective": "INJ",
        "Celestia": "TIA", "Sei": "SEI", "Pepe": "PEPE", "Bonk": "BONK", "Floki": "FLOKI",
        "Bitcoin SV": "BSV", "Bitcoin Gold": "BTG", "Zcash": "ZEC", "Dash": "DASH",
        "IOTA": "IOTA", "EOS": "EOS", "Tezos": "XTZ", "Neo": "NEO", "Waves": "WAVES",
        "Compound": "COMP", "Curve DAO Token": "CRV", "Synthetix": "SNX", "1inch": "1INCH",
        "PancakeSwap": "CAKE", "SushiSwap": "SUSHI", "Yearn.finance": "YFI",
        "Decentraland": "MANA", "The Sandbox": "SAND", "Axie Infinity": "AXS",
        "Gala": "GALA", "ApeCoin": "APE", "Flow": "FLOW", "Theta Network": "THETA",
        "Kusama": "KSM", "Elrond": "EGLD", "Chiliz": "CHZ", "Basic Attention Token": "BAT",
        "Enjin Coin": "ENJ", "Helium": "HNT", "Quant": "QNT", "Fetch.ai": "FET",
        "Render": "RNDR", "Immutable": "IMX", "Mina": "MINA", "Kava": "KAVA",
    }

    def _crypto_symbol_for(self, name_en: str, item_id: Any, used: Set[str]) -> str:
        name_en = str(name_en or "").strip()
        mapped = self._CRYPTO_TICKER_MAP.get(name_en)
        if mapped and mapped not in used:
            return mapped

        base = re.sub(r"[^A-Za-z0-9]", "", name_en).upper()[:12]
        if not base:
            base = f"COIN{item_id}"
        if base not in used:
            return base
        return f"{base}_{item_id}"

    def _is_crypto_api_format(self, data: Any) -> bool:
        try:
            return (
                isinstance(data, list)
                and len(data) > 0
                and isinstance(data[0], dict)
                and "price_toman" in data[0]
            )
        except Exception:
            return False

    def _process_crypto_api_format(self, data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        used: Set[str] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                price_toman = self._safe_float(item.get("price_toman"))
                price_usd = self._safe_float(item.get("price"))
                if price_toman is None and price_usd is None:
                    continue

                name_en = str(item.get("name_en") or "").strip()
                name_fa = str(item.get("name") or "").strip()
                item_id = item.get("id")
                symbol = self._crypto_symbol_for(name_en, item_id, used)
                used.add(symbol)

                change = self._safe_float(item.get("change_percent"))

                out[symbol] = {
                    "symbol": symbol,
                    "name": name_fa or name_en or symbol,
                    "name_en": name_en or symbol,
                    "price": str(price_toman if price_toman is not None else price_usd),
                    "price_usd": price_usd,
                    "unit": "تومان" if price_toman is not None else "دلار",
                    "change_percent": str(change if change is not None else 0.0),
                    "category": "crypto",
                    "crypto_category": item.get("category"),
                    "market_cap": self._safe_float(item.get("market_cap")),
                    "icon_url": item.get("link_icon"),
                    "source": "crypto_api",
                    "timestamp": time.time(),
                }
            except Exception:
                continue
        return out

    def _is_tetherland_format(self, data: Any) -> bool:
        try:
            return (
                isinstance(data, dict)
                and isinstance(data.get("data"), dict)
                and isinstance(data["data"].get("currencies"), dict)
            )
        except Exception:
            return False

    def _process_tetherland_format(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        try:
            currencies = data.get("data", {}).get("currencies", {})
            for sym_key, item in currencies.items():
                if not isinstance(item, dict):
                    continue
                symbol = str(sym_key).upper().strip()
                if not symbol:
                    continue

                price_f = self._safe_float(item.get("price"))
                if price_f is None:
                    continue

                change_f = self._safe_float(item.get("diff24d"))
                change_f = change_f if change_f is not None else 0.0

                buy_f = self._safe_float(item.get("buy_price"))
                sell_f = self._safe_float(item.get("sell_price"))

                # Tetherland is Toman-priced; canonical key matches the app's
                # existing "<SYMBOL>_IRT" convention used for Toman-denominated pairs.
                out_symbol = f"{symbol}_IRT" if not symbol.endswith("_IRT") else symbol
                base_en = "Tether" if symbol == "USDT" else symbol
                base_fa = "تتر" if symbol == "USDT" else symbol
                name_en = f"{base_en} (Toman)"
                name_fa = f"{base_fa} (تومان)"

                out[out_symbol] = {
                    "symbol": out_symbol,
                    "name": name_fa,
                    "name_en": name_en,
                    "price": str(price_f),
                    "unit": "تومان",
                    "change_percent": change_f,
                    "category": "currency",
                    "source": "tetherland",
                    "buy_price": buy_f,
                    "sell_price": sell_f,
                    "last24h": self._safe_float(item.get("last24h")),
                    "last24h_min": self._safe_float(item.get("last24hMin")),
                    "last24h_max": self._safe_float(item.get("last24hMax")),
                    "last7d_min": self._safe_float(item.get("last7dMin")),
                    "last7d_max": self._safe_float(item.get("last7dMax")),
                    "last30d_min": self._safe_float(item.get("last30dMin")),
                    "last30d_max": self._safe_float(item.get("last30dMax")),
                }
        except Exception as e:
            logger.debug(f"Tetherland processing failed: {e}")
        return out

    def _is_primary_api_format(self, data: Any) -> bool:
        if not isinstance(data, dict):
            return False

        # Accept common primary API shapes (case-insensitive keys)
        indicators = {"gold", "currency", "crypto", "digital_currency", "arz", "tala", "sekke"}
        try:
            for k in data.keys():
                if str(k).strip().lower() in indicators:
                    return True
        except Exception as e:
            logger.debug(f"Error checking API indicators: {e}")

        # Heuristic: lists of dict items with common fields
        try:
            for _, v in data.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    sample = v[0]
                    if any(f in sample for f in ("symbol", "price", "unit", "name_fa", "name_en", "p", "c")):
                        return True
                if isinstance(v, dict) and self._looks_like_currency_item(v):
                    return True
        except Exception as e:
            logger.debug(f"Error in API heuristic check: {e}")
        
        return False

    def _process_primary_api_format(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for category_name, category_data in data.items():
            if isinstance(category_data, list):
                for item in category_data:
                    cur = self._process_single_currency_primary(item, str(category_name))
                    if cur:
                        out[cur["symbol"]] = cur
            elif isinstance(category_data, dict):
                if self._looks_like_currency_item(category_data):
                    cur = self._process_single_currency_primary(category_data, str(category_name))
                    if cur:
                        out[cur["symbol"]] = cur
                else:
                    for sub_key, sub_data in category_data.items():
                        if isinstance(sub_data, list):
                            for item in sub_data:
                                cur = self._process_single_currency_primary(item, f"{category_name}_{sub_key}")
                                if cur:
                                    out[cur["symbol"]] = cur
        return out

    def _process_single_currency_primary(self, item: Any, category: str) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None

        symbol = self._extract_field(item, [
            "symbol", "Symbol", "SYMBOL", "code", "Code", "currency_code", "Currency_Code", "name_en", "Name_En"
        ])
        if not symbol:
            return None
        symbol = str(symbol).upper().strip()
        if not symbol:
            return None

        price = self._extract_field(item, [
            "price", "Price", "value", "Value", "rate", "Rate", "sell", "Sell", "buy", "Buy", "last_price", "Last_Price"
        ], default="0")

        price_f = self._safe_float(price)
        if price_f is None:
            return None
        price = price_f
        change = self._extract_field(item, [
            "change_percent", "Change_Percent", "change", "Change", "daily_change", "Daily_Change", "percent_change_24h"
        ], default="0")

        ch_f = self._safe_float(change)
        change = ch_f if ch_f is not None else 0.0
        unit = self._extract_field(item, [
            "unit", "Unit", "currency", "Currency", "base_currency", "Base_Currency", "quote_currency", "Quote_Currency"
        ], default="Toman")

        name_fa = self._extract_field(item, [
            "name_fa", "Name_Fa", "name", "Name", "title", "Title", "full_name", "Full_Name"
        ])
        name_en = self._extract_field(item, [
            "name_en", "Name_En", "english_name", "English_Name"
        ])
        if not name_fa and not name_en:
            name_fa = self._get_currency_name_by_symbol(symbol)
        name = name_fa or name_en or symbol

        currency = {
            "symbol": symbol,
            "name": str(name),
            "name_en": str(name_en) if name_en else "",
            "price": str(price),
            "unit": str(unit),
            "change_percent": str(change),
            "category": category,
            "timestamp": time.time(),
            "source": "primary_api",
        }
        return currency if self._validate_currency_data(currency) else None

    def _process_backup_api_format(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for key in ("crypto", "fiat"):
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict) and item.get("symbol"):
                        sym = str(item["symbol"]).upper().strip()
                        if sym:
                            out[sym] = item
        return out


    def _looks_like_coingecko_simple_price(self, data: Dict[str, Any]) -> bool:
        # Expected: {"bitcoin": {"usd": 123, "usd_24h_change": 1.2}, ...}
        try:
            if not data:
                return False
            sample_key = next(iter(data.keys()))
            v = data.get(sample_key)
            if not isinstance(v, dict):
                return False
            return ("usd" in v) or ("usd_24h_change" in v)
        except Exception:
            return False

    def _process_coingecko_simple_price(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        id_to_symbol = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "binancecoin": "BNB",
            "cardano": "ADA",
            "solana": "SOL",
            "polkadot": "DOT",
            "dogecoin": "DOGE",
            "avalanche-2": "AVAX",
            "polygon": "MATIC",
            "chainlink": "LINK",
        }

        out: Dict[str, Dict[str, Any]] = {}
        for cid, payload in data.items():
            if not isinstance(payload, dict):
                continue
            sym = id_to_symbol.get(str(cid).strip().lower())
            if not sym:
                # Unknown id -> skip (keep predictable set)
                continue

            price = payload.get("usd")
            if price is None:
                continue

            change = payload.get("usd_24h_change", 0) or 0
            try:
                price_f = float(price)
            except Exception:
                continue

            try:
                change_f = float(change)
            except Exception:
                change_f = 0.0

            out[sym] = {
                "symbol": sym,
                "name": self._get_currency_name_by_symbol(sym),
                "price": str(price_f),
                "unit": "USD",
                "change_percent": str(change_f),
                "category": "crypto",
                "source": "coingecko",
            }

        return out

    def _process_exchangerate_api(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        # Example: {"base_code":"USD","rates":{"EUR":0.91,...}}
        rates = data.get("rates") or {}
        base = str(data.get("base_code") or data.get("base") or "USD").upper().strip()

        # Convert rates so that "price" means 1 unit of currency in base currency.
        # If base=USD and rates["EUR"]=0.91 (1 USD = 0.91 EUR) => 1 EUR = 1/0.91 USD.
        out: Dict[str, Dict[str, Any]] = {}
        common = {"USD", "EUR", "GBP", "TRY", "AED", "CAD", "AUD", "JPY", "CHF", "CNY"}
        for sym, r in rates.items():
            sym_u = str(sym).upper().strip()
            if sym_u not in common:
                continue
            try:
                r_f = float(r)
            except Exception:
                continue
            if r_f <= 0:
                continue

            if sym_u == base:
                price_in_base = 1.0
            else:
                # 1 base = r sym => 1 sym = 1/r base
                price_in_base = 1.0 / r_f

            out[sym_u] = {
                "symbol": sym_u,
                "name": self._get_currency_name_by_symbol(sym_u),
                "price": str(price_in_base),
                "unit": base,
                "change_percent": "0",
                "category": "fiat",
                "source": "exchangerate-api",
            }

        return out

    def _process_generic_format(self, data: Any) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        items = self._extract_items_generic(data)
        for item in items:
            cur = self._process_single_currency_generic(item)
            if cur and self._validate_currency_data(cur):
                out[cur["symbol"]] = cur
        return out

    def _extract_items_generic(self, data: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            for _, v in data.items():
                if isinstance(v, list):
                    items.extend([x for x in v if isinstance(x, dict)])
                elif isinstance(v, dict) and self._looks_like_currency_item(v):
                    items.append(v)
        elif isinstance(data, list):
            items.extend([x for x in data if isinstance(x, dict)])
        return items

    def _process_single_currency_generic(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        symbol = self._extract_field(item, ["symbol", "Symbol", "code", "Code"])
        if not symbol:
            return None

        sym = str(symbol).upper().strip()
        price = self._extract_field(item, ["price", "Price", "value", "Value", "rate", "Rate"], default=0)
        price_f = self._safe_float(price)
        if price_f is None:
            return None
        price = price_f
        change = self._extract_field(item, ["change_percent", "change", "Change"], default=0)
        ch_f = self._safe_float(change)
        change = ch_f if ch_f is not None else 0.0
        unit = self._extract_field(item, ["unit", "Unit", "currency", "Currency"], default="USD")
        name = self._get_currency_name_by_symbol(sym)

        return {
            "symbol": sym,
            "name": name,
            "price": str(price),
            "unit": str(unit),
            "change_percent": str(change),
            "timestamp": time.time(),
            "source": "generic",
        }

    def _looks_like_currency_item(self, item: Dict[str, Any]) -> bool:
        essentials = (("symbol", "price"), ("Symbol", "Price"), ("code", "value"), ("name_en", "price"))
        return any(all(k in item for k in pair) for pair in essentials)

    def _extract_field(self, data: Dict[str, Any], field_names: Sequence[str], default: Any = None) -> Any:
        for name in field_names:
            if name in data:
                val = data.get(name)
                if val is not None and str(val).strip() != "":
                    return val
        return default

    def _validate_currency_data(self, currency: Dict[str, Any]) -> bool:
        for key in ("symbol", "name", "price", "unit"):
            if not str(currency.get(key, "")).strip():
                return False

        price_f = self._safe_float(currency.get("price"))
        if price_f is None:
            return False
        # store normalized numeric string (UI formatting will re-apply separators)
        currency["price"] = str(price_f)

        ch_f = self._safe_float(currency.get("change_percent", 0) or 0)
        if ch_f is None:
            currency["change_percent"] = "0"
        else:
            currency["change_percent"] = str(ch_f)
        return True


    def _get_currency_name_by_symbol(self, symbol: str) -> str:
        # Keep this map compact but useful for Iranian users
        currency_map = {
            "USD": "دلار آمریکا",
            "EUR": "یورو",
            "GBP": "پوند انگلیس",
            "AED": "درهم امارات",
            "TRY": "لیر ترکیه",
            "CNY": "یوان چین",
            "SAR": "ریال عربستان",
            "IQD": "دینار عراق",
            "AFN": "افغانی افغانستان",

            "BTC": "بیت کوین",
            "ETH": "اتریوم",
            "BNB": "بایننس کوین",
            "XRP": "ریپل",
            "SOL": "سولانا",
            "ADA": "کاردانو",
            "DOGE": "دوج کوین",

            "GOLD": "طلا",
            "SILVER": "نقره",
            "SEKEH": "سکه طلا",
            "GERAM18": "گرم طلای ۱۸ عیار",
            "GERAM24": "گرم طلای ۲۴ عیار",
            "MESGHAL": "مثقال طلا",
            "OUNCE": "اونس طلا",
        }
        return currency_map.get(symbol, symbol)

    @staticmethod
    def get_fallback_data() -> Dict[str, Dict[str, Any]]:
        now = time.time()
        return {
            "USD": {"symbol": "USD", "name": "دلار آمریکا", "price": "57250", "unit": "تومان", "change_percent": "1.24", "timestamp": now, "source": "fallback"},
            "EUR": {"symbol": "EUR", "name": "یورو", "price": "62180", "unit": "تومان", "change_percent": "-0.68", "timestamp": now, "source": "fallback"},
            "GBP": {"symbol": "GBP", "name": "پوند انگلیس", "price": "72340", "unit": "تومان", "change_percent": "2.15", "timestamp": now, "source": "fallback"},
            "BTC": {"symbol": "BTC", "name": "بیت کوین", "price": "97543", "unit": "USD", "change_percent": "3.45", "timestamp": now, "source": "fallback"},
            "ETH": {"symbol": "ETH", "name": "اتریوم", "price": "3892", "unit": "USD", "change_percent": "5.23", "timestamp": now, "source": "fallback"},
            "GOLD": {"symbol": "GOLD", "name": "طلا", "price": "2234", "unit": "USD/oz", "change_percent": "0.89", "timestamp": now, "source": "fallback"},
            "SEKEH": {"symbol": "SEKEH", "name": "سکه طلا", "price": "28500000", "unit": "تومان", "change_percent": "2.50", "timestamp": now, "source": "fallback"},
            "GERAM18": {"symbol": "GERAM18", "name": "گرم طلای ۱۸ عیار", "price": "2870000", "unit": "تومان", "change_percent": "1.80", "timestamp": now, "source": "fallback"},
        }

    # ---------------------------------------------------------------------
    # History (Crypto) via CoinGecko
    # ---------------------------------------------------------------------

    _COINGECKO_ID_MAP: Dict[str, str] = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "BNB": "binancecoin",
        "ADA": "cardano",
        "SOL": "solana",
        "DOT": "polkadot",
        "DOGE": "dogecoin",
        "AVAX": "avalanche-2",
        "MATIC": "polygon",
        "LINK": "chainlink",
    }

    def fetch_crypto_history(self, symbol: str, *, period_seconds: int) -> List[Tuple[float, float]]:
        """Return (ts_seconds, price) points for supported crypto symbols."""
        sym = str(symbol or "").upper().strip()
        coin_id = self._COINGECKO_ID_MAP.get(sym)
        if not coin_id:
            return []

        # CoinGecko expects days; clamp to a reasonable range to keep it fast.
        try:
            days = int(max(1, min(90, math.ceil(float(period_seconds) / 86400.0))))
        except Exception:
            days = 1

        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": str(days), "interval": "hourly"}
        try:
            r = self.session.get(url, params=params, timeout=config.API_TIMEOUT, verify=config.VERIFY_SSL)
            if r.status_code != 200:
                return []
            payload = r.json() if r.content else {}
            prices = payload.get("prices") or []
            points: List[Tuple[float, float]] = []
            for item in prices:
                try:
                    ts_ms = float(item[0])
                    price = float(item[1])
                    points.append((ts_ms / 1000.0, price))
                except Exception:
                    continue
            return points
        except Exception:
            return []


# Crypto tickers this app already knows how to fetch live spot prices for
# (see APIManager._COINGECKO_ID_MAP above), plus USDT itself. Used to route
# forward-price-modal clicks on these symbols to a real-time-rate label
# instead of a forward-price label, since crypto has no "tomorrow" market.
CRYPTO_SYMBOLS = set(APIManager._COINGECKO_ID_MAP.keys()) | {"USDT"}


class ForwardPriceService:
    """Forward ("fardaee") price data for the assets in FORWARD_PRICE_ASSETS
    (gold/coins, the global ounce, and a fixed list of fiat currencies),
    plus a real-time USDT/IRT rate used both to label USD's own popup
    honestly (there's no live forward-USD quote anymore) and to answer
    clicks on crypto cards, which show a live rate rather than a forward
    price -- crypto has no meaningful "tomorrow" market.

    Sources, in the order each asset type actually tries them:
      - alanchand.com's currency and gold/coin tables -- one request each,
        covers every fiat and gold/coin symbol this app tracks.
      - api.navasan.tech for a genuine forward USD rate (usd_farda_buy/
        sell). Needs a free key from @navasan_contact_bot on Telegram, set
        as config.NAVASAN_API_KEY; skipped entirely without one.
      - bonbast.amirhn.com, a community-maintained mirror of bonbast.com's
        rate table, as a fallback for the USD reference rate.
      - tgju.org's per-asset profile pages (BeautifulSoup), as a fallback
        for gold/coins if alanchand is ever unreachable.
      - api.tetherland.com for the USDT/IRT rate, with Nobitex's USDT/IRT
        order-book price as a live fallback.
      - a standard forex API for USD cross-rates, used as a last resort to
        estimate any fiat currency alanchand doesn't list.

    Deliberately not implemented, and not going to be: solving Cloudflare's
    bot challenge or any equivalent bot-detection bypass (e.g. a paid
    "scrape via headless browser" relay), for TGJU or anything else. TGJU
    doesn't need it -- plain requests already work -- and the general
    policy stands regardless of source: if a site actively blocks even a
    well-formed request, the fallback chain carries the weight, not
    further escalation.
    """

    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
    }

    BONBAST_PROXY_URL = "https://bonbast.amirhn.com/latest"
    TETHERLAND_URL = config.TETHERLAND_API_URL
    NOBITEX_ORDERBOOK_URL = "https://api.nobitex.ir/v2/orderbook/USDTIRT"
    GLOBAL_CROSS_RATE_URL = "https://api.exchangerate-api.com/v4/latest/USD"
    TGJU_PROFILE_URL = "https://www.tgju.org/profile/{slug}"
    ALANCHAND_CURRENCIES_URL = "https://alanchand.com/en/currencies-price"
    ALANCHAND_GOLD_URL = "https://alanchand.com/en/gold-price"
    NAVASAN_API_URL = "http://api.navasan.tech/latest/"

    # Row label on alanchand's gold/coin table, per asset. Prices there are
    # in Rial; XAUUSD is the only one already in USD (global ounce price).
    ALANCHAND_GOLD_ROWS: Dict[str, str] = {
        "IR_GOLD_MELTED": "Raw 24K Gold (Mesghal)",
        "IR_GOLD_18K": "18K Gold per Gram",
        "IR_COIN_EMAMI": "Full Coin (Imami)",
        "IR_COIN_BAHAR": "Bahar Azadi Coin",
        "IR_COIN_HALF": "Half Coin",
        "IR_COIN_QUARTER": "Quarter Coin",
        "IR_COIN_1G": "gram sekke",
        "XAUUSD": "Gold Ounce to US Dollar",
    }

    # Row label per fiat symbol on alanchand's currency table, without the
    # "100 " prefix some rows use -- _split_unit_multiplier strips that off
    # the scraped label automatically, so it doesn't need to be listed here.
    ALANCHAND_CURRENCY_NAMES: Dict[str, str] = {
        "USD": "US Dollar",
        "EUR": "Euro",
        "AED": "UAE Dirham",
        "GBP": "British Pound",
        "TRY": "Turkish Lira",
        "CNY": "Chinese Yuan",
        "CAD": "Canadian Dollar",
        "AUD": "Australian Dollar",
        "RUB": "Russian Ruble",
        "IQD": "Iraqi Dinar",
        "MYR": "Malaysian Ringgit",
        "GEL": "Georgian Lari",
        "AZN": "Azerbaijani Manat",
        "AMD": "Armenian Dram",
        "THB": "Thai Baht",
        "OMR": "Omani Rial",
        "INR": "Indian Rupee",
        "PKR": "Pakistani Rupee",
        "JPY": "Japanese Yen",
        "SAR": "Saudi Riyal",
        "AFN": "Afghan Afghani",
        "SEK": "Swedish Krona",
        "CHF": "Swiss Franc",
        "QAR": "Qatari Riyal",
        "KWD": "Kuwaiti Dinar",
        "BHD": "Bahraini Dinar",
        "SYP": "Syrian Pound",
    }

    # Ordered candidate slugs per asset. "sekee" turned out to price a
    # full coin (~1.88B against an 18k/24k gram rate of ~189M/252M, which
    # only lines up with a ~8.1g full coin, not a 1-gram one) -- it was
    # originally assigned to IR_COIN_1G by mistake and belongs to
    # IR_COIN_EMAMI instead. IR_COIN_1G and IR_COIN_BAHAR's real slugs
    # are still unconfirmed; the candidates below are best guesses.
    TGJU_SLUG_CANDIDATES: Dict[str, Tuple[str, ...]] = {
        "IR_GOLD_18K": ("geram18",),
        "IR_GOLD_24K": ("geram24",),
        "IR_GOLD_MELTED": ("mesghal", "gold_ab_shodeh"),
        "XAUUSD": ("ons",),
        "IR_COIN_1G": ("sekee_1g", "gerami", "sekee_gerami"),
        "IR_COIN_QUARTER": ("rob",),
        "IR_COIN_HALF": ("nim",),
        "IR_COIN_EMAMI": ("sekee", "sekee_emami"),
        "IR_COIN_BAHAR": ("azadi1", "sekee_azadi", "azadi"),
    }

    BONBAST_COIN_FALLBACK_KEYS = {
        "emami1": "IR_COIN_EMAMI",
        "azadi1g": "IR_COIN_1G",
        "azadi1_22": "IR_COIN_BAHAR",
        "nim": "IR_COIN_HALF",
        "rob": "IR_COIN_QUARTER",
    }

    PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
    NOISE_WORDS = ("تومان", "ریال", "درهم", ",", "٬")

    CACHE_TTL_SECONDS = 120  # forward/real-time quotes are cached briefly, not per-frame
    NAVASAN_MONTHLY_BUDGET = 130  # ~4 calls/day * 31 days, with a little slack -- see NAVASAN_MIN_INTERVAL_SECONDS
    NAVASAN_DAILY_BUDGET = 6  # keeps one heavy testing day from burning the whole month
    NAVASAN_MIN_INTERVAL_SECONDS = 6 * 3600  # the actual throttle: this API is good for once every 6h, not a call-count

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.BROWSER_HEADERS)
        self._cache: Dict[str, Any] = {}
        self._cache_ts: Dict[str, float] = {}
        self.resolved_tgju_slugs: Dict[str, str] = {}  # asset -> slug that actually worked, for diagnostics

    def _cached(self, key: str) -> Any:
        ts = self._cache_ts.get(key)
        if ts is not None and (time.time() - ts) < self.CACHE_TTL_SECONDS:
            return self._cache.get(key)
        return None

    def _store(self, key: str, value: Any) -> Any:
        self._cache[key] = value
        self._cache_ts[key] = time.time()
        return value

    def _normalize_persian_number(self, text: str) -> Optional[float]:
        """Convert Persian digits to ASCII and strip currency words/commas
        before parsing a scraped price string to float."""
        if not text:
            return None
        cleaned = text.strip()
        for i, digit in enumerate(self.PERSIAN_DIGITS):
            cleaned = cleaned.replace(digit, str(i))
        for word in self.NOISE_WORDS:
            cleaned = cleaned.replace(word, "")
        cleaned = re.sub(r"[^\d.\-]", "", cleaned)
        return self._safe_float(cleaned)

    def fetch_bonbast_spot_rates(self) -> Optional[Dict[str, float]]:
        """Fiat spot rates from bonbast.amirhn.com, a community-maintained
        open JSON mirror of bonbast.com (see the class docstring's caveat
        about this being an unverified third party). Tries both the
        '/latest' path and the bare root, since I can't confirm from here
        which one is actually correct."""
        cached = self._cached("bonbast")
        if cached is not None:
            return cached
        for url in (self.BONBAST_PROXY_URL, "https://bonbast.amirhn.com/"):
            try:
                response = self.session.get(url, timeout=config.API_TIMEOUT)
                response.raise_for_status()
                payload = response.json()
                rates = {k: v for k, v in ((k, self._safe_float(v)) for k, v in payload.items()) if v is not None}
                if rates:
                    return self._store("bonbast", rates)
                logger.debug(f"Bonbast proxy at {url} returned no parseable rates: {response.text[:200]!r}")
            except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError, AttributeError) as e:
                logger.debug(f"Bonbast proxy fetch failed for {url}: {e}")
        return None

    def _scrape_tgju_profile(self, asset: str) -> Optional[float]:
        """Multi-candidate extraction against tgju.org profile pages: try
        each slug candidate for this asset in order, and within each page
        try a couple of known CSS patterns before falling back to a plain
        text search for a table row labeled with the usual "current rate"
        phrasing."""
        for slug in self.TGJU_SLUG_CANDIDATES.get(asset, ()):
            try:
                response = self.session.get(
                    self.TGJU_PROFILE_URL.format(slug=slug), timeout=config.API_TIMEOUT
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                candidate = (
                    soup.select_one('span[data-col="info.last_trade.PDrCotVal"]')
                    or soup.select_one('span[data-col="info.last_trade.c"]')
                    or soup.select_one(".profile-price-box .price")
                    or soup.select_one(".tgju-current-price")
                )
                if candidate is None:
                    title = soup.select_one("h1.title")
                    if title is not None and title.find_next("span") is not None:
                        candidate = title.find_next("span")

                value = self._normalize_persian_number(candidate.get_text()) if candidate else None
                if value is None:
                    label_markers = ("نرخ فعلی", "نرخ روز", "فروش")
                    for row in soup.select("tr"):
                        cells = row.find_all("td")
                        if len(cells) < 2:
                            continue
                        if any(marker in cells[0].get_text() for marker in label_markers):
                            value = self._normalize_persian_number(cells[1].get_text())
                            if value:
                                break

                if value:
                    self.resolved_tgju_slugs[asset] = slug
                    return value
            except (requests.exceptions.RequestException, AttributeError) as e:
                logger.debug(f"tgju.org profile scrape failed for '{slug}' ({asset}): {e}")
                continue
        return None

    def fetch_tgju_gold_and_coins(self) -> Optional[Dict[str, float]]:
        """Gold/coin spot prices from tgju.org's per-asset profile pages,
        falling back to bonbast's own coin keys for anything tgju didn't
        return.

        TGJU displays domestic prices in Rial, not Toman (1 Toman = 10
        Rial) -- this app displays everything in Toman, so every asset
        here except XAUUSD (a global, USD-denominated price) gets divided
        by 10 right after scraping. Bonbast's own fallback values are
        already in Toman and are left as-is.
        """
        cached = self._cached("tgju_gold")
        if cached is not None:
            return cached

        values: Dict[str, float] = {}
        for asset in self.TGJU_SLUG_CANDIDATES:
            price = self._scrape_tgju_profile(asset)
            if price is not None:
                values[asset] = price if asset == "XAUUSD" else price / 10.0

        for asset, price in (self._fetch_gold_coins_from_bonbast() or {}).items():
            values.setdefault(asset, price)

        return self._store("tgju_gold", values) if values else None

    def _fetch_gold_coins_from_bonbast(self) -> Optional[Dict[str, float]]:
        rates = self.fetch_bonbast_spot_rates()
        if not rates:
            return None
        values = {
            asset: rates[src_key]
            for src_key, asset in self.BONBAST_COIN_FALLBACK_KEYS.items()
            if rates.get(src_key)
        }
        return values or None

    @staticmethod
    def _split_unit_multiplier(label: str) -> Tuple[str, float]:
        """'100 Iraqi Dinar' -> ('Iraqi Dinar', 100.0); plain names pass through unchanged."""
        label = label.strip()
        m = re.match(r"^(\d+)\s+(.+)$", label)
        if m:
            return m.group(2).strip(), float(m.group(1))
        return label, 1.0

    def fetch_alanchand_currency_rates(self) -> Optional[Dict[str, float]]:
        """Fiat buy prices (Toman) scraped from alanchand.com's currency
        table. One request covers every fiat symbol this app tracks, so
        this is tried before the bonbast + global-cross-rate fallback."""
        cached = self._cached("alanchand_currencies")
        if cached is not None:
            return cached

        name_to_symbol = {v: k for k, v in self.ALANCHAND_CURRENCY_NAMES.items()}
        values: Dict[str, float] = {}
        try:
            response = self.session.get(self.ALANCHAND_CURRENCIES_URL, timeout=config.API_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for row in soup.select("table tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                name, multiplier = self._split_unit_multiplier(cells[0].get_text(strip=True))
                symbol = name_to_symbol.get(name)
                if not symbol or symbol in values:
                    continue
                buy_rial = self._safe_float(cells[1].get_text(strip=True))
                if not buy_rial:
                    continue
                values[symbol] = (buy_rial / multiplier) / 10.0  # Rial -> Toman
        except (requests.exceptions.RequestException, AttributeError) as e:
            logger.debug(f"alanchand currency table fetch failed: {e}")

        return self._store("alanchand_currencies", values) if values else None

    def fetch_alanchand_gold_and_coins(self) -> Optional[Dict[str, float]]:
        """Gold/coin/ounce prices scraped from alanchand.com's gold table --
        one request instead of one tgju.org profile page per asset."""
        cached = self._cached("alanchand_gold")
        if cached is not None:
            return cached

        row_to_symbol = {v: k for k, v in self.ALANCHAND_GOLD_ROWS.items()}
        values: Dict[str, float] = {}
        try:
            response = self.session.get(self.ALANCHAND_GOLD_URL, timeout=config.API_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for row in soup.select("table tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                symbol = row_to_symbol.get(cells[0].get_text(strip=True))
                if not symbol:
                    continue
                m = re.match(r"^([\d,]+(?:\.\d+)?)", cells[1].get_text(strip=True))
                price = self._safe_float(m.group(1)) if m else None
                if not price:
                    continue
                values[symbol] = price if symbol == "XAUUSD" else price / 10.0
        except (requests.exceptions.RequestException, AttributeError) as e:
            logger.debug(f"alanchand gold table fetch failed: {e}")

        return self._store("alanchand_gold", values) if values else None

    def _navasan_budget_ok(self) -> bool:
        """Two caps, both persisted in the local database so they survive
        app restarts: a daily one (stops a single busy day from burning
        the month) and a monthly one (the real ceiling, under Navasan's
        120-calls/month free tier). A call only goes through if both
        still have room; each counter resets on its own since the key
        carries the date/month."""
        try:
            day_key = "navasan_calls_day_" + time.strftime("%Y-%m-%d")
            month_key = "navasan_calls_" + time.strftime("%Y-%m")
            used_today = int(db_manager.load_preference(day_key, 0) or 0)
            used_month = int(db_manager.load_preference(month_key, 0) or 0)
            if used_today >= self.NAVASAN_DAILY_BUDGET or used_month >= self.NAVASAN_MONTHLY_BUDGET:
                return False
            db_manager.save_preference(day_key, used_today + 1)
            db_manager.save_preference(month_key, used_month + 1)
            return True
        except Exception:
            return True

    def _fetch_worker_navasan(self) -> Optional[Dict[str, Any]]:
        """Same shared Cloudflare Worker as APIManager talks to (see
        cf-worker/), just fetched independently since this class has its
        own session/cache. The worker is what actually enforces the 6h
        spacing across every install -- this only reuses whatever it last
        fetched, cached here for CACHE_TTL_SECONDS like everything else
        in this class."""
        base = str(getattr(config, "WORKER_BASE_URL", "") or "").strip().rstrip("/")
        if not base:
            return None
        cached = self._cached("worker_envelope")
        if cached is not None:
            return cached
        try:
            response = self.session.get(f"{base}/prices", timeout=config.API_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                mapped = {"navasan": data.get("navasan", {})}
                return self._store("worker_envelope", mapped)
        except (requests.exceptions.RequestException, json.JSONDecodeError, AttributeError) as e:
            logger.debug(f"Worker fetch failed for forward-price service: {e}")
        return None

    @staticmethod
    def _parse_navasan_farda(payload: Dict[str, Any]) -> Optional[float]:
        buy = ForwardPriceService._safe_float((payload.get("usd_farda_buy") or {}).get("value"))
        sell = ForwardPriceService._safe_float((payload.get("usd_farda_sell") or {}).get("value"))
        values = [v for v in (buy, sell) if v]
        return sum(values) / len(values) if values else None

    def fetch_navasan_usd_farda(self) -> Optional[float]:
        """Genuine forward ('farda') USD/Toman rate from Navasan's API --
        needs a free key from @navasan_contact_bot on Telegram, set as
        config.NAVASAN_API_KEY. Returns None (silently) until a key is
        configured, so the Tether-derived estimate keeps working as-is.

        Navasan's free tier is good for one request every 6 hours, not a
        raw monthly call count -- this now tracks the last successful
        fetch's timestamp in the database (not just the in-memory cache
        above) and won't call again inside that window even across app
        restarts. When a worker is configured, this reads its value
        instead: the worker is the one actually holding to the 6h
        spacing across every install, not just this one.
        """
        envelope = self._fetch_worker_navasan()
        if envelope:
            value = self._parse_navasan_farda(envelope.get("navasan") or {})
            if value:
                return value

        api_key = str(getattr(config, "NAVASAN_API_KEY", "") or "").strip()
        if not api_key:
            return None

        cached = self._cached("navasan_farda")
        if cached is not None:
            return cached

        last_ts = float(db_manager.load_preference("navasan_last_fetch_ts", 0) or 0)
        if time.time() - last_ts < self.NAVASAN_MIN_INTERVAL_SECONDS:
            # Still inside the 6h window -- reuse whatever was stored last
            # time rather than calling again, even across restarts.
            stored = self._safe_float(db_manager.load_preference("navasan_last_value", None))
            return self._store("navasan_farda", stored) if stored else None

        if not self._navasan_budget_ok():
            logger.debug("Navasan monthly call budget reached; skipping.")
            return None

        try:
            response = self.session.get(
                self.NAVASAN_API_URL,
                params={"api_key": api_key, "item": "usd_farda_buy,usd_farda_sell"},
                timeout=config.API_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json() or {}
            avg = self._parse_navasan_farda(payload)
            if avg:
                # Navasan already quotes Toman for this item, not Rial.
                db_manager.save_preference("navasan_last_fetch_ts", time.time())
                db_manager.save_preference("navasan_last_value", avg)
                return self._store("navasan_farda", avg)
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.debug(f"Navasan farda fetch failed: {e}")
        return None

    def fetch_tetherland_usdt_irt(self) -> Optional[float]:
        """USDT/IRT rate from Tetherland's public currencies endpoint
        (already used elsewhere in this app -- see config.TETHERLAND_API_URL).
        The exact response shape is a best-effort guess covering the couple
        of layouts Tetherland's API has used publicly; if it returns
        something else entirely this falls through to Nobitex."""
        cached = self._cached("tetherland")
        if cached is not None:
            return cached
        try:
            response = self.session.get(self.TETHERLAND_URL, timeout=config.API_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            entries = payload.get("currencies", payload) if isinstance(payload, dict) else payload

            if isinstance(entries, list):
                for entry in entries:
                    if str(entry.get("code") or entry.get("symbol") or "").upper() == "USDT":
                        value = self._safe_float(entry.get("price") or entry.get("sell") or entry.get("toman"))
                        if value:
                            return self._store("tetherland", value)
            elif isinstance(entries, dict):
                usdt_entry = entries.get("USDT") or entries.get("usdt")
                if isinstance(usdt_entry, dict):
                    value = self._safe_float(usdt_entry.get("price") or usdt_entry.get("sell"))
                else:
                    value = self._safe_float(usdt_entry)
                if value:
                    return self._store("tetherland", value)
            logger.debug(f"Tetherland response had no recognizable USDT entry: {response.text[:300]!r}")
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.debug(f"Tetherland fetch failed: {e}")
        return None

    def fetch_nobitex_usdt_irt(self) -> Optional[float]:
        """USDT/IRT order-book price -- fallback for get_usdt_irt_rate()
        when Tetherland is unavailable."""
        cached = self._cached("nobitex")
        if cached is not None:
            return cached
        try:
            response = self.session.get(self.NOBITEX_ORDERBOOK_URL, timeout=config.API_TIMEOUT)
            response.raise_for_status()
            asks = (response.json() or {}).get("asks") or []
            if asks:
                price_rial = self._safe_float(asks[0][0])
                if price_rial:
                    return self._store("nobitex", price_rial / 10.0)  # rial -> toman
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError, IndexError) as e:
            logger.debug(f"Nobitex order-book fetch failed: {e}")
        return None

    def get_usdt_irt_rate(self) -> Optional[float]:
        """Best-available USDT/IRT rate: Tetherland first, Nobitex's
        order-book price as a live fallback. Used for USDT's own popup,
        for every other crypto symbol's popup (both labeled as a
        real-time rate, never "forward"), and as the USD anchor for
        deriving other fiat currencies' estimates when Bonbast is down."""
        value = self.fetch_tetherland_usdt_irt()
        if value:
            return value
        return self.fetch_nobitex_usdt_irt()

    def get_usd_reference_toman(self) -> Optional[float]:
        """Best-available USD-equivalent Toman rate: alanchand's own
        currency table first, then Bonbast's usd1, then the USDT/IRT rate.
        This is what USD's own popup shows (explicitly labeled as a
        Tether-derived rate, not a forward price -- see mixin_sections.py)
        and what every other fiat currency's estimate is derived from below."""
        rates = self.fetch_alanchand_currency_rates()
        if rates and rates.get("USD"):
            return rates["USD"]
        bonbast = self.fetch_bonbast_spot_rates()
        if bonbast and bonbast.get("usd1"):
            return bonbast["usd1"]
        return self.get_usdt_irt_rate()

    def get_melted_gold_toman(self) -> Optional[float]:
        gold_coins = self.fetch_alanchand_gold_and_coins() or self.fetch_tgju_gold_and_coins()
        return gold_coins.get("IR_GOLD_MELTED") if gold_coins else None

    def get_global_cross_rate(self, currency_code: str) -> Optional[float]:
        """USD-to-`currency_code` cross rate (1 USD = N units of the target
        currency), used to derive an estimate for non-USD currencies."""
        cached = self._cached(f"cross_{currency_code}")
        if cached is not None:
            return cached
        try:
            response = self.session.get(self.GLOBAL_CROSS_RATE_URL, timeout=config.API_TIMEOUT)
            response.raise_for_status()
            rates = (response.json() or {}).get("rates", {})
            value = self._safe_float(rates.get(currency_code.upper()))
            if value:
                return self._store(f"cross_{currency_code}", value)
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Global cross-rate fetch failed for {currency_code}: {e}")
        return None

    def get_global_xau_usd(self) -> Optional[float]:
        """Global ounce price (XAU/USD), from tgju.org's dedicated ounce
        profile page."""
        cached = self._cached("xau")
        if cached is not None:
            return cached
        value = self._scrape_tgju_profile("XAUUSD")
        return self._store("xau", value) if value else None

    def get_usd_forward_price(self) -> Tuple[Optional[float], bool]:
        """USD forward price plus whether it's a genuine forward ('farda')
        rate from Navasan, or the Tether-derived estimate used when no
        Navasan key is configured (or its monthly budget is used up).
        The popup in mixin_sections.py uses the flag to label itself
        honestly instead of always claiming to show a Tether substitute."""
        farda = self.fetch_navasan_usd_farda()
        if farda:
            return farda, True
        return self.get_usd_reference_toman(), False

    def compute_forward_price(self, asset_symbol: str) -> Optional[float]:
        """Forward/best-available price (Toman) for one whitelisted
        fiat/gold asset. Returns None for anything not in
        FORWARD_PRICE_ASSETS -- callers should check that whitelist before
        calling this at all; it's re-checked here too so a stale call
        site can't accidentally reach an out-of-scope asset."""
        sym = asset_symbol.upper().strip()
        if sym not in FORWARD_PRICE_ASSETS:
            return None

        if sym == "USD":
            price, _ = self.get_usd_forward_price()
            return price

        if sym in self.ALANCHAND_GOLD_ROWS or sym in self.TGJU_SLUG_CANDIDATES:
            gold_coins = self.fetch_alanchand_gold_and_coins() or self.fetch_tgju_gold_and_coins()
            direct = gold_coins.get(sym) if gold_coins else None
            if direct is not None:
                return direct

        fiat_rates = self.fetch_alanchand_currency_rates()
        if fiat_rates and sym in fiat_rates:
            return fiat_rates[sym]

        usd_reference = self.get_usd_reference_toman()
        cross_rate = self.get_global_cross_rate(sym)
        if not usd_reference or not cross_rate:
            return None
        return usd_reference / cross_rate

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None


forward_price_service = ForwardPriceService()