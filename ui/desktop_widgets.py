"""Always-on-top desktop widgets: config, window placement, tray icon, the widget window itself, and the manager that tracks them."""


from __future__ import annotations

import uuid
import ctypes
import os
import threading
import time
import tkinter as tk

from dataclasses import dataclass

from typing import Any, Callable, Dict, List, Optional, Tuple
from core.config import config
from core.utils import IS_WINDOWS, logger, resource_manager
from data.db import db_manager
from ui.widgets import CurrencyCardWidget


# ==========================================================================
# Widget config
# ==========================================================================

@dataclass
class DesktopWidgetConfig:
    widget_id: str
    widget_type: str = "price"  # price | movers | portfolio
    symbol: str = "USD"
    x: int = 80
    y: int = 80
    width: int = config.WIDGET_WIDTH
    height: int = config.WIDGET_HEIGHT
    opacity: float = config.WIDGET_DEFAULT_OPACITY

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DesktopWidgetConfig":
        src = dict(d or {})
        return DesktopWidgetConfig(
            widget_id=str(src.get("widget_id") or uuid.uuid4().hex[:10]),
            widget_type=str(src.get("widget_type") or "price"),
            symbol=str(src.get("symbol") or "USD").upper().strip(),
            x=int(src.get("x") or 80),
            y=int(src.get("y") or 80),
            width=int(src.get("width") or config.WIDGET_WIDTH),
            height=int(src.get("height") or config.WIDGET_HEIGHT),
            opacity=float(src.get("opacity") or config.WIDGET_DEFAULT_OPACITY),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "widget_id": self.widget_id,
            "widget_type": self.widget_type,
            "symbol": self.symbol,
            "x": int(self.x),
            "y": int(self.y),
            "width": int(self.width),
            "height": int(self.height),
            "opacity": float(self.opacity),
        }


# ==========================================================================
# Window placement helpers
# ==========================================================================

class DesktopWindowHelper:
    """Windows-only helper to pin a Tk window to the desktop (behind all apps)."""

    @staticmethod
    def is_supported() -> bool:
        return bool(IS_WINDOWS)

    @staticmethod
    def _get_workerw() -> Optional[int]:
        if not IS_WINDOWS:
            return None

        try:
            user32 = ctypes.windll.user32
            progman = user32.FindWindowW("Progman", None)
            if not progman:
                return None

            # Ask Progman to spawn a WorkerW behind the desktop icons
            result = ctypes.c_ulong()
            user32.SendMessageTimeoutW(
                progman,
                0x052C,
                0,
                0,
                0,
                1000,
                ctypes.byref(result),
            )

            workerw = ctypes.c_void_p()

            def enum_proc(hwnd, lparam):
                nonlocal workerw
                shell = user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
                if shell:
                    # Get the WorkerW behind the icons
                    w = user32.FindWindowExW(0, hwnd, "WorkerW", None)
                    if w:
                        workerw = ctypes.c_void_p(w)
                return True

            # EnumWindows callback
            cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows(cb_type(enum_proc), 0)

            if workerw and workerw.value:
                return int(workerw.value)
            return int(progman)
        except Exception:
            return None

    @staticmethod
    def _set_toolwindow(hwnd: int) -> None:
        if not IS_WINDOWS:
            return
        try:
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_NOACTIVATE = 0x08000000

            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex = ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            ex = ex & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
        except Exception:
            pass

    @staticmethod
    def _send_to_bottom(hwnd: int) -> None:
        if not IS_WINDOWS:
            return
        try:
            user32 = ctypes.windll.user32
            HWND_BOTTOM = 1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        except Exception:
            pass

    @staticmethod
    def attach_to_desktop(hwnd: int) -> bool:
        """Re-parent the window to the desktop worker window and keep it behind other apps."""
        if not IS_WINDOWS:
            return False
        try:
            user32 = ctypes.windll.user32
            parent = DesktopWindowHelper._get_workerw()
            if not parent:
                return False
            DesktopWindowHelper._set_toolwindow(hwnd)
            user32.SetParent(hwnd, int(parent))
            DesktopWindowHelper._send_to_bottom(hwnd)
            return True
        except Exception:
            return False


    @staticmethod
    def is_desktop_foreground() -> bool:
        """Return True if foreground window is desktop (Progman/WorkerW/taskbar). Windows-only."""
        if not IS_WINDOWS:
            return True
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return True

            try:
                shell_hwnd = user32.GetShellWindow()
                if shell_hwnd and int(hwnd) == int(shell_hwnd):
                    return True
            except Exception:
                pass

            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
            cls = (buf.value or "").strip()

            return cls in {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
        except Exception:
            return True


# ==========================================================================
# System tray icon
# ==========================================================================

class WinTrayIcon:
    """Minimal Windows tray icon (no external dependencies)."""

    def __init__(self, app: Any):
        self.app = app
        self._thread: Optional[threading.Thread] = None
        self._hwnd: Optional[int] = None
        self._running = False
        self._msg_id = 0x400 + 91
        self._icon_added = False
        self._hicon: Optional[int] = None
        try:
            icon_path = resource_manager.load_icon("assets/icons/icon.ico")
        except Exception:
            icon_path = None
        self._icon_path = icon_path

    def _load_custom_hicon(self):
        """Load the app's real .ico file as a small HICON for the tray/window
        class, falling back to the default system icon if it's unavailable."""
        user32 = ctypes.windll.user32
        if self._icon_path:
            try:
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x00000010
                LR_DEFAULTSIZE = 0x00000040
                handle = user32.LoadImageW(
                    None, str(self._icon_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
                )
                if handle:
                    return handle
            except Exception:
                pass
        return user32.LoadIconW(None, 32512)  # IDI_APPLICATION fallback

    def start(self) -> None:
        if not IS_WINDOWS:
            return
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="TrayIcon", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not IS_WINDOWS:
            return
        self._running = False
        try:
            if self._hwnd:
                ctypes.windll.user32.PostMessageW(int(self._hwnd), 0x0010, 0, 0)  # WM_CLOSE
        except Exception:
            pass

    def show_icon(self) -> None:
        self._add_icon()

    def hide_icon(self) -> None:
        self._remove_icon()

    def _run_loop(self) -> None:
        if not IS_WINDOWS:
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Set WinAPI signatures (prevents 64-bit overflow issues in callbacks)
        try:
            from ctypes import wintypes as _w
            if not hasattr(_w, "LRESULT"):
                _w.LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long

            PTR_SIZE = ctypes.sizeof(ctypes.c_void_p)
            WPARAM_T = ctypes.c_uint64 if PTR_SIZE == 8 else ctypes.c_uint32
            LPARAM_T = ctypes.c_int64 if PTR_SIZE == 8 else ctypes.c_int32
            LRESULT_T = ctypes.c_int64 if PTR_SIZE == 8 else ctypes.c_int32

            user32.DefWindowProcW.argtypes = [_w.HWND, _w.UINT, WPARAM_T, LPARAM_T]
            user32.DefWindowProcW.restype = LRESULT_T

            user32.CreatePopupMenu.argtypes = []
            user32.CreatePopupMenu.restype = _w.HMENU

            user32.AppendMenuW.argtypes = [_w.HMENU, _w.UINT, _w.UINT_PTR, _w.LPCWSTR]
            user32.AppendMenuW.restype = _w.BOOL

            user32.TrackPopupMenu.argtypes = [_w.HMENU, _w.UINT, _w.INT, _w.INT, _w.INT, _w.HWND, _w.LPCRECT]
            user32.TrackPopupMenu.restype = _w.UINT

            user32.DestroyMenu.argtypes = [_w.HMENU]
            user32.DestroyMenu.restype = _w.BOOL

            user32.GetCursorPos.argtypes = [ctypes.c_void_p]
            user32.GetCursorPos.restype = _w.BOOL

            user32.SetForegroundWindow.argtypes = [_w.HWND]
            user32.SetForegroundWindow.restype = _w.BOOL

            user32.PostQuitMessage.argtypes = [ctypes.c_int]
            user32.PostQuitMessage.restype = None
        except Exception:
            pass
        from ctypes import wintypes

        # Compatibility: some Python/Windows builds omit these aliases in ctypes.wintypes
        if not hasattr(wintypes, "HCURSOR"):
            wintypes.HCURSOR = wintypes.HANDLE
        if not hasattr(wintypes, "HICON"):
            wintypes.HICON = wintypes.HANDLE
        if not hasattr(wintypes, "LRESULT"):
            wintypes.LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        WM_DESTROY = 0x0002
        WM_COMMAND = 0x0111
        WM_RBUTTONUP = 0x0205
        WM_LBUTTONDBLCLK = 0x0203

        IDM_SHOW = 1001
        IDM_EXIT = 1002

        PTR_SIZE = ctypes.sizeof(ctypes.c_void_p)
        WPARAM_T = ctypes.c_uint64 if PTR_SIZE == 8 else ctypes.c_uint32
        LPARAM_T = ctypes.c_int64 if PTR_SIZE == 8 else ctypes.c_int32
        LRESULT_T = ctypes.c_int64 if PTR_SIZE == 8 else ctypes.c_int32

        WNDPROCTYPE = ctypes.WINFUNCTYPE(LRESULT_T, wintypes.HWND, wintypes.UINT, WPARAM_T, LPARAM_T)

        @WNDPROCTYPE
        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == self._msg_id:
                    lp = int(lparam) if lparam else 0
                    if lp == WM_LBUTTONDBLCLK:
                        try:
                            self.app._enqueue_ui(self.app._show_from_tray)
                        except Exception:
                            pass
                        return 0

                    if lp == WM_RBUTTONUP:
                        try:
                            menu = user32.CreatePopupMenu()
                            show_label = "باز کردن" if getattr(self.app, "language", "fa") == "fa" else "Open"
                            exit_label = "خروج" if getattr(self.app, "language", "fa") == "fa" else "Exit"
                            user32.AppendMenuW(menu, 0, IDM_SHOW, show_label)
                            user32.AppendMenuW(menu, 0, IDM_EXIT, exit_label)

                            pt = POINT()
                            user32.GetCursorPos(ctypes.byref(pt))
                            user32.SetForegroundWindow(hwnd)
                            cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0002, pt.x, pt.y, 0, hwnd, None)
                            user32.DestroyMenu(menu)

                            if cmd == IDM_SHOW:
                                self.app._enqueue_ui(self.app._show_from_tray)
                            elif cmd == IDM_EXIT:
                                self.app._enqueue_ui(self.app._exit_from_tray)
                        except Exception:
                            pass
                        return 0

                if msg == WM_COMMAND:
                    return 0

                if msg == WM_DESTROY:
                    try:
                        self._remove_icon()
                    except Exception:
                        pass
                    try:
                        user32.PostQuitMessage(0)
                    except Exception:
                        pass
                    return 0
            except Exception:
                pass

            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        hinst = kernel32.GetModuleHandleW(None)
        cls_name = f"GheymatMorabbaTray_{os.getpid()}"

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROCTYPE),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HCURSOR),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = wndproc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        self._hicon = self._load_custom_hicon()
        wc.hIcon = self._hicon
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = cls_name

        try:
            user32.RegisterClassW(ctypes.byref(wc))
        except Exception:
            pass

        hwnd = user32.CreateWindowExW(0, cls_name, cls_name, 0, 0, 0, 0, 0, 0, 0, hinst, None)
        self._hwnd = int(hwnd) if hwnd else None

        msg = wintypes.MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        try:
            if hwnd:
                user32.DestroyWindow(hwnd)
        except Exception:
            pass
        try:
            user32.UnregisterClassW(cls_name, hinst)
        except Exception:
            pass

    def _add_icon(self) -> None:
        if not IS_WINDOWS:
            return
        if self._icon_added:
            return
        hwnd = self._hwnd
        if not hwnd:
            return

        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("hWnd", ctypes.c_void_p),
                ("uID", ctypes.c_uint),
                ("uFlags", ctypes.c_uint),
                ("uCallbackMessage", ctypes.c_uint),
                ("hIcon", ctypes.c_void_p),
                ("szTip", ctypes.c_wchar * 128),
            ]

        NIM_ADD = 0x00000000
        NIF_MESSAGE = 0x00000001
        NIF_ICON = 0x00000002
        NIF_TIP = 0x00000004

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = ctypes.c_void_p(int(hwnd))
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = self._msg_id
        nid.hIcon = self._hicon or self._load_custom_hicon()

        tip = "Gheymat Morabba"
        try:
            tip = str(getattr(self.app, "config", config).APP_NAME)
        except Exception:
            pass
        nid.szTip = tip[:127]

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._icon_added = True

    def _remove_icon(self) -> None:
        if not IS_WINDOWS:
            return
        if not self._icon_added:
            return
        hwnd = self._hwnd
        if not hwnd:
            return

        shell32 = ctypes.windll.shell32

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("hWnd", ctypes.c_void_p),
                ("uID", ctypes.c_uint),
                ("uFlags", ctypes.c_uint),
                ("uCallbackMessage", ctypes.c_uint),
                ("hIcon", ctypes.c_void_p),
                ("szTip", ctypes.c_wchar * 128),
            ]

        NIM_DELETE = 0x00000002

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = ctypes.c_void_p(int(hwnd))
        nid.uID = 1

        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        self._icon_added = False


# ==========================================================================
# Desktop widget window
# ==========================================================================

class DesktopWidgetWindow(tk.Toplevel):
    """Borderless, lightweight desktop widget (Windows).
    - Rounded corners via transparentcolor (true rounded widget)
    - Interactive (drag/remove) when desktop is foreground
    - Hidden automatically when user switches to other apps (never overlays apps)
    """

    _DESKTOP_CHECK_MS = 420
    _DATA_TICK_MS = 900
    _REVEAL_GRACE_SECONDS = 6.0

    def __init__(
        self,
        app: Any,
        cfg: DesktopWidgetConfig,
        *,
        on_remove: Callable[[str], None],
        on_moved: Optional[Callable[[DesktopWidgetConfig], None]] = None,
    ):
        super().__init__(app)

        self.app = app
        self.cfg = cfg
        self._on_remove = on_remove
        self._on_moved = on_moved

        self._drag_dx = 0
        self._drag_dy = 0
        self._dragging = False

        self._transparent_key = "#ff00ff"  # magenta; used as transparent background on Windows
        self._last_sig: Optional[str] = None
        self._render_cache: Dict[str, Any] = {}
        self._created_at = time.time()

        self.overrideredirect(True)

        try:
            self.attributes("-topmost", False)
        except Exception:
            pass

        try:
            self.attributes("-alpha", float(self.cfg.opacity))
        except Exception:
            pass

        self.geometry(f"{int(self.cfg.width)}x{int(self.cfg.height)}+{int(self.cfg.x)}+{int(self.cfg.y)}")
        self.configure(bg=self._transparent_key)

        # True rounded widget: remove square window corners
        if IS_WINDOWS:
            try:
                self.wm_attributes("-transparentcolor", self._transparent_key)
            except Exception:
                pass

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, relief="flat", bg=self._transparent_key)
        self.canvas.pack(fill="both", expand=True)

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)

        self.canvas.tag_bind("remove_dot", "<Button-1>", self._remove_clicked)
        self.canvas.tag_bind("remove_dot", "<Enter>", lambda e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind("remove_dot", "<Leave>", lambda e: self.canvas.configure(cursor=""))

        self.bind("<Configure>", lambda e: self._redraw(force=True))

        self._redraw(force=True)

        # Window tweaks + periodic ticks
        self.after(60, self._setup_widget_window)

    def _setup_widget_window(self) -> None:
        if IS_WINDOWS:
            try:
                hwnd = int(self.winfo_id())
                DesktopWindowHelper._set_toolwindow(hwnd)
            except Exception:
                pass

        # Immediate data paint (no waiting for next app refresh)
        try:
            currencies = getattr(self.app, "currencies", {}) or {}
            if not currencies:
                try:
                    currencies = db_manager.load_cached_currencies()
                except Exception:
                    currencies = {}
            self.update_from_data(currencies)
        except Exception:
            pass

        self._desktop_visibility_tick()
        self._data_tick()

    def _rounded_rect(self, x1: float, y1: float, x2: float, y2: float, r: float, *, fill: str, outline: str, width: int) -> None:
        r = max(0.0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))

        # fill
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="")
        self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="")
        self.canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=fill, outline="")
        self.canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=fill, outline="")
        self.canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=fill, outline="")
        self.canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=fill, outline="")

        # outline
        if width > 0:
            self.canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="arc", outline=outline, width=width)
            self.canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="arc", outline=outline, width=width)
            self.canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="arc", outline=outline, width=width)
            self.canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="arc", outline=outline, width=width)
            self.canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=width)
            self.canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=width)
            self.canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=width)
            self.canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=width)

    def _redraw(self, *, force: bool = False) -> None:
        w = int(self.winfo_width() or self.cfg.width or config.WIDGET_WIDTH)
        h = int(self.winfo_height() or self.cfg.height or config.WIDGET_HEIGHT)

        self.canvas.delete("all")

        try:
            pal = self.app._widget_palette()
        except Exception:
            pal = {
                "bg": "#0a0a0c",
                "fill": "#151518",
                "border": "#2c2c2e",
                "txt": "#f5f5f7",
                "sub": "#a1a1a6",
                "dot": "#1c1c1e",
                "shine": "#7DA7FF",
                "up": "#32D74B",
                "down": "#FF453A",
            }

        fill = pal.get("fill", "#151518")
        border = pal.get("border", "#2c2c2e")
        txt = pal.get("txt", "#f5f5f7")
        sub = pal.get("sub", "#a1a1a6")
        up = pal.get("up", "#32D74B")
        down = pal.get("down", "#FF453A")

        rtl = bool(getattr(self.app, "rtl", False))

        def anchor_x(left_edge: float, right_edge: float) -> Tuple[str, float]:
            return ("ne", right_edge) if rtl else ("nw", left_edge)

        # Single rounded widget surface (no outer sharp box)
        self._rounded_rect(0, 0, w, h, 20, fill=fill, outline=border, width=1)

        # Glass shine hint
        try:
            shine = pal.get("shine", "#7DA7FF")
            self.canvas.create_line(18, 14, w - 18, 14, fill=shine, width=1)
        except Exception:
            pass

        # Remove dot -- mirrors to the top-left in RTL, matching the
        # remove button placement on the regular currency cards.
        dot_r = 10
        cx = 18 if rtl else (w - 18)
        cy = 18
        dot_fill = pal.get("dot", "#1c1c1e")
        self.canvas.create_oval(cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r, fill=dot_fill, outline=border, width=1, tags=("remove_dot",))
        self.canvas.create_text(cx, cy + 0.5, text="●", fill=txt, font=self.app._ui_font(12, True), tags=("remove_dot",))

        # Content
        t = str(self.cfg.widget_type or "price").lower().strip()
        padx = 18
        y = 36

        if t == "movers":
            title = self.app._t("widget_type_movers")
            a, x = anchor_x(padx, w - padx)
            self.canvas.create_text(x, y, text=title, fill=txt, anchor=a, font=self.app._ui_font(13, True))
            y += 26

            gainers = self._render_cache.get("gainers", [])
            losers = self._render_cache.get("losers", [])

            col_a, gx = anchor_x(padx, w / 2 - 6)
            _, lx = anchor_x(w / 2 + 6, w - padx)

            self.canvas.create_text(gx, y, text=self.app._t("top_gainers"), fill=sub, anchor=col_a, font=self.app._ui_font(11, True))
            self.canvas.create_text(lx, y, text=self.app._t("top_losers"), fill=sub, anchor=col_a, font=self.app._ui_font(11, True))
            y += 20

            lines = max(len(gainers), len(losers), 3)
            for i in range(lines):
                g = gainers[i] if i < len(gainers) else ("—", 0.0)
                l = losers[i] if i < len(losers) else ("—", 0.0)
                self.canvas.create_text(gx, y + i * 18, text=f"{g[0]}  {g[1]:+.2f}%", fill=up, anchor=col_a, font=self.app._ui_font(11, False))
                self.canvas.create_text(lx, y + i * 18, text=f"{l[0]}  {l[1]:+.2f}%", fill=down, anchor=col_a, font=self.app._ui_font(11, False))
            return

        if t == "portfolio":
            title = self.app._t("widget_type_portfolio")
            a, x = anchor_x(padx, w - padx)
            self.canvas.create_text(x, y, text=title, fill=txt, anchor=a, font=self.app._ui_font(13, True))
            y += 28

            total = int(self._render_cache.get("total", 0) or 0)
            best = self._render_cache.get("best", ("—", 0.0))
            worst = self._render_cache.get("worst", ("—", 0.0))
            upd = self._render_cache.get("updated", "—")

            self.canvas.create_text(x, y, text=f"{self.app._t('portfolio_items')}: {total}", fill=txt, anchor=a, font=self.app._ui_font(12, False))
            y += 22
            self.canvas.create_text(x, y, text=f"{self.app._t('best')}: {best[0]}  {float(best[1]):+.2f}%", fill=(up if float(best[1]) >= 0 else down), anchor=a, font=self.app._ui_font(11, False))
            y += 18
            self.canvas.create_text(x, y, text=f"{self.app._t('worst')}: {worst[0]}  {float(worst[1]):+.2f}%", fill=(up if float(worst[1]) >= 0 else down), anchor=a, font=self.app._ui_font(11, False))
            y += 24
            self.canvas.create_text(x, y, text=f"{self.app._t('updated')}: {upd}", fill=sub, anchor=a, font=self.app._ui_font(10, False))
            return

        # price
        sym = str(self.cfg.symbol or "USD").upper().strip()
        title = f"{self.app._t('widget_type_price')}: {sym}"
        a, x = anchor_x(padx, w - padx)
        self.canvas.create_text(x, y, text=title, fill=txt, anchor=a, font=self.app._ui_font(13, True))
        y += 30

        price_str = self._render_cache.get("price_str", "—")
        change_str = self._render_cache.get("change_str", "")
        change_val = float(self._render_cache.get("change_val", 0.0) or 0.0)
        unit = self._render_cache.get("unit", self.app._t("toman"))

        self.canvas.create_text(x, y, text=f"{price_str} {unit}", fill=txt, anchor=a, font=self.app._ui_font(18, True))
        y += 28
        if change_str:
            arrow = "↗" if change_val > 0 else ("↘" if change_val < 0 else "")
            color = up if change_val > 0 else (down if change_val < 0 else sub)
            self.canvas.create_text(x, y, text=f"{arrow} {change_str}".strip(), fill=color, anchor=a, font=self.app._ui_font(12, True))

    def _remove_clicked(self, _event=None) -> None:
        try:
            if callable(self._on_remove):
                self._on_remove(str(self.cfg.widget_id))
        finally:
            try:
                self.destroy()
            except Exception:
                pass

    def _on_drag_start(self, event) -> None:
        # Ignore if click was on remove dot
        try:
            x, y = int(event.x), int(event.y)
            w = int(self.winfo_width() or self.cfg.width or config.WIDGET_WIDTH)
            if x >= w - 32 and y <= 32:
                return
        except Exception:
            pass

        self._dragging = True
        try:
            self._drag_dx = int(event.x)
            self._drag_dy = int(event.y)
        except Exception:
            self._drag_dx = 0
            self._drag_dy = 0

    def _on_drag_move(self, event) -> None:
        if not self._dragging:
            return
        try:
            x = int(self.winfo_x() + (event.x - self._drag_dx))
            y = int(self.winfo_y() + (event.y - self._drag_dy))
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _on_drag_end(self, _event=None) -> None:
        if not self._dragging:
            return
        self._dragging = False

        try:
            self.cfg.x = int(self.winfo_x())
            self.cfg.y = int(self.winfo_y())
        except Exception:
            return

        try:
            if callable(self._on_moved):
                self._on_moved(self.cfg)
        except Exception:
            pass

    def _desktop_visibility_tick(self) -> None:
        if not IS_WINDOWS:
            return

        try:
            on_desktop = DesktopWindowHelper.is_desktop_foreground()
        except Exception:
            on_desktop = True

        in_grace = (time.time() - self._created_at) < self._REVEAL_GRACE_SECONDS

        if on_desktop or in_grace:
            try:
                if str(self.state()) == "withdrawn":
                    self.deiconify()
            except Exception:
                pass

            # Keep above wallpaper/icons but never overlay apps (we hide when apps are focused)
            try:
                self.attributes("-topmost", True)
                self.after(30, lambda: self.attributes("-topmost", False))
            except Exception:
                pass
        else:
            # Keep the widget behind other windows. It will naturally disappear when apps are in front.
            try:
                self.attributes("-topmost", False)
            except Exception:
                pass
            if IS_WINDOWS:
                try:
                    hwnd = int(self.winfo_id())
                    DesktopWindowHelper._send_to_bottom(hwnd)
                except Exception:
                    pass

        self.after(self._DESKTOP_CHECK_MS, self._desktop_visibility_tick)

    def _data_tick(self) -> None:
        try:
            currencies = getattr(self.app, "currencies", {}) or {}
        except Exception:
            currencies = {}

        try:
            t = str(self.cfg.widget_type or "price").lower().strip()
            sig = f"{t}|lang:{getattr(self.app,'language','fa')}"
            if t == "price":
                sym = str(self.cfg.symbol or "").upper().strip()
                d = currencies.get(sym) or {}
                sig = f"price|{sym}|{d.get('price')}|{d.get('change_percent')}|{d.get('unit')}|lang:{getattr(self.app, 'language', 'fa')}"
            elif t == "movers":
                sig = f"movers|{getattr(self.app,'top_gainers',None)}|{getattr(self.app,'top_losers',None)}"
            elif t == "portfolio":
                sig = f"portfolio|{sorted(list(getattr(self.app,'user_portfolio',set()) or []))}|{getattr(self.app,'last_update','')}"
        except Exception:
            sig = None

        if sig is not None and sig != self._last_sig:
            self._last_sig = sig
            try:
                self.update_from_data(currencies)
            except Exception:
                pass

        self.after(self._DATA_TICK_MS, self._data_tick)

    def update_from_data(self, currencies: Dict[str, Dict[str, Any]]) -> None:
        t = str(self.cfg.widget_type or "price").lower().strip()

        if t == "movers":
            gainers = list(getattr(self.app, "top_gainers", []) or [])[:3]
            losers = list(getattr(self.app, "top_losers", []) or [])[:3]
            self._render_cache["gainers"] = [(g[0], float(g[1])) for g in gainers] if gainers else []
            self._render_cache["losers"] = [(l[0], float(l[1])) for l in losers] if losers else []
            self._redraw()
            return

        if t == "portfolio":
            items = list(getattr(self.app, "user_portfolio", set()) or [])
            total = len(items)
            best = ("—", 0.0)
            worst = ("—", 0.0)
            for sym in items:
                d = currencies.get(str(sym).upper().strip()) or {}
                try:
                    ch = float(d.get("change_percent", 0) or 0)
                except Exception:
                    ch = 0.0
                if best[0] == "—" or ch > best[1]:
                    best = (str(sym).upper().strip(), ch)
                if worst[0] == "—" or ch < worst[1]:
                    worst = (str(sym).upper().strip(), ch)

            self._render_cache["total"] = total
            self._render_cache["best"] = best
            self._render_cache["worst"] = worst
            self._render_cache["updated"] = getattr(self.app, "last_update", "—")
            self._redraw()
            return

        # price
        sym = str(self.cfg.symbol or "").upper().strip()
        d = currencies.get(sym) or {}
        price_str = "—"
        unit = d.get("unit") or self.app._t("toman")
        try:
            price_str = CurrencyCardWidget._format_price(float(d.get("price", 0) or 0))
        except Exception:
            pass
        ch_str = ""
        ch_val = 0.0
        try:
            ch_val = float(d.get("change_percent", 0) or 0)
            if abs(ch_val) > 1e-9:
                ch_str = f"{ch_val:+.2f}%"
        except Exception:
            pass

        self._render_cache["price_str"] = price_str
        self._render_cache["change_str"] = ch_str
        self._render_cache["change_val"] = ch_val
        self._render_cache["unit"] = unit
        self._redraw()

    def apply_typography(self) -> None:
        try:
            self._last_sig = None
        except Exception:
            pass
        self._redraw(force=True)


# ==========================================================================
# Desktop widget manager
# ==========================================================================

class DesktopWidgetManager:
    def __init__(self, app: Any):
        self.app = app
        self.widgets: Dict[str, DesktopWidgetWindow] = {}
        self._restore_done = False

    def restore(self) -> None:
        if self._restore_done:
            return
        self._restore_done = True

        if not DesktopWindowHelper.is_supported():
            return

        try:
            saved = db_manager.load_desktop_widgets()
            for item in saved:
                cfg = DesktopWidgetConfig.from_dict(item)
                self._create(cfg, save=False)
        except Exception:
            pass

    def shutdown(self) -> None:
        for wid in list(self.widgets.keys()):
            try:
                self.remove(wid, save=False)
            except Exception:
                pass

    def _create(self, cfg: DesktopWidgetConfig, *, save: bool) -> bool:
        wid = str(cfg.widget_id or uuid.uuid4().hex[:10])
        cfg.widget_id = wid

        try:
            win = DesktopWidgetWindow(self.app, cfg, on_remove=self.remove, on_moved=self._on_widget_moved)
            self.widgets[wid] = win
            if save:
                db_manager.save_desktop_widget(wid, cfg.to_dict())
        except Exception as e:
            logger.warning(f"Desktop widget creation failed for {cfg.widget_type}/{cfg.symbol}: {e}")
            try:
                self.app.toasts.show(f"⚠️ {self.app._t('toast_widget_add_failed')}", duration=3200)
            except Exception:
                pass
            return False

        try:
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
        except Exception:
            pass

        try:
            if hasattr(self.app, "_refresh_widgets_ui"):
                self.app._refresh_widgets_ui()
        except Exception:
            pass

        return True

    def add(self, widget_type: str, symbol: str = "USD") -> None:
        if not DesktopWindowHelper.is_supported():
            try:
                self.app.toasts.show(self.app._t("toast_widget_not_supported"), duration=2600)
            except Exception:
                pass
            return

        base_x = 80 + (len(self.widgets) % 6) * 40
        base_y = 80 + (len(self.widgets) % 6) * 30

        cfg = DesktopWidgetConfig(
            widget_id=uuid.uuid4().hex[:10],
            widget_type=str(widget_type or "price"),
            symbol=str(symbol or "USD").upper().strip(),
            x=base_x,
            y=base_y,
        )
        if self._create(cfg, save=True):
            try:
                self.app.toasts.show(self.app._t("toast_widget_added"), duration=1800)
            except Exception:
                pass
            try:
                if not getattr(self.app, "run_in_background", False):
                    self.app.toasts.show(self.app._t("widgets_persist_hint"), duration=4600)
            except Exception:
                pass

    def remove(self, widget_id: str, *, save: bool = True) -> None:
        wid = str(widget_id or "").strip()
        if not wid:
            return
        win = self.widgets.pop(wid, None)
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        if save:
            try:
                db_manager.delete_desktop_widget(wid)
            except Exception:
                pass
            try:
                self.app.toasts.show(self.app._t("toast_widget_removed"), duration=1800)
            except Exception:
                pass

        try:
            if hasattr(self.app, "_refresh_widgets_ui"):
                self.app._refresh_widgets_ui()
        except Exception:
            pass

    def _on_widget_moved(self, cfg: DesktopWidgetConfig) -> None:
        try:
            db_manager.save_desktop_widget(cfg.widget_id, cfg.to_dict())
        except Exception:
            pass

    def update_all(self, currencies: Dict[str, Dict[str, Any]]) -> None:
        for win in list(self.widgets.values()):
            try:
                win.update_from_data(currencies)
            except Exception:
                continue

    def apply_typography(self) -> None:
        for win in list(self.widgets.values()):
            try:
                win.apply_typography()
            except Exception:
                continue

    def get_summaries(self) -> List[str]:
        out: List[str] = []
        for wid, w in self.widgets.items():
            try:
                t = str(w.cfg.widget_type)
                if t == "price":
                    out.append(f"{wid} • {w.cfg.symbol}")
                elif t == "movers":
                    out.append(f"{wid} • movers")
                elif t == "portfolio":
                    out.append(f"{wid} • portfolio")
                else:
                    out.append(f"{wid} • {t}")
            except Exception:
                out.append(wid)
        return out


# =============================================================================
# Main App
# =============================================================================
