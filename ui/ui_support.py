"""Window vibrancy effects, performance counters, and toast notifications."""


from __future__ import annotations

import customtkinter as ctk
import time

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from core.utils import IS_WINDOWS, PYWINSTYLES_AVAILABLE, pywinstyles, logger
from datetime import timedelta
from core.config import config
from core.theme import theme_manager


# ==========================================================================
# Window vibrancy effects
# ==========================================================================

class VisualEffectsManager:
    """Windows effects with safe fallbacks (no-op on non-Windows)."""

    def __init__(self, window: ctk.CTk):
        self.window = window
        self.current_effect = "normal"
        self.transparency_level = 1.0
        self.is_applying = False

    def reset_to_normal(self) -> None:
        try:
            if IS_WINDOWS and PYWINSTYLES_AVAILABLE:
                pywinstyles.apply_style(self.window, "normal")  # type: ignore[name-defined]
            self.window.attributes("-alpha", 1.0)
            self.window.update_idletasks()
            self.current_effect = "normal"
            self.transparency_level = 1.0
        except Exception:
            pass

    def apply_liquid_glass_effect(self) -> None:
        self._apply_windows_style(
            target="liquid_glass",
            candidates=[("acrylic", 0.97), ("mica", 0.96), ("blur", 0.95), ("aero", 0.94)],
            simulation_alpha=0.985,
        )

    def apply_crystal_mode(self) -> None:
        self._apply_windows_style(
            target="crystal",
            candidates=[("optimised", 0.89), ("acrylic", 0.88), ("blur", 0.90)],
            simulation_alpha=0.985,
        )


    def apply_paper_mode(self) -> None:
        """Solid, clean look (no transparency / glass)."""
        if self.is_applying:
            return
        self.is_applying = True
        try:
            # reset_to_normal already clears styles on Windows + restores alpha
            self.reset_to_normal()
            try:
                self.window.attributes("-alpha", 1.0)
            except Exception:
                pass
            self.current_effect = "paper"
            self.transparency_level = 1.0
        finally:
            self.is_applying = False

    def apply_paper_noir_mode(self) -> None:
        """Dark solid look (paper style in dark mode)."""
        if self.is_applying:
            return
        self.is_applying = True
        try:
            self.reset_to_normal()
            try:
                self.window.attributes("-alpha", 1.0)
            except Exception:
                pass
            self.current_effect = "paper_noir"
            self.transparency_level = 1.0
        finally:
            self.is_applying = False


    def _apply_windows_style(
        self,
        target: str,
        candidates: Sequence[Tuple[str, float]],
        simulation_alpha: float,
    ) -> None:
        if self.is_applying:
            return

        self.is_applying = True
        try:
            self.reset_to_normal()

            if not (IS_WINDOWS and PYWINSTYLES_AVAILABLE):
                self.window.attributes("-alpha", simulation_alpha)
                self.current_effect = f"{target}_simulation"
                self.transparency_level = simulation_alpha
                return

            for style_name, alpha in candidates:
                try:
                    pywinstyles.apply_style(self.window, style_name)  # type: ignore[name-defined]
                    self.window.attributes("-alpha", alpha)
                    self.window.update_idletasks()
                    self.current_effect = target
                    self.transparency_level = alpha
                    return
                except Exception:
                    continue

            # fallback
            self.window.attributes("-alpha", simulation_alpha)
            self.current_effect = f"{target}_simulation"
            self.transparency_level = simulation_alpha
        finally:
            self.is_applying = False

    def get_current_effect_info(self) -> Dict[str, Any]:
        return {
            "effect": self.current_effect,
            "transparency": self.transparency_level,
            "supported": bool(IS_WINDOWS and PYWINSTYLES_AVAILABLE),
        }


# ==========================================================================
# Performance counters
# ==========================================================================

class PerformanceMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.metrics = {
            "ui_updates": 0,
            "api_calls": 0,
            "cache_loads": 0,
            "errors": 0,
        }

    def inc(self, key: str) -> None:
        if key in self.metrics:
            self.metrics[key] += 1

    def report(self) -> Dict[str, Any]:
        runtime = max(0.001, time.time() - self.start_time)
        return {
            "runtime_seconds": runtime,
            "runtime_formatted": str(timedelta(seconds=int(runtime))),
            "metrics": dict(self.metrics),
            "ui_updates_per_min": self.metrics["ui_updates"] / (runtime / 60.0),
        }


performance_monitor = PerformanceMonitor()


# ==========================================================================
# Toast notifications
# ==========================================================================

class ToastManager:
    """Stackable toast notifications (top-right)."""

    def __init__(
        self,
        root: ctk.CTk,
        *,
        font_getter: Optional[Callable[[int, bool], Tuple[Any, ...]]] = None,
        rtl: bool = False,
    ):
        self.root = root
        self._toasts: List[ctk.CTkFrame] = []
        self.max_toasts = 3
        self.offset_x = 16
        self.offset_y = 16
        self.gap = 10

        self.font_getter = font_getter or (lambda size, bold=False: (config.FALLBACK_FONT, size, "bold") if bold else (config.FALLBACK_FONT, size))
        self.rtl = rtl

    def set_typography(
        self,
        *,
        font_getter: Optional[Callable[[int, bool], Tuple[Any, ...]]] = None,
        rtl: Optional[bool] = None,
    ) -> None:
        if font_getter is not None:
            self.font_getter = font_getter
        if rtl is not None:
            self.rtl = rtl

    def show(self, message: str, duration: int = 2800) -> None:
        try:
            toast = ctk.CTkFrame(
                self.root,
                fg_color=(theme_manager.colors.glass_overlay_light, theme_manager.colors.glass_overlay_dark),
                corner_radius=12,
                border_width=1,
                border_color=(theme_manager.colors.border_light, theme_manager.colors.border_dark),
            )
            label = ctk.CTkLabel(
                toast,
                text=message,
                font=self.font_getter(13, False),
                text_color=(theme_manager.colors.text_primary_light, theme_manager.colors.text_primary_dark),
                anchor="e" if self.rtl else "w",
                justify="right" if self.rtl else "left",
            )
            label.pack(padx=14, pady=10)

            self._toasts.append(toast)
            if len(self._toasts) > self.max_toasts:
                old = self._toasts.pop(0)
                try:
                    old.destroy()
                except Exception:
                    pass

            self._reposition()
            self.root.after(duration, lambda: self._dismiss(toast))
        except Exception as e:
            logger.debug(f"Toast failed: {e}")

    def _dismiss(self, toast: ctk.CTkFrame) -> None:
        try:
            if toast in self._toasts:
                self._toasts.remove(toast)
            toast.destroy()
        except Exception:
            pass
        self._reposition()

    def _reposition(self) -> None:
        try:
            for i, toast in enumerate(reversed(self._toasts)):
                toast.update_idletasks()
                w = toast.winfo_reqwidth()
                h = toast.winfo_reqheight()
                x = self.root.winfo_width() - w - self.offset_x
                y = self.offset_y + i * (h + self.gap)
                toast.place(x=x, y=y)
        except Exception:
            pass
