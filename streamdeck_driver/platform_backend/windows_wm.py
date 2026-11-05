"""Windows-Fensterverwaltung per Win32 (ctypes, keine Zusatz-Abhaengigkeit):
Fenster/Monitore auflisten, exakt positionieren, in den Vordergrund holen,
maximieren/wiederherstellen, Dienste minimiert starten.

Wichtige Stolpersteine, die hier bewusst behandelt sind:

* HWND-Handles sind unter 64-bit Pointer-breit - ctypes' Standard-Rueckgabetyp
  'int' schneidet sie ab. Deshalb haben ALLE benutzten Funktionen explizite
  argtypes/restype.
* DPI: ohne Per-Monitor-DPI-Awareness bekommt der Prozess virtualisierte
  Koordinaten (bei gemischter Skalierung z.B. 125 % links / 150 % rechts
  stimmen Position und Groesse dann nicht). Wird einmalig beim ersten Zugriff
  gesetzt.
* Unsichtbarer Fensterrahmen: Win10/11-Fenster haben einen ~7 px breiten
  unsichtbaren Schatten-Rand. SetWindowPos arbeitet auf dem AEUSSEREN Rahmen,
  gewuenscht ist aber die SICHTBARE Position (sonst klaffen Luecken/Ueberlappung).
  Der Rand wird pro Fenster aus GetWindowRect vs. DWMWA_EXTENDED_FRAME_BOUNDS
  berechnet.
* Beim Verschieben ueber Monitore mit verschiedener Skalierung aendert Windows
  die Fenstergroesse nachtraeglich (WM_DPICHANGED) - deshalb wird nach dem
  Verschieben nachgemessen und bis zu 3x korrigiert.
* Vordergrund-Sperre: SetForegroundWindow aus einem Hintergrundprozess wird von
  Windows haeufig verweigert (Fenster blinkt nur in der Taskleiste). Abhilfe:
  Eingabe-Thread kurz an den des aktuellen Vordergrundfensters anhaengen.

Getestet: Windows 11, zwei Monitore mit unterschiedlicher Skalierung."""
from __future__ import annotations

import ctypes
import logging
import re
import subprocess
import time
from ctypes import wintypes

import psutil

logger = logging.getLogger("streamdeck_driver.platform_backend.windows_wm")

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

HWND = wintypes.HWND
SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE, SW_SHOWMINNOACTIVE = 3, 6, 9, 7
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000080, 0x00040000
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
STARTF_USESHOWWINDOW = 0x00000001
MONITORINFOF_PRIMARY = 1

_SHELL_CLASSES = {"progman", "workerw", "shell_traywnd", "shell_secondarytraywnd"}
_FRAME_HOST = "applicationframehost"


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
    ]


_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)
_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
)


def _sig(func, restype, *argtypes):
    func.restype = restype
    func.argtypes = list(argtypes)


_sig(user32.EnumWindows, wintypes.BOOL, _WNDENUMPROC, wintypes.LPARAM)
_sig(user32.EnumChildWindows, wintypes.BOOL, HWND, _WNDENUMPROC, wintypes.LPARAM)
_sig(user32.IsWindowVisible, wintypes.BOOL, HWND)
_sig(user32.IsIconic, wintypes.BOOL, HWND)
_sig(user32.IsZoomed, wintypes.BOOL, HWND)
_sig(user32.IsWindow, wintypes.BOOL, HWND)
_sig(user32.GetWindowTextLengthW, ctypes.c_int, HWND)
_sig(user32.GetWindowTextW, ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
_sig(user32.GetClassNameW, ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
_sig(user32.GetWindowThreadProcessId, wintypes.DWORD, HWND, ctypes.POINTER(wintypes.DWORD))
_sig(user32.GetWindowLongW, ctypes.c_long, HWND, ctypes.c_int)
_sig(user32.GetWindow, HWND, HWND, wintypes.UINT)
_sig(user32.GetWindowRect, wintypes.BOOL, HWND, ctypes.POINTER(wintypes.RECT))
_sig(user32.GetForegroundWindow, HWND)
_sig(user32.SetForegroundWindow, wintypes.BOOL, HWND)
_sig(user32.BringWindowToTop, wintypes.BOOL, HWND)
_sig(user32.ShowWindow, wintypes.BOOL, HWND, ctypes.c_int)
_sig(user32.SetWindowPos, wintypes.BOOL, HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
_sig(user32.AttachThreadInput, wintypes.BOOL, wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
_sig(user32.AllowSetForegroundWindow, wintypes.BOOL, wintypes.DWORD)
_sig(user32.SwitchToThisWindow, None, HWND, wintypes.BOOL)
_sig(user32.EnumDisplayMonitors, wintypes.BOOL, wintypes.HDC, ctypes.POINTER(wintypes.RECT), _MONITORENUMPROC, wintypes.LPARAM)
_sig(user32.GetMonitorInfoW, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(_MONITORINFO))
_sig(dwmapi.DwmGetWindowAttribute, ctypes.c_long, HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
ctypes.windll.kernel32.GetCurrentThreadId.restype = wintypes.DWORD

_dpi_set = False


def _ensure_dpi_aware() -> None:
    """Per-Monitor-v2 (Windows 10 1703+), Fallback auf aeltere Varianten. Schlaegt
    der Aufruf fehl, weil der Prozess (z.B. per Manifest) schon eine Einstellung
    hat, ist das in Ordnung - dann gilt eben diese."""
    global _dpi_set
    if _dpi_set:
        return
    _dpi_set = True
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            logger.warning("DPI-Awareness konnte nicht gesetzt werden - Positionen koennen bei gemischter Skalierung abweichen")


def _hwnd(window_id) -> int:
    return int(window_id)


def _title(h) -> str:
    n = user32.GetWindowTextLengthW(h)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def _class(h) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    return buf.value


def _pid(h) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def _outer_rect(h) -> wintypes.RECT:
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r


def _visible_rect(h) -> wintypes.RECT:
    r = wintypes.RECT()
    hr = dwmapi.DwmGetWindowAttribute(h, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r))
    return r if hr == 0 else _outer_rect(h)


def _process_name(pid: int, cache: dict[int, str]) -> str:
    if pid not in cache:
        try:
            name = psutil.Process(pid).name().lower()
            cache[pid] = name[:-4] if name.endswith(".exe") else name
        except psutil.Error:
            cache[pid] = ""
    return cache[pid]


def _hosted_app_pid(h, frame_pid: int) -> int:
    """UWP-Apps (Rechner, aeltere Fotos-Versionen, ...) haengen als Kindfenster
    'Windows.UI.Core.CoreWindow' im ApplicationFrameHost-Rahmen - die echte App
    ist der Prozess dieses Kindfensters."""
    found = []

    def _cb(child, _lparam):
        pid = _pid(child)
        if pid and pid != frame_pid:
            found.append(pid)
            return False
        return True

    user32.EnumChildWindows(h, _WNDENUMPROC(_cb), 0)
    return found[0] if found else frame_pid


def _is_candidate(h) -> bool:
    if not user32.IsWindowVisible(h) or user32.GetWindowTextLengthW(h) == 0:
        return False
    cloaked = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(h, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    if cloaked.value:  # z.B. Fenster auf einem anderen virtuellen Desktop oder noch nicht eingeblendete UWP-Huellen
        return False
    ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW:
        return False
    if user32.GetWindow(h, GW_OWNER) and not ex & WS_EX_APPWINDOW:
        return False  # Dialoge/Popups, die einem Hauptfenster gehoeren
    return _class(h).lower() not in _SHELL_CLASSES


def list_windows() -> list[dict]:
    """Sichtbare Top-Level-Fenster. 'app_id' = Prozessname ohne .exe, klein.
    Koordinaten = SICHTBARER Rahmen in physischen Pixeln des virtuellen Desktops."""
    _ensure_dpi_aware()
    foreground = user32.GetForegroundWindow()
    cache: dict[int, str] = {}
    result: list[dict] = []

    def _cb(h, _lparam):
        if not _is_candidate(h):
            return True
        pid = _pid(h)
        name = _process_name(pid, cache)
        if name == _FRAME_HOST:
            pid = _hosted_app_pid(h, pid)
            name = _process_name(pid, cache) or name
        r = _visible_rect(h)
        result.append({
            "id": str(int(h)), "app_id": name, "title": _title(h), "pid": pid,
            "x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top,
            "minimized": bool(user32.IsIconic(h)), "maximized": bool(user32.IsZoomed(h)),
            "focused": bool(foreground) and int(h) == int(foreground),
        })
        return True

    user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    return result


def list_monitors() -> list[dict]:
    _ensure_dpi_aware()
    result: list[dict] = []

    def _cb(hmon, _hdc, _rect, _lparam):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            m, w = info.rcMonitor, info.rcWork
            result.append({
                "x": m.left, "y": m.top, "w": m.right - m.left, "h": m.bottom - m.top,
                "work_x": w.left, "work_y": w.top, "work_w": w.right - w.left, "work_h": w.bottom - w.top,
                "primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
            })
        return True

    user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(_cb), 0)
    return result


def move_window(window_id, x: int, y: int, w: int, h: int) -> None:
    """Positioniert den SICHTBAREN Rahmen des Fensters exakt auf (x, y, w, h)."""
    _ensure_dpi_aware()
    hwnd = _hwnd(window_id)
    if not user32.IsWindow(hwnd):
        return
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)  # maximierte/minimierte Fenster lassen sich nicht verschieben
    for attempt in range(3):
        outer, visible = _outer_rect(hwnd), _visible_rect(hwnd)
        pad_l, pad_t = visible.left - outer.left, visible.top - outer.top
        pad_r, pad_b = outer.right - visible.right, outer.bottom - visible.bottom
        user32.SetWindowPos(
            hwnd, None, x - pad_l, y - pad_t, w + pad_l + pad_r, h + pad_t + pad_b,
            SWP_NOZORDER | SWP_NOACTIVATE,
        )
        now = _visible_rect(hwnd)
        if (abs(now.left - x) <= 1 and abs(now.top - y) <= 1
                and abs((now.right - now.left) - w) <= 1 and abs((now.bottom - now.top) - h) <= 1):
            return
        time.sleep(0.05)
    logger.debug("Fenster %s nach 3 Versuchen nicht exakt auf %s,%s %sx%s (Mindestgroesse/feste Groesse?)", window_id, x, y, w, h)


def focus_window(window_id) -> None:
    hwnd = _hwnd(window_id)
    if not user32.IsWindow(hwnd):
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    if fg and int(fg) == hwnd:
        return
    this_tid = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(fg_tid) and fg_tid != this_tid and user32.AttachThreadInput(this_tid, fg_tid, True)
    try:
        user32.AllowSetForegroundWindow(-1 & 0xFFFFFFFF)  # ASFW_ANY
        user32.BringWindowToTop(hwnd)
        ok = user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(this_tid, fg_tid, False)
    if not ok:
        user32.SwitchToThisWindow(hwnd, True)


def maximize_window(window_id) -> None:
    user32.ShowWindow(_hwnd(window_id), SW_MAXIMIZE)


def restore_window(window_id) -> None:
    user32.ShowWindow(_hwnd(window_id), SW_RESTORE)


def minimize_window(window_id) -> None:
    user32.ShowWindow(_hwnd(window_id), SW_MINIMIZE)


def start_minimized(command: str, cwd: str | None = None) -> None:
    """Startet einen Hintergrunddienst (z.B. ein .bat mit Server) in einem
    MINIMIERTEN, nicht aktivierten Konsolenfenster - es nimmt dem Nutzer weder
    den Fokus noch verdeckt es etwas, bleibt aber in der Taskleiste erreichbar."""
    if not command:
        return
    si = subprocess.STARTUPINFO()
    si.dwFlags |= STARTF_USESHOWWINDOW
    si.wShowWindow = SW_SHOWMINNOACTIVE
    command = command.strip()
    if re.search(r"\.(bat|cmd)\"?$", command, re.IGNORECASE):
        args = ["cmd.exe", "/c", command.strip('"')]
    else:
        import shlex
        args = shlex.split(command, posix=False)
    try:
        subprocess.Popen(args, cwd=cwd or None, startupinfo=si, creationflags=subprocess.CREATE_NEW_CONSOLE)
        logger.info("Dienst minimiert gestartet: %s", command)
    except OSError as exc:
        logger.error("Dienst konnte nicht gestartet werden (%s): %s", command, exc)
