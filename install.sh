#!/bin/bash
# iPad Remote - Installation script
# Installs desktop integration for GNOME

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing iPad Remote..."

# Make launcher executable
chmod +x "$SCRIPT_DIR/ipad-remote-launcher"
echo "✓ Made launcher executable"

# Install polkit policy (requires sudo)
if [ "$EUID" -ne 0 ]; then
    echo ""
    echo "Installing polkit policy (requires sudo)..."
    sudo cp "$SCRIPT_DIR/com.github.ipad-remote.policy" /usr/share/polkit-1/actions/
else
    cp "$SCRIPT_DIR/com.github.ipad-remote.policy" /usr/share/polkit-1/actions/
fi
echo "✓ Installed polkit policy"

# Install desktop file
mkdir -p ~/.local/share/applications
cp "$SCRIPT_DIR/ipad-remote.desktop" ~/.local/share/applications/
echo "✓ Installed desktop file"

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
fi

echo ""
echo "Installation complete!"
echo ""
echo "You can now launch 'iPad Remote' from your applications menu."
echo "The first launch will ask for your password (for Bluetooth access)."
