#!/bin/bash
# iPad Remote - Uninstallation script

set -e

echo "Uninstalling iPad Remote..."

# Remove desktop file
rm -f ~/.local/share/applications/ipad-remote.desktop
echo "✓ Removed desktop file"

# Remove polkit policy (requires sudo)
POLICY_FILE="/usr/share/polkit-1/actions/com.github.ipad-remote.policy"
if [ -f "$POLICY_FILE" ]; then
    if [ "$EUID" -ne 0 ]; then
        echo ""
        echo "Removing polkit policy (requires sudo)..."
        sudo rm -f "$POLICY_FILE"
    else
        rm -f "$POLICY_FILE"
    fi
    echo "✓ Removed polkit policy"
fi

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
fi

echo ""
echo "Uninstallation complete!"
