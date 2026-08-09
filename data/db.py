"""SQLite persistence: cached currency snapshots, user preferences,
per-mode portfolios, price history, and desktop-widget layout."""

from __future__ import annotations

import json
import sqlite3
import time

from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple
from core.utils import logger


class DatabaseManager:
    """SQLite store for cache + preferences."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                try:
                    # WAL lets background worker threads read while another writes,
                    # instead of blocking/erroring under the app's concurrent access pattern.
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                except Exception:
                    pass
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS currency_cache (
                        symbol TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_preferences (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS selected_currencies (
                        symbol TEXT PRIMARY KEY,
                        added_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS portfolio_symbols (
                        symbol TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        added_at REAL NOT NULL,
                        PRIMARY KEY(symbol, mode)
                    )
                """)
                try:
                    migrated = conn.execute("SELECT COUNT(*) FROM portfolio_symbols").fetchone()[0]
                    legacy_rows = conn.execute("SELECT symbol, added_at FROM selected_currencies").fetchall()
                    if not migrated and legacy_rows:
                        conn.executemany(
                            "INSERT OR IGNORE INTO portfolio_symbols(symbol, mode, added_at) VALUES (?, 'normal', ?)",
                            legacy_rows,
                        )
                except Exception:
                    pass
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS price_history (
                        symbol TEXT NOT NULL,
                        ts REAL NOT NULL,
                        price REAL NOT NULL,
                        PRIMARY KEY(symbol, ts)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS desktop_widgets (
                        widget_id TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Database init failed: {e}")

    # ----- cache -----

    def cache_bulk_currency_data(self, currencies: Dict[str, Dict[str, Any]]) -> None:
        """Cache the latest dataset for faster startup."""
        try:
            now = time.time()
            rows = [(sym, json.dumps(data, ensure_ascii=False), now) for sym, data in currencies.items()]
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO currency_cache(symbol, data, timestamp) VALUES (?, ?, ?)",
                    rows,
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Bulk cache write failed: {e}")

    def load_cached_currencies(self, max_age_seconds: int = 6 * 3600) -> Dict[str, Dict[str, Any]]:
        """Load cached dataset (not expired)."""
        try:
            cutoff = time.time() - max_age_seconds
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT symbol, data, timestamp FROM currency_cache WHERE timestamp >= ?",
                    (cutoff,),
                )
                out: Dict[str, Dict[str, Any]] = {}
                for sym, raw, ts in cursor.fetchall():
                    try:
                        item = json.loads(raw)
                        if isinstance(item, dict):
                            item.setdefault("symbol", sym)
                            item.setdefault("timestamp", ts)
                            out[sym] = item
                    except Exception:
                        continue
                return out
        except Exception as e:
            logger.debug(f"Load cached currencies failed: {e}")
            return {}

    def prune_cache(self, keep_last_seconds: int = 24 * 3600) -> None:
        """Delete old cache rows (or clear all if keep_last_seconds<=0)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if keep_last_seconds <= 0:
                    conn.execute("DELETE FROM currency_cache")
                else:
                    cutoff = time.time() - keep_last_seconds
                    conn.execute("DELETE FROM currency_cache WHERE timestamp < ?", (cutoff,))
                conn.commit()
        except Exception as e:
            logger.debug(f"Cache prune failed: {e}")

    # ----- preferences -----

    def save_preference(self, key: str, value: Any) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO user_preferences(key, value) VALUES (?, ?)",
                    (str(key), json.dumps(value, ensure_ascii=False)),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Preference save failed: {e}")

    def load_preference(self, key: str, default: Any = None) -> Any:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT value FROM user_preferences WHERE key = ?",
                    (str(key),),
                )
                row = cursor.fetchone()
            if row is None:
                return default
            raw = row[0]
            try:
                return json.loads(raw)
            except Exception:
                return raw
        except Exception as e:
            logger.debug(f"Preference load failed: {e}")
            return default

    # ----- portfolio -----

    def save_selected_currencies(self, currencies: Iterable[str], mode: str = "normal") -> None:
        mode = str(mode or "normal").strip().lower()
        try:
            symbols = sorted({str(s).upper().strip() for s in currencies if str(s).strip()})
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM portfolio_symbols WHERE mode = ?", (mode,))
                conn.executemany(
                    "INSERT INTO portfolio_symbols(symbol, mode, added_at) VALUES (?, ?, ?)",
                    [(sym, mode, time.time()) for sym in symbols],
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Selected currencies save failed: {e}")

    def load_selected_currencies(self, mode: str = "normal") -> Set[str]:
        mode = str(mode or "normal").strip().lower()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT symbol FROM portfolio_symbols WHERE mode = ?", (mode,))
                return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.debug(f"Selected currencies load failed: {e}")
            return set()


    # ----- history -----

    def insert_price_history_bulk(self, rows: Sequence[Tuple[str, float, float]]) -> None:
        """Insert (symbol, ts, price) rows. Safe to call often; runs quickly with executemany."""
        if not rows:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO price_history(symbol, ts, price) VALUES (?, ?, ?)",
                    [(str(sym).upper().strip(), float(ts), float(price)) for sym, ts, price in rows],
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"History bulk insert failed: {e}")

    def load_price_history(self, symbol: str, *, since_ts: float, limit: int = 2000) -> List[Tuple[float, float]]:
        sym = str(symbol or "").upper().strip()
        if not sym:
            return []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT ts, price FROM price_history WHERE symbol = ? AND ts >= ? ORDER BY ts ASC LIMIT ?",
                    (sym, float(since_ts), int(max(1, limit))),
                )
                return [(float(ts), float(price)) for ts, price in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"History load failed: {e}")
            return []

    def prune_price_history(self, keep_days: int = 14) -> None:
        try:
            keep_days = int(max(1, keep_days))
            cutoff = time.time() - keep_days * 86400
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM price_history WHERE ts < ?", (float(cutoff),))
                conn.commit()
        except Exception as e:
            logger.debug(f"History prune failed: {e}")

    # ----- desktop widgets -----

    def save_desktop_widget(self, widget_id: str, data: Dict[str, Any]) -> None:
        wid = str(widget_id or "").strip()
        if not wid:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO desktop_widgets(widget_id, data, created_at) VALUES (?, ?, ?)",
                    (wid, json.dumps(dict(data or {}), ensure_ascii=False), time.time()),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Widget save failed: {e}")

    def delete_desktop_widget(self, widget_id: str) -> None:
        wid = str(widget_id or "").strip()
        if not wid:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM desktop_widgets WHERE widget_id = ?", (wid,))
                conn.commit()
        except Exception as e:
            logger.debug(f"Widget delete failed: {e}")

    def load_desktop_widgets(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT widget_id, data FROM desktop_widgets ORDER BY created_at ASC")
                out: List[Dict[str, Any]] = []
                for wid, raw in cursor.fetchall():
                    try:
                        item = json.loads(raw)
                        if isinstance(item, dict):
                            item.setdefault("widget_id", wid)
                            out.append(item)
                    except Exception:
                        continue
                return out
        except Exception as e:
            logger.debug(f"Widgets load failed: {e}")
            return []


from core.config import config

db_manager = DatabaseManager(config.DATABASE_PATH)
