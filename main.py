#!/usr/bin/env python3
"""
iPad Remote - Control your iPad with your laptop's keyboard and mouse.

This application exposes your laptop as a Bluetooth LE HID device (keyboard + mouse)
that your iPad can connect to, allowing you to control the iPad using your
laptop's input devices.

Uses BLE HID over GATT Profile (HoGP) for better iOS compatibility.

Usage:
    1. Run this script (sudo may be needed for Bluetooth)
    2. On iPad, go to Settings > Bluetooth
    3. Connect to "iPad Remote"
    4. Move mouse and use keyboard - input will be sent to iPad
    5. Press Ctrl+Alt+Q to exit
"""

import sys
import signal
import asyncio
import argparse
from ble_hid_profile import BLEHIDProfile
from input_capture import InputCapture


class IPadRemote:
    """Main application class for iPad Remote."""

    def __init__(self, device_name: str = "iPad Remote"):
        self.device_name = device_name
        self.hid_profile: BLEHIDProfile = None
        self.input_capture: InputCapture = None
        self.running = False
        self.loop: asyncio.AbstractEventLoop = None

    def on_keyboard_event(self, modifier_keys: int, keys: list):
        """Handle keyboard events from input capture."""
        if self.hid_profile and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.hid_profile.send_keyboard_report(modifier_keys, keys),
                self.loop
            )

    def on_mouse_event(self, buttons: int, x: int, y: int, wheel: int):
        """Handle mouse events from input capture."""
        if self.hid_profile and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.hid_profile.send_mouse_report(buttons, x, y, wheel),
                self.loop
            )

    async def run(self):
        """Run the iPad Remote service."""
        print("=" * 60)
        print("iPad Remote - BLE HID Controller")
        print("=" * 60)
        print()

        self.loop = asyncio.get_event_loop()

        # Initialize BLE HID profile
        print("Initializing BLE HID profile...")
        self.hid_profile = BLEHIDProfile(self.device_name)

        try:
            # Start BLE server
            await self.hid_profile.start()

            print()
            print("-" * 60)
            print("READY FOR PAIRING")
            print("-" * 60)
            print()
            print("On your iPad:")
            print("  1. Go to Settings > Bluetooth")
            print("  2. Make sure Bluetooth is ON")
            print(f"  3. Look for '{self.device_name}' in the device list")
            print("  4. Tap to pair and connect")
            print()
            print("Once connected:")
            print("  - Start screen mirroring from iPad to see the display")
            print("  - Focus the UxPlay window to send keyboard/mouse to iPad")
            print("  - Press Ctrl+Alt+Q to disconnect and exit")
            print()

            # Initialize input capture
            self.input_capture = InputCapture(
                keyboard_callback=self.on_keyboard_event,
                mouse_callback=self.on_mouse_event
            )

            self.running = True
            self.input_capture.start()

            # Keep running until interrupted
            while self.running:
                await asyncio.sleep(0.1)

        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.stop()

    async def stop(self):
        """Stop the iPad Remote service."""
        if not self.running:
            return

        self.running = False
        print("\nShutting down iPad Remote...")

        if self.input_capture:
            self.input_capture.stop()

        if self.hid_profile:
            await self.hid_profile.stop()

        print("Goodbye!")

    def start(self):
        """Start the application (blocking)."""
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}")
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        asyncio.run(self.run())


def main():
    parser = argparse.ArgumentParser(
        description="Control your iPad with your laptop's keyboard and mouse via BLE HID"
    )
    parser.add_argument(
        "--name",
        default="iPad Remote",
        help="Bluetooth device name (default: iPad Remote)"
    )
    args = parser.parse_args()

    app = IPadRemote(device_name=args.name)
    app.start()


if __name__ == "__main__":
    main()
