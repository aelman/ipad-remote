"""
Input capture module for relaying keyboard and mouse events to iPad.

This module captures input events from the laptop and converts them
to HID reports that can be sent to the iPad via Bluetooth.

Uses Xlib directly to avoid evdev dependency.
"""

from typing import Callable, Optional
import threading
import time
import ctypes
import ctypes.util

from Xlib import X, XK, display
from Xlib.ext import record
from Xlib.protocol import rq

# Load X11 library for cursor creation
_xlib = None
try:
    _xlib_path = ctypes.util.find_library('X11')
    if _xlib_path:
        _xlib = ctypes.CDLL(_xlib_path)
except Exception:
    pass


# USB HID keyboard usage codes (simplified mapping)
# Full list: https://usb.org/sites/default/files/hut1_4.pdf
KEY_CODES = {
    # Letters
    'a': 0x04, 'b': 0x05, 'c': 0x06, 'd': 0x07, 'e': 0x08, 'f': 0x09,
    'g': 0x0A, 'h': 0x0B, 'i': 0x0C, 'j': 0x0D, 'k': 0x0E, 'l': 0x0F,
    'm': 0x10, 'n': 0x11, 'o': 0x12, 'p': 0x13, 'q': 0x14, 'r': 0x15,
    's': 0x16, 't': 0x17, 'u': 0x18, 'v': 0x19, 'w': 0x1A, 'x': 0x1B,
    'y': 0x1C, 'z': 0x1D,

    # Numbers
    '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21, '5': 0x22,
    '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,

    # Special keys
    'return': 0x28, 'escape': 0x29, 'backspace': 0x2A, 'tab': 0x2B,
    'space': 0x2C, 'minus': 0x2D, 'equal': 0x2E, 'bracketleft': 0x2F,
    'bracketright': 0x30, 'backslash': 0x31, 'semicolon': 0x33,
    'apostrophe': 0x34, 'grave': 0x35, 'comma': 0x36,
    'period': 0x37, 'slash': 0x38,

    # Function keys
    'f1': 0x3A, 'f2': 0x3B, 'f3': 0x3C, 'f4': 0x3D, 'f5': 0x3E,
    'f6': 0x3F, 'f7': 0x40, 'f8': 0x41, 'f9': 0x42, 'f10': 0x43,
    'f11': 0x44, 'f12': 0x45,

    # Navigation
    'insert': 0x49, 'home': 0x4A, 'prior': 0x4B, 'delete': 0x4C,
    'end': 0x4D, 'next': 0x4E, 'right': 0x4F, 'left': 0x50,
    'down': 0x51, 'up': 0x52,

    # Caps lock
    'caps_lock': 0x39,
}

# Modifier key bit masks
MODIFIER_LEFT_CTRL = 0x01
MODIFIER_LEFT_SHIFT = 0x02
MODIFIER_LEFT_ALT = 0x04
MODIFIER_LEFT_GUI = 0x08  # Command/Windows key
MODIFIER_RIGHT_CTRL = 0x10
MODIFIER_RIGHT_SHIFT = 0x20
MODIFIER_RIGHT_ALT = 0x40
MODIFIER_RIGHT_GUI = 0x80

# X11 modifier keysyms to HID modifiers
MODIFIER_KEYSYMS = {
    XK.XK_Control_L: MODIFIER_LEFT_CTRL,
    XK.XK_Control_R: MODIFIER_RIGHT_CTRL,
    XK.XK_Shift_L: MODIFIER_LEFT_SHIFT,
    XK.XK_Shift_R: MODIFIER_RIGHT_SHIFT,
    XK.XK_Alt_L: MODIFIER_LEFT_ALT,
    XK.XK_Alt_R: MODIFIER_RIGHT_ALT,
    XK.XK_Super_L: MODIFIER_LEFT_GUI,
    XK.XK_Super_R: MODIFIER_RIGHT_GUI,
    XK.XK_Meta_L: MODIFIER_LEFT_GUI,
    XK.XK_Meta_R: MODIFIER_RIGHT_GUI,
}


class InputCapture:
    """Captures keyboard and mouse input and converts to HID reports."""

    # Window name patterns to match for UxPlay
    UXPLAY_WINDOW_PATTERNS = ['uxplay', 'ipad remote', 'airplay']

    def __init__(
        self,
        keyboard_callback: Callable[[int, list], None],
        mouse_callback: Callable[[int, int, int, int], None],
        capture_region: Optional[tuple] = None,
        require_focus: bool = True
    ):
        """
        Initialize input capture.

        Args:
            keyboard_callback: Function to call with (modifier_keys, key_list)
            mouse_callback: Function to call with (buttons, x, y, wheel)
            capture_region: Optional (x, y, width, height) to limit mouse capture
            require_focus: Only capture when UxPlay window is focused
        """
        self.keyboard_callback = keyboard_callback
        self.mouse_callback = mouse_callback
        self.capture_region = capture_region
        self.require_focus = require_focus

        self.local_display = None
        self.record_display = None
        self.focus_display = None  # Separate connection for focus checks
        self.context = None

        self.modifier_state = 0
        self.pressed_keys = set()
        self.mouse_buttons = 0

        self.capturing = False
        self.capture_lock = threading.Lock()
        self.capture_thread = None

        # For relative mouse movement
        self.last_mouse_x = None
        self.last_mouse_y = None

        # Cursor hiding state
        self.cursor_hidden = False
        self._last_focus_check = 0
        self._last_focus_state = False
        self._cursor_display = None
        self._raw_display = None
        self._blank_cursor_id = None
        self._uxplay_window = None

    def _init_cursor_hiding(self):
        """Initialize cursor hiding with a blank cursor."""
        if not _xlib:
            return

        try:
            self._cursor_display = display.Display()
            screen = self._cursor_display.screen()

            # Get the raw X display pointer and root window
            xdisplay = self._cursor_display.display.display_name
            # Open a raw X connection for ctypes
            self._raw_display = _xlib.XOpenDisplay(xdisplay.encode() if xdisplay else None)
            if not self._raw_display:
                return

            # Create blank 1x1 pixmaps for source and mask
            root_id = screen.root.id
            source = _xlib.XCreatePixmap(self._raw_display, root_id, 1, 1, 1)
            mask = _xlib.XCreatePixmap(self._raw_display, root_id, 1, 1, 1)

            # XColor structure for black (all zeros works)
            class XColor(ctypes.Structure):
                _fields_ = [
                    ('pixel', ctypes.c_ulong),
                    ('red', ctypes.c_ushort),
                    ('green', ctypes.c_ushort),
                    ('blue', ctypes.c_ushort),
                    ('flags', ctypes.c_char),
                    ('pad', ctypes.c_char),
                ]

            black = XColor(0, 0, 0, 0, b'\x00', b'\x00')

            # Create the blank cursor
            cursor_id = _xlib.XCreatePixmapCursor(
                self._raw_display,
                source, mask,
                ctypes.byref(black), ctypes.byref(black),
                0, 0
            )

            _xlib.XFreePixmap(self._raw_display, source)
            _xlib.XFreePixmap(self._raw_display, mask)

            if cursor_id:
                self._blank_cursor_id = cursor_id
        except Exception:
            self._cursor_display = None
            self._blank_cursor_id = None

    def _cleanup_cursor_hiding(self):
        """Clean up cursor resources."""
        # Restore cursor on UxPlay window if we hid it
        if self._uxplay_window and self.cursor_hidden:
            try:
                self._uxplay_window.change_attributes(cursor=X.NONE)
                self._cursor_display.flush()
            except Exception:
                pass

        if self._blank_cursor_id and self._raw_display and _xlib:
            try:
                _xlib.XFreeCursor(self._raw_display, self._blank_cursor_id)
            except Exception:
                pass
            self._blank_cursor_id = None

        if self._raw_display and _xlib:
            try:
                _xlib.XCloseDisplay(self._raw_display)
            except Exception:
                pass
            self._raw_display = None

        if self._cursor_display:
            try:
                self._cursor_display.close()
            except Exception:
                pass
            self._cursor_display = None

        self._uxplay_window = None
        self.cursor_hidden = False

    def _find_uxplay_window(self):
        """Find the UxPlay window by searching window tree."""
        if not self._cursor_display:
            return None

        try:
            root = self._cursor_display.screen().root
            return self._search_window_tree(root)
        except Exception:
            return None

    def _search_window_tree(self, window):
        """Recursively search window tree for UxPlay window."""
        try:
            # Check this window
            try:
                wm_name = window.get_wm_name()
                if wm_name:
                    wm_name_lower = wm_name.lower()
                    for pattern in self.UXPLAY_WINDOW_PATTERNS:
                        if pattern in wm_name_lower:
                            return window
            except Exception:
                pass

            try:
                wm_class = window.get_wm_class()
                if wm_class:
                    for cls in wm_class:
                        if cls:
                            cls_lower = cls.lower()
                            for pattern in self.UXPLAY_WINDOW_PATTERNS:
                                if pattern in cls_lower:
                                    return window
            except Exception:
                pass

            # Search children
            children = window.query_tree().children
            for child in children:
                result = self._search_window_tree(child)
                if result:
                    return result
        except Exception:
            pass
        return None

    def _update_cursor_visibility(self):
        """Update cursor visibility based on focus, throttled."""
        now = time.time()
        # Only check every 100ms
        if now - self._last_focus_check < 0.1:
            return
        self._last_focus_check = now

        focused = self._is_uxplay_focused()
        if focused != self._last_focus_state:
            self._last_focus_state = focused
            if focused:
                self._hide_cursor()
            else:
                self._show_cursor()

    def _hide_cursor(self):
        """Hide cursor by setting blank cursor on UxPlay window."""
        if self.cursor_hidden or not self._blank_cursor_id or not self._raw_display:
            return

        try:
            # Find UxPlay window if we haven't yet
            if not self._uxplay_window:
                self._uxplay_window = self._find_uxplay_window()

            if self._uxplay_window and _xlib:
                _xlib.XDefineCursor(self._raw_display, self._uxplay_window.id, self._blank_cursor_id)
                _xlib.XFlush(self._raw_display)
                self.cursor_hidden = True
        except Exception:
            self._uxplay_window = None

    def _show_cursor(self):
        """Show cursor by resetting cursor on UxPlay window."""
        if not self.cursor_hidden or not self._raw_display:
            return

        try:
            if self._uxplay_window and _xlib:
                _xlib.XUndefineCursor(self._raw_display, self._uxplay_window.id)
                _xlib.XFlush(self._raw_display)
        except Exception:
            self._uxplay_window = None

        self.cursor_hidden = False

    def _is_uxplay_focused(self) -> bool:
        """Check if UxPlay window is currently focused."""
        if not self.require_focus:
            return True

        try:
            if not self.focus_display:
                return True

            # Get the focused window
            focus = self.focus_display.get_input_focus()
            window = focus.focus

            if not window or window == X.NONE:
                return False

            # Try to get window name
            try:
                wm_name = window.get_wm_name()
                if wm_name:
                    wm_name_lower = wm_name.lower()
                    for pattern in self.UXPLAY_WINDOW_PATTERNS:
                        if pattern in wm_name_lower:
                            return True
            except Exception:
                pass

            # Try to get WM_CLASS
            try:
                wm_class = window.get_wm_class()
                if wm_class:
                    for cls in wm_class:
                        if cls:
                            cls_lower = cls.lower()
                            for pattern in self.UXPLAY_WINDOW_PATTERNS:
                                if pattern in cls_lower:
                                    return True
            except Exception:
                pass

            return False
        except Exception:
            # On error, allow capture (fail open)
            return True

    def _keysym_to_hid(self, keysym: int) -> Optional[int]:
        """Convert X11 keysym to HID usage code."""
        # Get key name from keysym
        key_name = XK.keysym_to_string(keysym)
        if key_name:
            key_name = key_name.lower()
            return KEY_CODES.get(key_name)
        return None

    def _is_modifier(self, keysym: int) -> bool:
        """Check if keysym is a modifier key."""
        return keysym in MODIFIER_KEYSYMS

    def _update_modifier(self, keysym: int, pressed: bool):
        """Update modifier state for a keysym."""
        if keysym in MODIFIER_KEYSYMS:
            if pressed:
                self.modifier_state |= MODIFIER_KEYSYMS[keysym]
            else:
                self.modifier_state &= ~MODIFIER_KEYSYMS[keysym]

    def _check_exit_hotkey(self, keysym: int) -> bool:
        """Check if exit hotkey (Ctrl+Alt+Q) was pressed."""
        if keysym == XK.XK_q or keysym == XK.XK_Q:
            if (self.modifier_state & (MODIFIER_LEFT_CTRL | MODIFIER_LEFT_ALT) ==
                    (MODIFIER_LEFT_CTRL | MODIFIER_LEFT_ALT)):
                return True
        return False

    def _send_keyboard_state(self):
        """Send current keyboard state via callback."""
        if not self._is_uxplay_focused():
            return
        # HID supports up to 6 simultaneous keys
        keys = list(self.pressed_keys)[:6]
        self.keyboard_callback(self.modifier_state, keys)

    def _process_event(self, reply):
        """Process X11 record event."""
        if reply.category != record.FromServer:
            return
        if reply.client_swapped:
            return

        # Update cursor visibility based on focus
        self._update_cursor_visibility()

        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(
                data, self.record_display.display, None, None
            )

            if event.type == X.KeyPress:
                keysym = self.local_display.keycode_to_keysym(event.detail, 0)

                # Check exit hotkey
                if self._check_exit_hotkey(keysym):
                    print("\nExit hotkey pressed (Ctrl+Alt+Q)")
                    self.stop()
                    return

                # Handle modifiers
                if self._is_modifier(keysym):
                    self._update_modifier(keysym, True)
                    self._send_keyboard_state()
                else:
                    # Regular key
                    hid_code = self._keysym_to_hid(keysym)
                    if hid_code:
                        self.pressed_keys.add(hid_code)
                        self._send_keyboard_state()

            elif event.type == X.KeyRelease:
                keysym = self.local_display.keycode_to_keysym(event.detail, 0)

                # Handle modifiers
                if self._is_modifier(keysym):
                    self._update_modifier(keysym, False)
                    self._send_keyboard_state()
                else:
                    # Regular key
                    hid_code = self._keysym_to_hid(keysym)
                    if hid_code:
                        self.pressed_keys.discard(hid_code)
                        self._send_keyboard_state()

            elif event.type == X.ButtonPress:
                button = event.detail
                if button == 1:  # Left
                    self.mouse_buttons |= 0x01
                elif button == 2:  # Middle
                    self.mouse_buttons |= 0x04
                elif button == 3:  # Right
                    self.mouse_buttons |= 0x02
                elif button == 4:  # Scroll up
                    if self._is_uxplay_focused():
                        self.mouse_callback(self.mouse_buttons, 0, 0, 3)
                    continue
                elif button == 5:  # Scroll down
                    if self._is_uxplay_focused():
                        self.mouse_callback(self.mouse_buttons, 0, 0, -3)
                    continue
                if self._is_uxplay_focused():
                    self.mouse_callback(self.mouse_buttons, 0, 0, 0)

            elif event.type == X.ButtonRelease:
                button = event.detail
                if button == 1:  # Left
                    self.mouse_buttons &= ~0x01
                elif button == 2:  # Middle
                    self.mouse_buttons &= ~0x04
                elif button == 3:  # Right
                    self.mouse_buttons &= ~0x02
                # Ignore scroll button releases
                if button not in (4, 5):
                    if self._is_uxplay_focused():
                        self.mouse_callback(self.mouse_buttons, 0, 0, 0)

            elif event.type == X.MotionNotify:
                x, y = event.root_x, event.root_y

                # Check if in capture region
                if self.capture_region:
                    rx, ry, rw, rh = self.capture_region
                    if not (rx <= x < rx + rw and ry <= y < ry + rh):
                        continue

                # Calculate relative movement
                if self.last_mouse_x is not None:
                    dx = x - self.last_mouse_x
                    dy = y - self.last_mouse_y

                    if dx != 0 or dy != 0:
                        if self._is_uxplay_focused():
                            self.mouse_callback(self.mouse_buttons, dx, dy, 0)

                self.last_mouse_x = x
                self.last_mouse_y = y

    def _capture_loop(self):
        """Main capture loop running in separate thread."""
        try:
            self.record_display.record_enable_context(self.context, self._process_event)
        except Exception as e:
            if self.capturing:
                print(f"Capture error: {e}")

    def start(self):
        """Start capturing input."""
        with self.capture_lock:
            if self.capturing:
                return

            # Open X11 connections
            self.local_display = display.Display()
            self.record_display = display.Display()
            self.focus_display = display.Display()  # For focus checks

            # Initialize cursor hiding (separate connection)
            self._init_cursor_hiding()

            # Check for RECORD extension
            if not self.record_display.has_extension("RECORD"):
                raise RuntimeError("X11 RECORD extension not available")

            # Create record context
            self.context = self.record_display.record_create_context(
                0,
                [record.AllClients],
                [{
                    'core_requests': (0, 0),
                    'core_replies': (0, 0),
                    'ext_requests': (0, 0, 0, 0),
                    'ext_replies': (0, 0, 0, 0),
                    'delivered_events': (0, 0),
                    'device_events': (X.KeyPress, X.MotionNotify),
                    'errors': (0, 0),
                    'client_started': False,
                    'client_died': False,
                }]
            )

            self.capturing = True

            # Start capture thread
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()

            if self.require_focus:
                print("Input capture started - only active when UxPlay window is focused (Ctrl+Alt+Q to exit)")
            else:
                print("Input capture started (Ctrl+Alt+Q to exit)")

    def stop(self):
        """Stop capturing input."""
        with self.capture_lock:
            if not self.capturing:
                return

            self.capturing = False

            # Restore cursor and cleanup cursor connection
            self._cleanup_cursor_hiding()

            # Disable record context
            if self.context and self.local_display:
                try:
                    self.local_display.record_disable_context(self.context)
                    self.local_display.flush()
                except Exception:
                    pass

            # Close connections
            if self.record_display:
                try:
                    self.record_display.close()
                except Exception:
                    pass
            if self.focus_display:
                try:
                    self.focus_display.close()
                except Exception:
                    pass
            if self.local_display:
                try:
                    self.local_display.close()
                except Exception:
                    pass

            # Reset state
            self.modifier_state = 0
            self.pressed_keys.clear()
            self.mouse_buttons = 0
            self.last_mouse_x = None
            self.last_mouse_y = None
            self.cursor_hidden = False
            self._last_focus_state = False

            print("Input capture stopped")

    def wait(self):
        """Wait for capture to finish."""
        if self.capture_thread:
            self.capture_thread.join()


def main():
    """Test input capture."""
    def on_keyboard(modifiers, keys):
        print(f"Keyboard: modifiers={modifiers:02x}, keys={keys}")

    def on_mouse(buttons, x, y, wheel):
        if x != 0 or y != 0 or wheel != 0 or buttons != 0:
            print(f"Mouse: buttons={buttons}, dx={x}, dy={y}, wheel={wheel}")

    capture = InputCapture(on_keyboard, on_mouse)
    capture.start()

    print("Move mouse and press keys. Ctrl+Alt+Q to exit.")
    capture.wait()


if __name__ == "__main__":
    main()
