#!/bin/sh
# Entfernt eine mit install.sh vorgenommene systemweite Installation:
#
#   sudo ./uninstall.sh
#
# Einstellungen und Lesezeichen der Benutzer (~/.config/anzeiger/) bleiben erhalten.
set -eu

APPDIR="${APPDIR:-/opt/anzeiger}"
PREFIX="${PREFIX:-/usr/local}"

if [ -e "$PREFIX/bin/anzeiger" ] && [ ! -w "$PREFIX/bin" ]; then
    echo "Fehler: keine Schreibrechte für $PREFIX – bitte mit sudo aufrufen." >&2
    exit 1
fi

rm -rf "${APPDIR:?}/anzeiger"
rmdir "$APPDIR" 2>/dev/null || true
rm -f "$PREFIX/bin/anzeiger" "$PREFIX/share/applications/anzeiger.desktop"
for size in 16 24 32 48 64 128 256; do
    rm -f "$PREFIX/share/icons/hicolor/${size}x${size}/apps/anzeiger.png"
done
rm -f "$PREFIX/share/icons/hicolor/scalable/apps/anzeiger.svg"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$PREFIX/share/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
fi

echo "Anzeiger entfernt. Benutzerdaten in ~/.config/anzeiger/ wurden nicht angetastet."
