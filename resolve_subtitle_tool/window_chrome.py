"""The app's own title bar, on Windows.

Windows draws a caption bar in the system's colours, which sits above a very
dark UI looking like it belongs to a different program. So the Windows build
asks pywebview for a frameless window and draws the bar in React instead.

Going frameless gives up three things the OS was doing for free -- the resize
border, dragging by the title bar, and the minimize/maximize/close buttons --
and this module buys each of them back with the Win32 call that does that job.
Everything here is a no-op on macOS, which keeps its native title bar.
"""

from __future__ import annotations

import sys
import time

WINDOWS = sys.platform == "win32"

#: What the frontend should draw. "custom" means it owns the title bar.
KIND = "custom" if WINDOWS else "native"

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _dwmapi = ctypes.windll.dwmapi

    GWL_STYLE = -16
    WS_THICKFRAME = 0x00040000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000

    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020

    VK_LBUTTON = 0x01
    MONITOR_DEFAULTTONEAREST = 0x0002
    SW_SHOWNORMAL = 1

    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 2

    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongW.restype = ctypes.c_long
    _user32.GetAsyncKeyState.restype = ctypes.c_short

    class _WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.UINT),
            ("flags", wintypes.UINT),
            ("showCmd", wintypes.UINT),
            ("ptMinPosition", wintypes.POINT),
            ("ptMaxPosition", wintypes.POINT),
            ("rcNormalPosition", wintypes.RECT),
        ]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    def _hwnd_of(window) -> int:
        """The Win32 handle behind a pywebview window, or 0 before it exists."""
        native = getattr(window, "native", None)
        handle = getattr(native, "Handle", None)
        if handle is None:
            return 0
        try:
            return int(handle.ToInt64())
        except Exception:  # noqa: BLE001  # A window that is going away has none.
            return 0

    def _rect(hwnd: int) -> wintypes.RECT:
        r = wintypes.RECT()
        _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
        return r

    def _cursor() -> tuple[int, int]:
        p = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def _work_area(hwnd: int) -> wintypes.RECT:
        """The monitor's usable area -- the screen minus the taskbar."""
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        monitor = _user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
        _user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        return info.rcWork

    def _button_down() -> bool:
        return bool(_user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)

    def _move(hwnd: int, x: int, y: int) -> None:
        _user32.SetWindowPos(
            wintypes.HWND(hwnd), None, x, y, 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
        )

    def _placement(hwnd: int) -> _WINDOWPLACEMENT:
        wp = _WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
        _user32.GetWindowPlacement(wintypes.HWND(hwnd), ctypes.byref(wp))
        return wp

    def _set_normal_rect(hwnd: int, rc: wintypes.RECT) -> None:
        """Overwrite the rect Windows will use the next time the window restores."""
        wp = _placement(hwnd)
        wp.rcNormalPosition = rc
        _user32.SetWindowPlacement(wintypes.HWND(hwnd), ctypes.byref(wp))


class WindowChrome:
    """Window buttons and dragging for a frameless window.

    Every method is safe to call from a worker thread, which is where pywebview
    runs calls coming from JavaScript, and safe to call before the window
    exists -- the frontend can ask for the state during its first render.
    """

    def __init__(self, window) -> None:
        self._window = window
        self._dragging = False
        self._saved_rect = None  # rcNormalPosition saved before maximizing

    # -- setup -----------------------------------------------------------
    def attach(self) -> None:
        """Undo what frameless cost us, once the window has a handle.

        pywebview makes a window frameless by setting the WinForms border style
        to None, which drops WS_THICKFRAME along with the caption. Without that
        bit the window cannot be resized by dragging its edges and Windows will
        not snap it, so put it back: the caption stays gone, and the 8px sizing
        border it restores is the invisible grab area every normal window has,
        not something the user can see.
        """
        if not WINDOWS:
            return
        hwnd = _hwnd_of(self._window)
        if not hwnd:
            return
        style = _user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_STYLE)
        _user32.SetWindowLongW(
            wintypes.HWND(hwnd), GWL_STYLE,
            style | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX,
        )
        _user32.SetWindowPos(
            wintypes.HWND(hwnd), None, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
        # Windows 11 rounds app windows; a frameless one has to ask. Older
        # builds reject the attribute, which is exactly the square corner they
        # would have drawn anyway.
        try:
            preference = ctypes.c_int(DWMWCP_ROUND)
            _dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(preference), ctypes.sizeof(preference),
            )
        except Exception:  # noqa: BLE001  # Cosmetic; never worth failing over.
            pass

    # -- state -----------------------------------------------------------
    def is_maximized(self) -> bool:
        if not WINDOWS:
            return False
        hwnd = _hwnd_of(self._window)
        return bool(hwnd and _user32.IsZoomed(wintypes.HWND(hwnd)))

    # -- the buttons -----------------------------------------------------
    # These go through pywebview rather than ShowWindow. The window belongs to
    # the UI thread and these calls arrive on a worker one; pywebview marshals
    # them across, where a raw ShowWindow changes the window behind WinForms'
    # back. Minimizing that way left WinForms thinking the window was never
    # minimized, and the WebView2 control came back from the taskbar blank.

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> None:
        if self.is_maximized():
            self._window.restore()
            # Bug fix: WS_THICKFRAME changes the frame delta WinForms uses when
            # it saves the restored bounds, shrinking the window ~16px on every
            # maximize/restore cycle.  Reapply the rect we remembered.
            if WINDOWS and self._saved_rect is not None:
                hwnd = _hwnd_of(self._window)
                if hwnd:
                    _set_normal_rect(hwnd, self._saved_rect)
                    self._saved_rect = None
        else:
            # Remember the rect *before* WinForms touches it.
            if WINDOWS:
                hwnd = _hwnd_of(self._window)
                if hwnd:
                    self._saved_rect = _placement(hwnd).rcNormalPosition
            self._window.maximize()

    def close(self) -> None:
        self._window.destroy()

    # -- dragging --------------------------------------------------------
    def drag(self) -> None:
        """Move the window with the pointer until the mouse button comes up.

        The obvious approach -- handing the drag to Windows with a synthetic
        WM_NCLBUTTONDOWN -- does nothing here, because WebView2 already holds
        the mouse capture for the click that started this. So follow the cursor
        directly instead. GetCursorPos and GetAsyncKeyState read the hardware
        rather than the message queue, so neither cares who has capture.

        This runs on the thread pywebview gave the JavaScript call, and returns
        when the drag ends.
        """
        if not WINDOWS or self._dragging:
            return
        hwnd = _hwnd_of(self._window)
        if not hwnd:
            return
        self._dragging = True
        try:
            self._follow_cursor(hwnd)
        finally:
            self._dragging = False

    def _follow_cursor(self, hwnd: int) -> None:
        start = _cursor()
        if _user32.IsZoomed(wintypes.HWND(hwnd)):
            self._unmaximize_under_cursor(hwnd, start)
            start = _cursor()
        rect = _rect(hwnd)
        origin = (rect.left, rect.top)
        last = start
        # A ceiling in case the button-up is somehow missed -- a lost drag is a
        # thread that never returns, and the window would follow the mouse for
        # the rest of the session.
        deadline = time.monotonic() + 120
        while _button_down() and time.monotonic() < deadline:
            here = _cursor()
            if here != last:
                last = here
                _move(hwnd, origin[0] + here[0] - start[0], origin[1] + here[1] - start[1])
            time.sleep(0.008)
        # Dropped against the top edge means maximize, as it does everywhere
        # else in Windows.
        x, y = _cursor()
        work = _work_area(hwnd)
        if y <= work.top + 1 and work.left <= x <= work.right:
            self._window.maximize()

    def _unmaximize_under_cursor(self, hwnd: int, cursor: tuple[int, int]) -> None:
        """Come out of maximized keeping the grab point under the pointer.

        Restoring on its own would drop the window back to wherever it last
        was, which is usually not under the mouse -- so the window would jump
        out from under the pointer and then start following it.
        """
        big = _rect(hwnd)
        width = max(1, big.right - big.left)
        across = (cursor[0] - big.left) / width
        # The maximized rect's top is ~-8px above the visible work area. Using
        # it as the reference puts the restored window that many pixels too low.
        # The work area top is where the title bar actually begins visually.
        work = _work_area(hwnd)
        down = cursor[1] - work.top
        # restore() is marshalled to the UI thread, so _rect() immediately after
        # may still return the maximized rect.  Read the *normal* rect from the
        # placement instead -- that is what Windows will use.
        normal = _placement(hwnd).rcNormalPosition
        restored_w = max(1, normal.right - normal.left)
        self._window.restore()
        _move(
            hwnd,
            int(cursor[0] - restored_w * across),
            cursor[1] - down,
        )

