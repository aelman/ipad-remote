#!/bin/bash
# iPad Remote - Launch script
# Starts both the AirPlay receiver (for screen mirroring) and the Bluetooth HID service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for required packages
check_packages() {
    local missing=()

    if ! command -v uxplay &> /dev/null; then
        missing+=("uxplay")
    fi

    if ! dpkg -l python3-dbus &> /dev/null 2>&1; then
        missing+=("python3-dbus")
    fi

    if ! dpkg -l python3-gi &> /dev/null 2>&1; then
        missing+=("python3-gi")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo "Missing packages: ${missing[*]}"
        echo "Install with: sudo apt install ${missing[*]}"
        exit 1
    fi
}

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down..."

    # Kill UxPlay if running
    if [ -n "$UXPLAY_PID" ] && kill -0 "$UXPLAY_PID" 2>/dev/null; then
        kill "$UXPLAY_PID" 2>/dev/null || true
    fi

    # Kill Python HID process
    if [ -n "$HID_PID" ] && kill -0 "$HID_PID" 2>/dev/null; then
        kill "$HID_PID" 2>/dev/null || true
    fi

    echo "Goodbye!"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Print banner
echo "============================================================"
echo "iPad Remote"
echo "============================================================"
echo ""

# Check if running as root (needed for Bluetooth HID)
if [ "$EUID" -ne 0 ]; then
    echo "This script requires root privileges for Bluetooth HID."
    echo "Please run with: sudo $0"
    exit 1
fi

check_packages

echo "Starting AirPlay receiver (UxPlay)..."
echo "Your iPad should see this computer as an AirPlay destination."
echo ""

# Start UxPlay in background
# -n: Set the AirPlay server name
# -p: Allow pairing
uxplay -n "iPad Remote Display" -nc &
UXPLAY_PID=$!

sleep 2

if ! kill -0 "$UXPLAY_PID" 2>/dev/null; then
    echo "ERROR: Failed to start UxPlay"
    exit 1
fi

echo "AirPlay receiver started (PID: $UXPLAY_PID)"
echo ""
echo "------------------------------------------------------------"
echo "INSTRUCTIONS"
echo "------------------------------------------------------------"
echo ""
echo "1. SCREEN MIRRORING (already running):"
echo "   - On your iPad, open Control Center"
echo "   - Tap 'Screen Mirroring'"
echo "   - Select 'iPad Remote Display'"
echo ""
echo "2. KEYBOARD/MOUSE CONTROL:"
echo "   - On your iPad, go to Settings > Bluetooth"
echo "   - Connect to 'iPad Remote'"
echo "   - Once connected, your laptop's keyboard and mouse"
echo "     will control the iPad"
echo ""
echo "Press Ctrl+C to exit"
echo "------------------------------------------------------------"
echo ""

# Activate venv and start HID service
source "$SCRIPT_DIR/venv/bin/activate"
python3 "$SCRIPT_DIR/main.py" &
HID_PID=$!

# Wait for processes
wait
