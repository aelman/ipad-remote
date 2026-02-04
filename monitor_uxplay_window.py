#!/usr/bin/env python3
"""
Monitor for UxPlay window and exit when it disappears.
Used by the launcher to detect when user closes the UxPlay window.
"""

import sys
import time
from Xlib import display, X

# Patterns to match UxPlay's video window (created by GStreamer)
# The window could have various names depending on GStreamer sink used
UXPLAY_PATTERNS = [
    'uxplay',           # UxPlay window class
    'gst',              # GStreamer windows (gst-launch, etc)
    'autovideosink',    # GStreamer auto sink
    'xvimagesink',      # X video image sink
    'ximagesink',       # X image sink
    'glimagesink',      # OpenGL sink
]
CHECK_INTERVAL = 0.5  # seconds


def find_uxplay_window(dpy, window):
    """Recursively search for UxPlay window."""
    try:
        wm_name = window.get_wm_name()
        if wm_name:
            wm_name_lower = wm_name.lower()
            for pattern in UXPLAY_PATTERNS:
                if pattern in wm_name_lower:
                    return True

        wm_class = window.get_wm_class()
        if wm_class:
            for cls in wm_class:
                if cls:
                    cls_lower = cls.lower()
                    for pattern in UXPLAY_PATTERNS:
                        if pattern in cls_lower:
                            return True
    except Exception:
        pass

    try:
        children = window.query_tree().children
        for child in children:
            if find_uxplay_window(dpy, child):
                return True
    except Exception:
        pass

    return False


def main():
    """Wait for UxPlay window to appear, then exit when it disappears."""
    try:
        dpy = display.Display()
    except Exception as e:
        print(f"Cannot open display: {e}", file=sys.stderr)
        sys.exit(1)

    root = dpy.screen().root
    window_appeared = False

    while True:
        window_exists = find_uxplay_window(dpy, root)

        if window_exists and not window_appeared:
            window_appeared = True

        elif not window_exists and window_appeared:
            # Window was there but now gone - user closed it
            sys.exit(0)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
