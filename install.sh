#!/usr/bin/env bash
# Install KSnapMark for the current user (no sudo needed).
#   ./install.sh                  install / upgrade (starts KSnapMark in the background)
#   ./install.sh --no-autostart   install, but do not start at login
#   ./install.sh --uninstall      remove (your ideas collection is kept)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
prefix="$data_home/ksnapmark-app"
bin_dir="$HOME/.local/bin"
apps_dir="$data_home/applications"
autostart_dir="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
autostart_file="$autostart_dir/ksnapmark-daemon.desktop"

if [[ "${1:-}" == "--uninstall" ]]; then
    "$bin_dir/ksnapmark" --quit >/dev/null 2>&1 || true
    rm -rf "$prefix" "$bin_dir/ksnapmark" "$apps_dir/ksnapmark.desktop" "$apps_dir/ksnapmark-ideas.desktop" \
        "$autostart_file" "$data_home/icons/hicolor/scalable/apps/ksnapmark.svg"
    echo "KSnapMark removed. Your ideas collection is still in $data_home/ksnapmark"
    exit 0
fi

if ! command -v python3 >/dev/null || ! python3 -c "import PySide6" 2>/dev/null; then
    echo "PySide6 is missing. Please install it first:  sudo pacman -S pyside6"
    exit 1
fi

# Remove leftovers of the former version "snapmark" (data is kept and migrated on first start).
if [[ -x "$bin_dir/snapmark" ]]; then
    "$bin_dir/snapmark" --quit >/dev/null 2>&1 || true
    sleep 1
fi
rm -rf "$data_home/snapmark-app" "$bin_dir/snapmark" "$apps_dir/snapmark.desktop" \
    "$apps_dir/snapmark-ideas.desktop" "$autostart_dir/snapmark-daemon.desktop"

# Stop an older version running in the background so the new code gets loaded.
if [[ -x "$bin_dir/ksnapmark" ]]; then
    "$bin_dir/ksnapmark" --quit >/dev/null 2>&1 || true
    sleep 1
fi

mkdir -p "$prefix" "$bin_dir" "$apps_dir"
rm -rf "$prefix/ksnapmark"
cp -r "$here/ksnapmark" "$prefix/"
find "$prefix" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

icons_dir="$data_home/icons/hicolor/scalable/apps"
mkdir -p "$icons_dir"
cp "$here/ksnapmark/data/ksnapmark.svg" "$icons_dir/ksnapmark.svg"

cat > "$bin_dir/ksnapmark" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$prefix\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m ksnapmark "\$@"
EOF
chmod +x "$bin_dir/ksnapmark"

cat > "$apps_dir/ksnapmark.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=KSnapMark
Comment=Capture, edit and share screenshots
Comment[de]=Screenshot aufnehmen, bearbeiten und teilen
Exec=$bin_dir/ksnapmark
Icon=ksnapmark
Terminal=false
Categories=Utility;Graphics;
Keywords=Screenshot;Capture;Bildschirmfoto;OCR;
EOF

cat > "$apps_dir/ksnapmark-ideas.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=KSnapMark Ideas Collection
Name[de]=KSnapMark Ideen-Sammlung
Comment=Browse collected screenshots and ideas
Comment[de]=Gesammelte Screenshots und Ideen durchsuchen
Exec=$bin_dir/ksnapmark --ideas
Icon=ksnapmark
Terminal=false
Categories=Utility;Graphics;
EOF

if [[ "${1:-}" != "--no-autostart" ]]; then
    mkdir -p "$autostart_dir"
    cat > "$autostart_file" <<EOF
[Desktop Entry]
Type=Application
Name=KSnapMark
Comment=Screenshot tool running in the background (tray icon)
Comment[de]=Screenshot-Werkzeug im Hintergrund (Tray-Symbol)
Exec=$bin_dir/ksnapmark --daemon
Icon=ksnapmark
Terminal=false
X-KDE-autostart-after=panel
X-GNOME-Autostart-enabled=true
EOF
    echo "Autostart:        KSnapMark will start at login (can be switched off in the tray menu)"
fi

echo "Installed to $prefix"
echo "Command:          $bin_dir/ksnapmark"
case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) echo "Note: $bin_dir is not in your PATH – please add it to your shell configuration." ;;
esac
echo
"$bin_dir/ksnapmark" --doctor || true
echo

# Start in the background now if a graphical session is running.
if [[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]]; then
    setsid "$bin_dir/ksnapmark" --daemon >/dev/null 2>&1 &
    echo "KSnapMark is now running in the background – the icon appears in the system tray."
    echo
fi
echo "Next step: bind a keyboard shortcut to the command 'ksnapmark' (see README.md)."
