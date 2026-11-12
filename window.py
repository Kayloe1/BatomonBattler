"""Find the Batomon Showdown window and capture its client area.

All positions in later code are fractions (0.0-1.0) of the 16:9 game picture
(the client area without its black bars), so they keep working if the window
is resized or moved.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass

import mss
import win32gui
import win32process
from PIL import Image

WINDOW_TITLE = "Batomon Showdown"
PROCESS_NAME = "batomon_showdown.exe"


def _make_dpi_aware() -> None:
    """Use physical pixels everywhere (must run before any window/screen calls)."""
    try:
        # Per-monitor DPI aware v2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_make_dpi_aware()


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def _process_name(hwnd: int) -> str | None:
    try:
        import win32api
        import win32con

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        try:
            path = win32process.GetModuleFileNameEx(handle, 0)
        finally:
            win32api.CloseHandle(handle)
        return path.replace("/", "\\").rsplit("\\", 1)[-1].lower()
    except Exception:
        return None


def find_window(title: str = WINDOW_TITLE) -> int | None:
    """Return the HWND of the visible game window, or None if not found."""
    matches: list[int] = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == title:
            matches.append(hwnd)
        return True

    win32gui.EnumWindows(_cb, None)
    # Prefer the window owned by the game process (avoids e.g. a browser tab with the same title)
    for hwnd in matches:
        if _process_name(hwnd) == PROCESS_NAME:
            return hwnd
    return matches[0] if matches else None


def client_rect(hwnd: int) -> Rect:
    """Client area of the window in screen pixels (physical, DPI aware)."""
    _, _, w, h = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    return Rect(left, top, w, h)


def is_minimized(hwnd: int) -> bool:
    return bool(win32gui.IsIconic(hwnd))


_PW_CLIENTONLY_RENDERFULLCONTENT = 0x1 | 0x2


def _capture_printwindow(hwnd: int, r: Rect) -> Image.Image | None:
    """Ask the window to draw itself; works even when other windows cover it."""
    import win32ui

    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    try:
        bmp.CreateCompatibleBitmap(src, r.width, r.height)
        mem.SelectObject(bmp)
        ok = ctypes.windll.user32.PrintWindow(
            hwnd, mem.GetSafeHdc(), _PW_CLIENTONLY_RENDERFULLCONTENT
        )
        if not ok:
            return None
        info = bmp.GetInfo()
        img = Image.frombuffer(
            "RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True),
            "raw", "BGRX", 0, 1,
        )
        # An all-black result means the window didn't render into our DC.
        return img if img.getbbox() else None
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        mem.DeleteDC()
        src.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc)


def capture_client(hwnd: int, method: str = "auto") -> Image.Image:
    """Grab the client area as an RGB PIL image.

    method: "printwindow" (works when covered), "screen" (reads screen pixels,
    window must be on top), or "auto" (printwindow, falling back to screen).
    """
    r = client_rect(hwnd)
    if r.width <= 0 or r.height <= 0:
        raise RuntimeError("Game window has no visible client area (minimized?)")
    if method in ("auto", "printwindow"):
        img = _capture_printwindow(hwnd, r)
        if img is not None:
            return img
        if method == "printwindow":
            raise RuntimeError("PrintWindow capture failed")
    with mss.mss() as sct:
        shot = sct.grab({"left": r.left, "top": r.top, "width": r.width, "height": r.height})
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


# ---- the 16:9 game picture inside the client area ----
#
# The game draws a 16:9 picture centred in the window and fills the rest with
# black bars (at 2560x1600 that is an 80 px bar above and below). Every
# fraction in this project is measured against that picture, never the bars.

ASPECT = 16 / 9
CANON_W, CANON_H = 2560, 1440   # size the reader works in


def picture_rect(rect: Rect) -> Rect:
    """The 16:9 game picture inside a client rect, in the same coordinates."""
    if rect.width / rect.height > ASPECT:      # bars left and right
        h = rect.height
        w = int(round(h * ASPECT))
    else:                                      # bars above and below
        w = rect.width
        h = int(round(w / ASPECT))
    return Rect(rect.left + (rect.width - w) // 2, rect.top + (rect.height - h) // 2, w, h)


def crop_picture(img: Image.Image) -> Image.Image:
    """Cut the black bars off a client-area capture."""
    p = picture_rect(Rect(0, 0, img.width, img.height))
    if (p.width, p.height) == img.size:
        return img
    return img.crop((p.left, p.top, p.right, p.bottom))


def canonical_picture(img: Image.Image) -> Image.Image:
    """Client-area capture -> game picture scaled to CANON_W x CANON_H."""
    pic = crop_picture(img).convert("RGB")
    if pic.size != (CANON_W, CANON_H):
        pic = pic.resize((CANON_W, CANON_H), Image.BILINEAR)
    return pic


def frac_to_client(rect: Rect, fx: float, fy: float) -> tuple[int, int]:
    """Fraction of the game picture -> pixel within the client area / captured image.

    rect is the client rect; only its size matters here.
    """
    p = picture_rect(Rect(0, 0, rect.width, rect.height))
    return p.left + int(round(fx * (p.width - 1))), p.top + int(round(fy * (p.height - 1)))


def frac_to_screen(rect: Rect, fx: float, fy: float) -> tuple[int, int]:
    """Fraction of the game picture -> absolute screen pixel (for clicking later)."""
    x, y = frac_to_client(rect, fx, fy)
    return rect.left + x, rect.top + y


def screen_to_frac(rect: Rect, sx: int, sy: int) -> tuple[float, float]:
    """Absolute screen pixel -> fraction of the game picture (outside 0..1 = on a black bar)."""
    p = picture_rect(rect)
    return (sx - p.left) / max(p.width - 1, 1), (sy - p.top) / max(p.height - 1, 1)
