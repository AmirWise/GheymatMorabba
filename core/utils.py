"""Cross-cutting infrastructure: logging, OS/platform helpers, resource loading, single-instance IPC."""


from __future__ import annotations

import io
import logging
import sys
import ctypes
import customtkinter as ctk
import pyglet
import socket

from typing import Any, Optional
from datetime import datetime
from pathlib import Path
from functools import lru_cache
from core.config import config


# ==========================================================================
# Logging
# ==========================================================================

class LogManager:
    """Builds the application's shared logger. Call ``setup_logging()`` once."""

    @staticmethod
    def setup_logging() -> logging.Logger:
        logger = logging.getLogger("GheymatMorabba")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()

        try:
            wrapped_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            console_handler = logging.StreamHandler(wrapped_stdout)
        except Exception:
            console_handler = logging.StreamHandler(sys.stdout)

        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(console_handler)

        try:
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)

            # Prune old log files so a long-running install doesn't accumulate
            # one file per day forever.
            try:
                cutoff = datetime.now().timestamp() - (14 * 24 * 3600)
                for old_log in log_dir.glob("Gheymat_Morabbat_*.log"):
                    try:
                        if old_log.stat().st_mtime < cutoff:
                            old_log.unlink()
                    except Exception:
                        continue
            except Exception:
                pass

            file_handler = logging.FileHandler(
                log_dir / f"Gheymat_Morabbat_{datetime.now().strftime('%Y%m%d')}.log",
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
            ))
            logger.addHandler(file_handler)
        except Exception:
            pass  # File logging is nice-to-have, never fatal.

        return logger


logger = LogManager.setup_logging()


# ==========================================================================
# Platform detection & Windows helpers
# ==========================================================================

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

PYWINSTYLES_AVAILABLE = False
pywinstyles: Any = None
if IS_WINDOWS:
    try:
        import pywinstyles  # type: ignore
        PYWINSTYLES_AVAILABLE = True
    except Exception:
        pywinstyles = None
        PYWINSTYLES_AVAILABLE = False

try:
    import aiohttp  # type: ignore
    AIOHTTP_AVAILABLE = True
except Exception:
    aiohttp = None  # type: ignore
    AIOHTTP_AVAILABLE = False


def configure_utf8_console() -> None:
    """Best-effort UTF-8 console encoding (helps on some Windows terminals)."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def apply_dark_titlebar(window: Any, dark: bool) -> None:
    """Best-effort dark native title bar on Windows 10 (2004+) / Windows 11.
    No-op everywhere else, and never raises."""
    if not IS_WINDOWS:
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20 on modern builds, 19 on early ones)
            try:
                res = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
                if res == 0:
                    break
            except Exception:
                continue
    except Exception:
        pass


def apply_window_shape_region(window: Any, width: int, height: int, radius: Optional[int] = None) -> None:
    """Mask a Toplevel to a real circular (radius >= min(w,h)//2) or rounded-rect
    OS-level window shape on Windows, via SetWindowRgn. This is the only way to
    truly eliminate a rectangular artifact behind a "floating" round/rounded
    widget — a flat background color can approximate a solid backdrop, but can
    never match a live blurred/acrylic backdrop, since Tk has no real per-pixel
    alpha. No-op (graceful rectangular fallback) on non-Windows platforms."""
    if not IS_WINDOWS:
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        r = int(radius) if radius is not None else int(min(width, height) // 2)
        r = max(1, r)
        region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, int(width) + 1, int(height) + 1, r, r)
        if region:
            ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
    except Exception:
        pass


# ==========================================================================
# Font/icon resource loading
# ==========================================================================

class ResourceManager:
    """Resource loading with caching, PyInstaller friendly."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get_resource_path(relative_path: str) -> Path:
        try:
            base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        except Exception:
            base_path = Path(__file__).resolve().parent.parent
        return base_path / relative_path

    @lru_cache(maxsize=32)
    def load_font(self, font_path: str) -> bool:
        """Load a font file so Tk/CustomTkinter can use it reliably on Windows."""
        try:
            full_path = self.get_resource_path(font_path)
            if not full_path.exists():
                return False

            # 1) Register for Tk / CustomTkinter
            try:
                ctk.FontManager.load_font(str(full_path))
            except Exception:
                pass

            # 2) Private font registration on Windows (no system install required)
            if IS_WINDOWS:
                try:
                    FR_PRIVATE = 0x10
                    gdi32 = ctypes.windll.gdi32
                    user32 = ctypes.windll.user32
                    gdi32.AddFontResourceExW(str(full_path), FR_PRIVATE, 0)
                    try:
                        user32.SendMessageW(0xFFFF, 0x001D, 0, 0)  # WM_FONTCHANGE
                    except Exception:
                        pass
                except Exception:
                    pass

            # 3) Keep pyglet registration as a harmless fallback
            try:
                pyglet.font.add_file(str(full_path))
            except Exception:
                pass

            logger.info(f"Font loaded: {font_path}")
            return True
        except Exception as e:
            logger.debug(f"Font load failed for {font_path}: {e}")
            return False

    @lru_cache(maxsize=16)
    def load_icon(self, icon_path: str) -> Optional[str]:
        try:
            full_path = self.get_resource_path(icon_path)
            if full_path.exists():
                return str(full_path)
        except Exception:
            pass
        return None

    def cleanup_resources(self) -> None:
        try:
            self.load_font.cache_clear()
            self.load_icon.cache_clear()
        except Exception:
            pass


resource_manager = ResourceManager()


# ==========================================================================
# Single-instance IPC
# ==========================================================================

def acquire_single_instance_lock() -> Optional[socket.socket]:
    """Bind a fixed loopback port as an exclusive single-instance lock.

    Returns the bound, listening socket on success (keep it open for the
    life of the process), or None if another instance already holds it.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        sock.bind(("127.0.0.1", config.SINGLE_INSTANCE_PORT))
        sock.listen(4)
        sock.settimeout(0.5)
        return sock
    except OSError:
        return None
    except Exception:
        return None


def notify_running_instance() -> bool:
    """Ask an already-running instance to restore and focus itself."""
    try:
        with socket.create_connection(("127.0.0.1", config.SINGLE_INSTANCE_PORT), timeout=1.5) as conn:
            conn.sendall(config.SINGLE_INSTANCE_TOKEN.encode("utf-8"))
        return True
    except Exception:
        return False