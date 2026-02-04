# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

iPad Remote exposes a Linux laptop as a Bluetooth LE HID device (keyboard + mouse) that an iPad can connect to. Combined with AirPlay screen mirroring (via UxPlay), this allows controlling an iPad using the laptop's input devices while viewing the iPad screen on the laptop.

## Commands

```bash
# First-time setup (installs system packages, creates venv)
sudo ./setup.sh

# Install desktop integration (adds app to GNOME launcher)
./install.sh

# Run full app (UxPlay + BLE HID + waiting dialog)
./ipad-remote-launcher

# Run only the BLE HID service (requires sudo)
sudo venv/bin/python main.py

# Test input capture (no sudo needed)
venv/bin/python input_capture.py
```

Root privileges are required for Bluetooth HID operations. The launcher uses polkit (pkexec) for privilege elevation.

## Desktop Integration

- **ipad-remote.desktop** - GNOME application entry
- **ipad-remote-launcher** - Main launcher script that orchestrates UxPlay, waiting dialog, HID service, and window monitoring
- **com.github.ipad-remote.policy** - Polkit policy for privilege elevation
- **waiting_dialog.py** - GTK dialog showing connection instructions until iPad connects
- **monitor_uxplay_window.py** - Monitors UxPlay window and triggers cleanup when closed

## Architecture

**main.py** - Entry point. `IPadRemote` class coordinates BLE HID and input capture, forwarding X11 events to the iPad via BLE notifications.

**ble_hid_profile.py** - BLE HID over GATT Profile (HoGP) implementation using BlueZ D-Bus API. Key components:
- `BLEHIDProfile` - Main class managing BLE advertising and GATT services
- `HIDService` - GATT service with keyboard/mouse report characteristics
- `PairingAgent` - Handles Bluetooth pairing requests
- `HID_REPORT_MAP` - USB HID descriptor defining keyboard (Report ID 1) and mouse (Report ID 2)

**input_capture.py** - Captures keyboard/mouse via X11 RECORD extension. Converts X11 keysyms to USB HID usage codes. Only forwards input when UxPlay window is focused. Exit hotkey: Ctrl+Alt+Q.

## Key Technical Details

- Uses BLE HID (HoGP) instead of classic Bluetooth HID for iOS compatibility
- BlueZ D-Bus API: services registered at `/org/bluez/hid/*`
- GATT notifications only sent after iPad enables CCC descriptor
- GLib main loop runs in separate thread for D-Bus event handling
- HID reports: keyboard is 8 bytes (modifiers + reserved + 6 keys), mouse is 4 bytes (buttons + X + Y + wheel)

## Dependencies

System packages (via apt): `python3-dbus`, `python3-gi`, `bluez`, `uxplay`
Python packages: `python-xlib`

The venv uses `--system-site-packages` to access dbus and gi modules.
