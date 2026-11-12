"""Save a timestamped PNG of the Batomon Showdown client area to captures/.

Read-only: it never clicks or sends input to the game.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import window

CAPTURE_DIR = Path(__file__).resolve().parent / "captures"


def main() -> int:
    hwnd = window.find_window()
    if hwnd is None:
        print(f"Window '{window.WINDOW_TITLE}' not found. Is the game running?")
        return 1
    if window.is_minimized(hwnd):
        print("Game window is minimized; restore it and try again.")
        return 1

    rect = window.client_rect(hwnd)
    img = window.capture_client(hwnd)

    CAPTURE_DIR.mkdir(exist_ok=True)
    path = CAPTURE_DIR / f"capture_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
    img.save(path)

    print(f"Client area: {rect.width}x{rect.height} at screen ({rect.left}, {rect.top})")
    print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
