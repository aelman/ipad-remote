"""
Bluetooth Low Energy HID Profile (HoGP) for exposing laptop as keyboard/mouse to iPad.

Uses BlueZ D-Bus API directly for proper GATT service structure that iOS requires.
"""

import asyncio
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import struct
import threading


# HID Report Descriptor for keyboard + mouse combo
HID_REPORT_MAP = bytes([
    # Keyboard (Report ID 1)
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
    0x81, 0x02,        #   Input (Data, Variable, Absolute)
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x08,        #   Report Size (8)
    0x81, 0x01,        #   Input (Constant)
    0x95, 0x06,        #   Report Count (6)
    0x75, 0x08,        #   Report Size (8)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x65,        #   Logical Maximum (101)
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0x00,        #   Usage Minimum (0)
    0x29, 0x65,        #   Usage Maximum (101)
    0x81, 0x00,        #   Input (Data, Array)
    0xC0,              # End Collection

    # Mouse (Report ID 2)
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
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    0x95, 0x01,        #     Report Count (1)
    0x75, 0x05,        #     Report Size (5)
    0x81, 0x01,        #     Input (Constant)
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x09, 0x38,        #     Usage (Wheel)
    0x15, 0x81,        #     Logical Minimum (-127)
    0x25, 0x7F,        #     Logical Maximum (127)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x03,        #     Report Count (3)
    0x81, 0x06,        #     Input (Data, Variable, Relative)
    0xC0,              #   End Collection
    0xC0,              # End Collection
])

DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
BLUEZ_SERVICE = 'org.bluez'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'
AGENT_IFACE = 'org.bluez.Agent1'
AGENT_MANAGER_IFACE = 'org.bluez.AgentManager1'


class PairingAgent(dbus.service.Object):
    """Pairing agent that accepts all pairing requests."""
    PATH = '/org/bluez/hid/agent'

    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, self.PATH)

    @dbus.service.method(AGENT_IFACE, in_signature='', out_signature='')
    def Release(self):
        print("Agent released")

    @dbus.service.method(AGENT_IFACE, in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        print(f"AuthorizeService: {device} {uuid}")

    @dbus.service.method(AGENT_IFACE, in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        print(f"RequestPinCode: {device}")
        return "0000"

    @dbus.service.method(AGENT_IFACE, in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        print(f"RequestPasskey: {device}")
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_IFACE, in_signature='ouq', out_signature='')
    def DisplayPasskey(self, device, passkey, entered):
        print(f"DisplayPasskey: {device} {passkey:06d} entered={entered}")

    @dbus.service.method(AGENT_IFACE, in_signature='os', out_signature='')
    def DisplayPinCode(self, device, pincode):
        print(f"DisplayPinCode: {device} {pincode}")

    @dbus.service.method(AGENT_IFACE, in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        print(f"RequestConfirmation: {device} {passkey:06d} - auto-accepting")

    @dbus.service.method(AGENT_IFACE, in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        print(f"RequestAuthorization: {device} - auto-accepting")

    @dbus.service.method(AGENT_IFACE, in_signature='', out_signature='')
    def Cancel(self):
        print("Pairing cancelled")


class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/hid/advertisement'

    def __init__(self, bus, index, device_name):
        self.path = f'{self.PATH_BASE}{index}'
        self.bus = bus
        self.ad_type = 'peripheral'
        self.local_name = device_name
        # Appearance: 0x03C1 = Keyboard, 0x03C2 = Mouse, 0x03C0 = HID Generic
        self.appearance = 0x03C1  # Keyboard
        self.service_uuids = ['1812']  # HID Service
        self.discoverable = True
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = {
            LE_ADVERTISEMENT_IFACE: {
                'Type': self.ad_type,
                'LocalName': dbus.String(self.local_name),
                'Appearance': dbus.UInt16(self.appearance),
                'ServiceUUIDs': dbus.Array(self.service_uuids, signature='s'),
                'Discoverable': dbus.Boolean(self.discoverable),
            }
        }
        return properties

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.get_properties()[interface]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature='', out_signature='')
    def Release(self):
        print('Advertisement released')


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f'{service.path}/char{index}'
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.value = []
        self.notifying = False
        self.descriptors = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Descriptors': dbus.Array(
                    [d.get_path() for d in self.descriptors],
                    signature='o'
                ),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.get_properties()[interface]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        return self.value

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        self.value = value

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='', out_signature='')
    def StartNotify(self):
        self.notifying = True

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='', out_signature='')
    def StopNotify(self):
        self.notifying = False

    @dbus.service.signal(DBUS_PROP_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def notify(self, value):
        if not self.notifying:
            return
        self.value = value
        self.PropertiesChanged(GATT_CHRC_IFACE, {'Value': dbus.Array(value, signature='y')}, [])


class Descriptor(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, characteristic):
        self.path = f'{characteristic.path}/desc{index}'
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.chrc = characteristic
        self.value = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_DESC_IFACE: {
                'Characteristic': self.chrc.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.get_properties()[interface]

    @dbus.service.method(GATT_DESC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        return self.value

    @dbus.service.method(GATT_DESC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        self.value = value


class ReportReferenceDescriptor(Descriptor):
    """Report Reference Descriptor - required for HID Reports."""
    UUID = '2908'

    def __init__(self, bus, index, characteristic, report_id, report_type):
        # report_type: 1 = Input, 2 = Output, 3 = Feature
        self.report_id = report_id
        self.report_type = report_type
        super().__init__(bus, index, self.UUID, ['read'], characteristic)
        self.value = [report_id, report_type]


class CCCDescriptor(Descriptor):
    """Client Characteristic Configuration Descriptor."""
    UUID = '2902'

    def __init__(self, bus, index, characteristic):
        super().__init__(bus, index, self.UUID, ['read', 'write'], characteristic)
        self.value = [0x00, 0x00]

    @dbus.service.method(GATT_DESC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        self.value = list(value)
        # Check if notifications enabled (bit 0)
        if value[0] & 0x01:
            print(f"Notifications enabled for {self.chrc.uuid}")
            self.chrc.notifying = True
        else:
            print(f"Notifications disabled for {self.chrc.uuid}")
            self.chrc.notifying = False


class Service(dbus.service.Object):
    PATH_BASE = '/org/bluez/hid/service'

    def __init__(self, bus, index, uuid, primary):
        self.path = f'{self.PATH_BASE}{index}'
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    [c.get_path() for c in self.characteristics],
                    signature='o'
                ),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.get_properties()[interface]


class HIDService(Service):
    """HID Service implementation."""
    UUID = '1812'

    def __init__(self, bus, index):
        super().__init__(bus, index, self.UUID, True)
        self.keyboard_report = None
        self.mouse_report = None
        self._setup_characteristics()

    def _setup_characteristics(self):
        # HID Information
        hid_info = Characteristic(self.bus, 0, '2a4a', ['read'], self)
        hid_info.value = [0x11, 0x01, 0x00, 0x03]  # HID 1.11, no country, remote wake + normally connectable
        self.add_characteristic(hid_info)

        # Report Map
        report_map = Characteristic(self.bus, 1, '2a4b', ['read'], self)
        report_map.value = list(HID_REPORT_MAP)
        self.add_characteristic(report_map)

        # Protocol Mode
        protocol_mode = Characteristic(self.bus, 2, '2a4e', ['read', 'write-without-response'], self)
        protocol_mode.value = [0x01]  # Report Protocol
        self.add_characteristic(protocol_mode)

        # HID Control Point
        control_point = Characteristic(self.bus, 3, '2a4c', ['write-without-response'], self)
        control_point.value = [0x00]
        self.add_characteristic(control_point)

        # Keyboard Report (Input)
        self.keyboard_report = Characteristic(
            self.bus, 4, '2a4d',
            ['read', 'notify'],
            self
        )
        self.keyboard_report.value = [0x00] * 8
        # Add Report Reference Descriptor (Report ID 1, Input)
        kb_ref = ReportReferenceDescriptor(self.bus, 0, self.keyboard_report, 0x01, 0x01)
        self.keyboard_report.add_descriptor(kb_ref)
        # Add CCC Descriptor
        kb_ccc = CCCDescriptor(self.bus, 1, self.keyboard_report)
        self.keyboard_report.add_descriptor(kb_ccc)
        self.add_characteristic(self.keyboard_report)

        # Mouse Report (Input)
        self.mouse_report = Characteristic(
            self.bus, 5, '2a4d',
            ['read', 'notify'],
            self
        )
        self.mouse_report.value = [0x00] * 4
        # Add Report Reference Descriptor (Report ID 2, Input)
        mouse_ref = ReportReferenceDescriptor(self.bus, 0, self.mouse_report, 0x02, 0x01)
        self.mouse_report.add_descriptor(mouse_ref)
        # Add CCC Descriptor
        mouse_ccc = CCCDescriptor(self.bus, 1, self.mouse_report)
        self.mouse_report.add_descriptor(mouse_ccc)
        self.add_characteristic(self.mouse_report)


class BatteryService(Service):
    """Battery Service."""
    UUID = '180f'

    def __init__(self, bus, index):
        super().__init__(bus, index, self.UUID, True)
        self._setup_characteristics()

    def _setup_characteristics(self):
        battery_level = Characteristic(self.bus, 0, '2a19', ['read', 'notify'], self)
        battery_level.value = [100]  # 100%
        ccc = CCCDescriptor(self.bus, 0, battery_level)
        battery_level.add_descriptor(ccc)
        self.add_characteristic(battery_level)


class DeviceInfoService(Service):
    """Device Information Service."""
    UUID = '180a'

    def __init__(self, bus, index):
        super().__init__(bus, index, self.UUID, True)
        self._setup_characteristics()

    def _setup_characteristics(self):
        # Manufacturer Name
        mfr = Characteristic(self.bus, 0, '2a29', ['read'], self)
        mfr.value = list(b'Linux HID')
        self.add_characteristic(mfr)

        # PnP ID
        pnp = Characteristic(self.bus, 1, '2a50', ['read'], self)
        # Vendor ID Source (USB=2), Vendor ID, Product ID, Version
        pnp.value = list(struct.pack('<BHHH', 0x02, 0x1234, 0x5678, 0x0100))
        self.add_characteristic(pnp)


class Application(dbus.service.Object):
    """GATT Application."""
    PATH = '/org/bluez/hid'

    def __init__(self, bus):
        self.path = self.PATH
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.characteristics:
                response[chrc.get_path()] = chrc.get_properties()
                for desc in chrc.descriptors:
                    response[desc.get_path()] = desc.get_properties()
        return response


class BLEHIDProfile:
    """BLE HID Profile using BlueZ D-Bus API."""

    def __init__(self, device_name: str = "iPad Remote"):
        self.device_name = device_name
        self.bus = None
        self.mainloop = None
        self.app = None
        self.hid_service = None
        self.advertisement = None
        self.agent = None
        self.connected = False
        self._loop_thread = None

    def _find_adapter(self):
        """Find the Bluetooth adapter."""
        remote_om = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, '/'),
            DBUS_OM_IFACE
        )
        objects = remote_om.GetManagedObjects()

        for path, interfaces in objects.items():
            if LE_ADVERTISING_MANAGER_IFACE in interfaces:
                return path
        return None

    async def start(self):
        """Start the BLE HID server."""
        print(f"Starting BLE HID server as '{self.device_name}'...")

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()

        adapter_path = self._find_adapter()
        if not adapter_path:
            raise Exception("No BLE adapter found")

        print(f"Using adapter: {adapter_path}")

        # Set adapter properties
        adapter_props = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, adapter_path),
            DBUS_PROP_IFACE
        )
        adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(True))
        adapter_props.Set('org.bluez.Adapter1', 'Alias', dbus.String(self.device_name))
        adapter_props.Set('org.bluez.Adapter1', 'Discoverable', dbus.Boolean(True))
        adapter_props.Set('org.bluez.Adapter1', 'Pairable', dbus.Boolean(True))

        # Register pairing agent
        self.agent = PairingAgent(self.bus)
        agent_manager = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, '/org/bluez'),
            AGENT_MANAGER_IFACE
        )
        try:
            agent_manager.RegisterAgent(PairingAgent.PATH, "KeyboardDisplay")
            agent_manager.RequestDefaultAgent(PairingAgent.PATH)
            print("Pairing agent registered")
        except Exception as e:
            print(f"Agent registration: {e}")

        # Create application
        self.app = Application(self.bus)

        # Add services
        self.hid_service = HIDService(self.bus, 0)
        self.app.add_service(self.hid_service)
        self.app.add_service(DeviceInfoService(self.bus, 1))
        self.app.add_service(BatteryService(self.bus, 2))

        # Register application
        gatt_manager = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, adapter_path),
            GATT_MANAGER_IFACE
        )

        try:
            gatt_manager.RegisterApplication(
                self.app.get_path(),
                {},
                reply_handler=lambda: print("GATT application registered"),
                error_handler=lambda e: print(f"Failed to register GATT: {e}")
            )
        except Exception as e:
            print(f"GATT registration error: {e}")

        # Create and register advertisement
        self.advertisement = Advertisement(self.bus, 0, self.device_name)
        ad_manager = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE, adapter_path),
            LE_ADVERTISING_MANAGER_IFACE
        )

        try:
            ad_manager.RegisterAdvertisement(
                self.advertisement.get_path(),
                {},
                reply_handler=lambda: print("Advertisement registered"),
                error_handler=lambda e: print(f"Failed to register advertisement: {e}")
            )
        except Exception as e:
            print(f"Advertisement registration error: {e}")

        # Start GLib main loop in a thread
        self.mainloop = GLib.MainLoop()
        self._loop_thread = threading.Thread(target=self.mainloop.run, daemon=True)
        self._loop_thread.start()

        self.connected = True
        print("BLE HID server started")

    async def send_keyboard_report(self, modifier_keys: int, keys: list):
        """Send keyboard report via notification."""
        if not self.hid_service or not self.connected:
            return
        if not self.hid_service.keyboard_report.notifying:
            return

        keys = (keys + [0] * 6)[:6]
        report = [modifier_keys, 0x00] + keys

        try:
            self.hid_service.keyboard_report.notify(report)
        except Exception:
            pass

    async def send_mouse_report(self, buttons: int, x: int, y: int, wheel: int = 0):
        """Send mouse report via notification."""
        if not self.hid_service or not self.connected:
            return
        if not self.hid_service.mouse_report.notifying:
            return  # iPad hasn't enabled notifications yet

        x = max(-127, min(127, x))
        y = max(-127, min(127, y))
        wheel = max(-127, min(127, wheel))

        report = [buttons, x & 0xFF, y & 0xFF, wheel & 0xFF]

        try:
            self.hid_service.mouse_report.notify(report)
        except Exception:
            pass

    async def stop(self):
        """Stop the BLE server."""
        self.connected = False
        if self.mainloop:
            self.mainloop.quit()
        print("BLE HID server stopped")


async def main():
    """Test the BLE HID profile."""
    profile = BLEHIDProfile("iPad Remote")

    try:
        await profile.start()

        print("\nBLE HID device ready!")
        print("On your iPad:")
        print("  1. Go to Settings > Bluetooth")
        print("  2. Look for 'iPad Remote'")
        print("  3. Tap to pair and connect")
        print("\nPress Ctrl+C to exit")

        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await profile.stop()


if __name__ == "__main__":
    asyncio.run(main())
