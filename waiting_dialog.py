#!/usr/bin/env python3
"""
Waiting dialog that shows until iPad connects and UxPlay window appears.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from Xlib import display


class WaitingDialog(Gtk.Window):
    """Simple dialog showing connection instructions."""

    # Patterns to match UxPlay's video window (created by GStreamer)
    UXPLAY_PATTERNS = [
        'uxplay',           # UxPlay window class
        'gst',              # GStreamer windows
        'autovideosink',    # GStreamer auto sink
        'xvimagesink',      # X video image sink
        'ximagesink',       # X image sink
        'glimagesink',      # OpenGL sink
    ]

    def __init__(self):
        super().__init__(title="iPad Remote")
        self.set_default_size(400, 200)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)

        # Main container
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_top(30)
        box.set_margin_bottom(30)
        box.set_margin_start(30)
        box.set_margin_end(30)
        self.add(box)

        # Title
        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>iPad Remote</span>")
        box.pack_start(title, False, False, 0)

        # Instructions
        instructions = Gtk.Label()
        instructions.set_markup(
            "Waiting for iPad to connect...\n\n"
            "On your iPad:\n"
            "1. Open Control Center\n"
            "2. Tap Screen Mirroring\n"
            "3. Select 'iPad Remote Display'"
        )
        instructions.set_justify(Gtk.Justification.CENTER)
        box.pack_start(instructions, True, True, 0)

        # Spinner
        spinner = Gtk.Spinner()
        spinner.start()
        box.pack_start(spinner, False, False, 0)

        self.connect("destroy", Gtk.main_quit)

        # Start checking for UxPlay window
        self.display = None
        try:
            self.display = display.Display()
        except Exception:
            pass

        GLib.timeout_add(500, self._check_for_uxplay)

    def _check_for_uxplay(self):
        """Check if UxPlay window has appeared."""
        if not self.display:
            return True

        try:
            root = self.display.screen().root
            if self._find_uxplay_window(root):
                # UxPlay window found, close this dialog
                self.destroy()
                return False
        except Exception:
            pass

        return True  # Continue checking

    def _find_uxplay_window(self, window):
        """Recursively search for UxPlay window."""
        try:
            # Check window name
            wm_name = window.get_wm_name()
            if wm_name:
                wm_name_lower = wm_name.lower()
                for pattern in self.UXPLAY_PATTERNS:
                    if pattern in wm_name_lower:
                        return True

            # Check window class (more reliable for identifying apps)
            wm_class = window.get_wm_class()
            if wm_class:
                for cls in wm_class:
                    if cls:
                        cls_lower = cls.lower()
                        for pattern in self.UXPLAY_PATTERNS:
                            if pattern in cls_lower:
                                return True
        except Exception:
            pass

        try:
            children = window.query_tree().children
            for child in children:
                if self._find_uxplay_window(child):
                    return True
        except Exception:
            pass

        return False


def main():
    dialog = WaitingDialog()
    dialog.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
