"""
Bluetooth HID Profile for exposing laptop as keyboard/mouse to iPad.

This module creates a Bluetooth HID device profile using BlueZ D-Bus API.
The iPad will see this as a standard Bluetooth keyboard and mouse.
"""

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import socket
import subprocess
import os
import time
import threading


# Bluetooth HID ports
PSM_CTRL = 0x11  # HID Control channel
PSM_INTR = 0x13  # HID Interrupt channel

# HID Report Descriptor for keyboard + mouse combo device
HID_REPORT_DESCRIPTOR = bytes([
    # Keyboard
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x06,        # Usage (Keyboard)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID (1)
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0xE0,        #   Usage Minimum (224)
    0x29, 0xE7,        #   Usage Maximum (231)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x01,        #   Logical Maximum (1)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x08,        #   Report Count (8)
    0x81, 0x02,        #   Input (Data, Variable, Absolute) - Modifier keys
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x08,        #   Report Size (8)
    0x81, 0x01,        #   Input (Constant) - Reserved byte
    0x95, 0x06,        #   Report Count (6)
    0x75, 0x08,        #   Report Size (8)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x65,        #   Logical Maximum (101)
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0x00,        #   Usage Minimum (0)
    0x29, 0x65,        #   Usage Maximum (101)
    0x81, 0x00,        #   Input (Data, Array) - Key array
    0xC0,              # End Collection

    # Mouse
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x02,        #   Report ID (2)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x05, 0x09,        #     Usage Page (Buttons)
    0x19, 0x01,        #     Usage Minimum (1)
    0x29, 0x03,        #     Usage Maximum (3)
    0x15, 0x00,        #     Logical Minimum (0)
    0x25, 0x01,        #     Logical Maximum (1)
    0x95, 0x03,        #     Report Count (3)
    0x75, 0x01,        #     Report Size (1)
    0x81, 0x02,        #     Input (Data, Variable, Absolute) - Buttons
    0x95, 0x01,        #     Report Count (1)
    0x75, 0x05,        #     Report Size (5)
    0x81, 0x01,        #     Input (Constant) - Padding
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x09, 0x38,        #     Usage (Wheel)
    0x15, 0x81,        #     Logical Minimum (-127)
    0x25, 0x7F,        #     Logical Maximum (127)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x03,        #     Report Count (3)
    0x81, 0x06,        #     Input (Data, Variable, Relative) - X, Y, Wheel
    0xC0,              #   End Collection
    0xC0,              # End Collection
])


class HIDProfile:
    """Manages the Bluetooth HID profile registration and connections."""

    PROFILE_PATH = "/org/bluez/hid_profile"

    # SDP Record for HID device
    SDP_RECORD = f'''<?xml version="1.0" encoding="UTF-8" ?>
    <record>
        <attribute id="0x0001">
            <sequence>
                <uuid value="0x1124"/>
            </sequence>
        </attribute>
        <attribute id="0x0004">
            <sequence>
                <sequence>
                    <uuid value="0x0100"/>
                    <uint16 value="0x0011"/>
                </sequence>
                <sequence>
                    <uuid value="0x0011"/>
                </sequence>
            </sequence>
        </attribute>
        <attribute id="0x0005">
            <sequence>
                <uuid value="0x1002"/>
            </sequence>
        </attribute>
        <attribute id="0x0006">
            <sequence>
                <uint16 value="0x656e"/>
                <uint16 value="0x006a"/>
                <uint16 value="0x0100"/>
            </sequence>
        </attribute>
        <attribute id="0x0009">
            <sequence>
                <sequence>
                    <uuid value="0x1124"/>
                    <uint16 value="0x0100"/>
                </sequence>
            </sequence>
        </attribute>
        <attribute id="0x000d">
            <sequence>
                <sequence>
                    <sequence>
                        <uuid value="0x0100"/>
                        <uint16 value="0x0013"/>
                    </sequence>
                    <sequence>
                        <uuid value="0x0011"/>
                    </sequence>
                </sequence>
            </sequence>
        </attribute>
        <attribute id="0x0100">
            <text value="iPad Remote"/>
        </attribute>
        <attribute id="0x0101">
            <text value="Keyboard and Mouse"/>
        </attribute>
        <attribute id="0x0102">
            <text value="Linux HID"/>
        </attribute>
        <attribute id="0x0200">
            <uint16 value="0x0100"/>
        </attribute>
        <attribute id="0x0201">
            <uint16 value="0x0111"/>
        </attribute>
        <attribute id="0x0202">
            <uint8 value="0xC0"/>
        </attribute>
        <attribute id="0x0203">
            <uint8 value="0x00"/>
        </attribute>
        <attribute id="0x0204">
            <boolean value="true"/>
        </attribute>
        <attribute id="0x0205">
            <boolean value="true"/>
        </attribute>
        <attribute id="0x0206">
            <sequence>
                <sequence>
                    <uint8 value="0x22"/>
                    <text encoding="hex" value="{HID_REPORT_DESCRIPTOR.hex()}"/>
                </sequence>
            </sequence>
        </attribute>
        <attribute id="0x0207">
            <sequence>
                <sequence>
                    <uint16 value="0x0409"/>
                    <uint16 value="0x0100"/>
                </sequence>
            </sequence>
        </attribute>
        <attribute id="0x020b">
            <uint16 value="0x0100"/>
        </attribute>
        <attribute id="0x020c">
            <uint16 value="0x0c80"/>
        </attribute>
        <attribute id="0x020d">
            <boolean value="false"/>
        </attribute>
        <attribute id="0x020e">
            <boolean value="true"/>
        </attribute>
        <attribute id="0x020f">
            <uint16 value="0x0640"/>
        </attribute>
        <attribute id="0x0210">
            <uint16 value="0x0320"/>
        </attribute>
    </record>
    '''

    def __init__(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        self.mainloop = None
        self.ctrl_sock = None
        self.intr_sock = None
        self.ctrl_client = None
        self.intr_client = None
        self.connected = False
        self.target_address = None

    def configure_adapter(self, device_name: str = "iPad Remote"):
        """Configure the Bluetooth adapter for HID device mode."""
        adapter_path = "/org/bluez/hci0"
        adapter = dbus.Interface(
            self.bus.get_object("org.bluez", adapter_path),
            "org.freedesktop.DBus.Properties"
        )

        # Set device class to Peripheral (keyboard + pointing device combo)
        try:
            subprocess.run(
                ["hciconfig", "hci0", "class", "0x002540"],
                check=True, capture_output=True
            )
            print("Device class set to Peripheral (keyboard+mouse)")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not set device class: {e}")

        # Set device name
        try:
            subprocess.run(
                ["hciconfig", "hci0", "name", device_name],
                check=True, capture_output=True
            )
            print(f"Device name set to '{device_name}'")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not set device name: {e}")

        # Configure via D-Bus
        adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
        adapter.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(True))
        adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(0))
        adapter.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(True))
        adapter.Set("org.bluez.Adapter1", "PairableTimeout", dbus.UInt32(0))

        try:
            adapter.Set("org.bluez.Adapter1", "Alias", dbus.String(device_name))
        except Exception:
            pass

        print("Bluetooth adapter configured for HID mode")

    def register_sdp(self):
        """Register SDP record using sdptool."""
        # Write SDP record to temp file
        sdp_file = "/tmp/hid_sdp.xml"
        with open(sdp_file, "w") as f:
            f.write(self.SDP_RECORD)

        # Register with sdptool
        try:
            result = subprocess.run(
                ["sdptool", "add", "--channel=17", "HID"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print("SDP HID service registered")
            else:
                print(f"Warning: sdptool returned: {result.stderr}")
        except Exception as e:
            print(f"Warning: Could not register SDP: {e}")

    def get_adapter_address(self):
        """Get the Bluetooth adapter's MAC address."""
        adapter_path = "/org/bluez/hci0"
        adapter = dbus.Interface(
            self.bus.get_object("org.bluez", adapter_path),
            "org.freedesktop.DBus.Properties"
        )
        return str(adapter.Get("org.bluez.Adapter1", "Address"))

    def setup_sockets(self):
        """Set up L2CAP sockets for HID control and interrupt channels."""
        adapter_addr = self.get_adapter_address()
        print(f"Using Bluetooth adapter: {adapter_addr}")

        # Close any existing sockets
        for sock in [self.ctrl_sock, self.intr_sock]:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        self.ctrl_sock = None
        self.intr_sock = None

        # Try to create sockets with retries
        max_retries = 5
        for attempt in range(max_retries):
            try:
                # Control channel
                self.ctrl_sock = socket.socket(
                    socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
                )
                self.ctrl_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.ctrl_sock.bind((adapter_addr, PSM_CTRL))
                self.ctrl_sock.listen(1)

                # Interrupt channel
                self.intr_sock = socket.socket(
                    socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
                )
                self.intr_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.intr_sock.bind((adapter_addr, PSM_INTR))
                self.intr_sock.listen(1)

                print(f"Listening on L2CAP PSM {PSM_CTRL} (control) and {PSM_INTR} (interrupt)")
                return

            except OSError as e:
                if e.errno == 98:  # Address in use
                    if self.ctrl_sock:
                        self.ctrl_sock.close()
                        self.ctrl_sock = None
                    if self.intr_sock:
                        self.intr_sock.close()
                        self.intr_sock = None

                    if attempt < max_retries - 1:
                        print(f"Sockets in use (attempt {attempt + 1}/{max_retries}), waiting...")
                        # Try killing any process using the port
                        subprocess.run(
                            ["fuser", "-k", "17/bluetooth", "19/bluetooth"],
                            capture_output=True
                        )
                        time.sleep(3)
                    else:
                        raise OSError(
                            "Could not bind to HID ports. Try running:\n"
                            "  sudo systemctl stop bluetooth\n"
                            "  sudo killall bluetoothd\n"
                            "  sudo systemctl start bluetooth\n"
                            "Then run this app again."
                        )
                else:
                    raise

    def accept_connections(self):
        """Accept incoming connections on both channels."""
        print("Waiting for iPad to connect...")

        # Set socket timeouts for better interrupt handling
        self.ctrl_sock.settimeout(1.0)
        self.intr_sock.settimeout(1.0)

        ctrl_connected = False
        intr_connected = False

        while not (ctrl_connected and intr_connected):
            if not ctrl_connected:
                try:
                    self.ctrl_client, ctrl_addr = self.ctrl_sock.accept()
                    print(f"Control channel connected from {ctrl_addr[0]}")
                    self.target_address = ctrl_addr[0]
                    ctrl_connected = True
                except socket.timeout:
                    pass

            if ctrl_connected and not intr_connected:
                try:
                    self.intr_client, intr_addr = self.intr_sock.accept()
                    print(f"Interrupt channel connected from {intr_addr[0]}")
                    intr_connected = True
                except socket.timeout:
                    pass

        self.connected = True
        print("HID connection established!")
        return True

    def send_keyboard_report(self, modifier_keys: int, keys: list):
        """Send a keyboard HID report."""
        if not self.intr_client or not self.connected:
            return

        keys = (keys + [0] * 6)[:6]
        report = bytes([0xA1, 0x01, modifier_keys, 0x00] + keys)

        try:
            self.intr_client.send(report)
        except Exception as e:
            print(f"Failed to send keyboard report: {e}")
            self.connected = False

    def send_mouse_report(self, buttons: int, x: int, y: int, wheel: int = 0):
        """Send a mouse HID report."""
        if not self.intr_client or not self.connected:
            return

        x = max(-127, min(127, x))
        y = max(-127, min(127, y))
        wheel = max(-127, min(127, wheel))

        x_byte = x & 0xFF
        y_byte = y & 0xFF
        wheel_byte = wheel & 0xFF

        report = bytes([0xA1, 0x02, buttons, x_byte, y_byte, wheel_byte])

        try:
            self.intr_client.send(report)
        except Exception as e:
            print(f"Failed to send mouse report: {e}")
            self.connected = False

    def close(self):
        """Clean up connections and sockets."""
        self.connected = False
        for client in [self.ctrl_client, self.intr_client]:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
        for sock in [self.ctrl_sock, self.intr_sock]:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        print("HID profile closed")


def main():
    """Test the HID profile setup."""
    profile = HIDProfile()

    try:
        profile.configure_adapter()
        profile.register_sdp()
        profile.setup_sockets()
        profile.accept_connections()

        print("HID device ready! Press Ctrl+C to exit.")

        # Test: send some mouse movements
        for i in range(10):
            profile.send_mouse_report(0, 10, 0)
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        profile.close()


if __name__ == "__main__":
    main()
