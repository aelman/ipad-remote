# iPad Remote

Control your iPad using your Linux laptop's keyboard and mouse.

iPad Remote exposes your laptop as a Bluetooth LE HID device that your iPad can connect to. Combined with AirPlay screen mirroring (via UxPlay), this lets you view and control your iPad directly from your laptop.

## Features

- Bluetooth LE HID keyboard and mouse emulation
- AirPlay screen mirroring via UxPlay
- Automatic cursor hiding when controlling iPad
- GNOME desktop integration
- Exit hotkey: Ctrl+Alt+Q

## Requirements

- Linux with BlueZ (tested on Ubuntu/Debian)
- X11 display server
- iPad with Bluetooth enabled

## Installation

```bash
# Install system dependencies and create virtual environment
sudo ./setup.sh

# Install desktop launcher (optional)
./install.sh
```

## Usage

### From Desktop

Launch "iPad Remote" from your applications menu.

### From Terminal

```bash
./ipad-remote-launcher
```

### Connecting Your iPad

1. Launch iPad Remote on your laptop
2. On your iPad, go to **Settings > Bluetooth**
3. Find and tap **iPad Remote** to pair
4. Start screen mirroring from your iPad's Control Center
5. Focus the UxPlay window to send input to your iPad

### Controls

- Keyboard input is forwarded when UxPlay window is focused
- Mouse movement and clicks are sent as relative motion
- Scroll wheel works with natural scrolling
- Press **Ctrl+Alt+Q** to exit

## Uninstalling

```bash
./uninstall.sh
```

## How It Works

- **BLE HID over GATT (HoGP)** - Exposes the laptop as a Bluetooth LE keyboard/mouse that iOS devices can connect to natively
- **X11 RECORD extension** - Captures keyboard and mouse input from the laptop
- **UxPlay** - Receives AirPlay screen mirroring from the iPad

## Troubleshooting

**iPad doesn't see the device:**
- Make sure Bluetooth is enabled on both devices
- Try restarting the Bluetooth service: `sudo systemctl restart bluetooth`

**No input sent to iPad:**
- Make sure the UxPlay window is focused
- Check that the iPad shows as connected in Bluetooth settings

**Screen mirroring not working:**
- Ensure UxPlay is running (it starts automatically with the launcher)
- Check that your iPad and laptop are on the same network for AirPlay

## License

MIT
