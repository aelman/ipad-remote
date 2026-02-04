#!/bin/bash
# iPad Remote - Setup script
# Installs required system packages and Python dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "iPad Remote - Setup"
echo "============================================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script requires root privileges to install packages."
    echo "Please run with: sudo $0"
    exit 1
fi

echo "Installing system packages..."
apt update
apt install -y \
    uxplay \
    python3-dbus \
    python3-gi \
    python3-venv \
    bluez \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav

echo ""
echo "Setting up Python virtual environment..."

# Create venv with system site packages (for dbus and gi)
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    python3 -m venv --system-site-packages "$SCRIPT_DIR/venv"
fi

# Install pip packages
source "$SCRIPT_DIR/venv/bin/activate"
pip install --upgrade pip
pip install python-xlib

echo ""
echo "Configuring Bluetooth..."

# Enable Bluetooth service
systemctl enable bluetooth
systemctl start bluetooth

# Make Bluetooth adapter discoverable (temporary)
bluetoothctl power on
bluetoothctl discoverable on
bluetoothctl pairable on

echo ""
echo "============================================================"
echo "Setup complete!"
echo "============================================================"
echo ""
echo "To run iPad Remote:"
echo "  sudo ./run.sh"
echo ""
echo "Or run components separately:"
echo "  1. Start AirPlay receiver: uxplay -n 'iPad Remote Display'"
echo "  2. Start HID service: sudo python3 main.py"
echo ""
