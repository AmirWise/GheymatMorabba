"""Entry point: single-instance guard, startup diagnostics, mainloop."""

from __future__ import annotations

import sys
from tkinter import messagebox

import customtkinter as ctk
import pyglet
import requests

from core.config import config
from core.utils import logger, IS_WINDOWS, PYWINSTYLES_AVAILABLE, acquire_single_instance_lock, notify_running_instance
from core.theme import theme_manager
from ui.app import MainWindow


def run_system_diagnostics() -> None:
    print("=" * 80)
    print("Gheymat Morabba Price Tracker — Diagnostics")
    print("=" * 80)
    print(f"OS: {sys.platform}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Version: {config.APP_VERSION}")
    print(f"CustomTkinter: {getattr(ctk, '__version__', 'unknown')}")
    print(f"Requests: {getattr(requests, '__version__', 'unknown')}")
    print(f"Pyglet: {getattr(pyglet, 'version', 'unknown')}")
    if IS_WINDOWS:
        print(f"PyWinStyles: {'Available' if PYWINSTYLES_AVAILABLE else 'Not available'}")
    if not config.BRSAPI_KEY and not config.WORKER_BASE_URL:
        print()
        print("WARNING: BRSAPI_KEY is not set and no WORKER_BASE_URL is configured.")
        print("         Live market data will not load until one of them is.")
        print("         See README.md > Configuration for how to set BRSAPI_KEY.")
    print("=" * 80)
    print()


def main() -> None:
    lock_socket = acquire_single_instance_lock()
    if lock_socket is None:
        notify_running_instance()
        logger.info("Another instance is already running; focused it instead of opening a new window.")
        return

    try:
        run_system_diagnostics()
        theme_manager.load()
        app = MainWindow()
        app.start_single_instance_listener(lock_socket)
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        try:
            messagebox.showerror("Critical Error", f"Application failed:\n\n{e}")
        except Exception:
            pass
        raise
    finally:
        try:
            lock_socket.close()
        except Exception:
            pass
        logger.info("Session ended")


if __name__ == "__main__":
    main()
