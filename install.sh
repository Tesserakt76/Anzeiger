#!/bin/sh
# Installiert den Anzeiger systemweit für alle Benutzer:
#
#   sudo ./install.sh
#
# Programm:      /opt/anzeiger/anzeiger/          (APPDIR)
# Startbefehl:   /usr/local/bin/anzeiger          (PREFIX/bin)
# Menüeintrag:   /usr/local/share/applications/anzeiger.desktop
# Symbole:       /usr/local/share/icons/hicolor/…/apps/anzeiger.{png,svg}
#
# Benötigt das System-Python mit tkinter und Pillow, unter Debian/Ubuntu:
#   sudo apt install python3-tk python3-pil
# Empfohlen (Bilder erscheinen deutlich schneller): python3-pil.imagetk
# Einstellungen und Lesezeichen bleiben pro Benutzer in ~/.config/anzeiger/.
# Erneutes Ausführen aktualisiert eine bestehende Installation.
set -eu

APPDIR="${APPDIR:-/opt/anzeiger}"
PREFIX="${PREFIX:-/usr/local}"
SRC="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-$(command -v python3 || true)}"

if [ -z "$PYTHON" ]; then
    echo "Fehler: python3 nicht gefunden." >&2
    exit 1
fi
if ! "$PYTHON" -I -c 'import tomllib' 2>/dev/null; then
    echo "Fehler: $PYTHON ist zu alt, nötig ist Python 3.11 oder neuer." >&2
    exit 1
fi
if ! "$PYTHON" -I -c 'import tkinter, PIL' 2>/dev/null; then
    echo "Fehler: tkinter oder Pillow fehlt für $PYTHON." >&2
    echo "Unter Debian/Ubuntu: sudo apt install python3-tk python3-pil" >&2
    exit 1
fi
if ! "$PYTHON" -I -c 'from PIL import ImageTk' 2>/dev/null; then
    echo "Hinweis: Mit python3-pil.imagetk erscheinen Bilder deutlich schneller." >&2
fi
if [ ! -f "$SRC/anzeiger/app.py" ]; then
    echo "Fehler: $SRC/anzeiger/app.py fehlt – install.sh muss im Projektordner liegen." >&2
    exit 1
fi
if ! mkdir -p "$APPDIR" "$PREFIX/bin" 2>/dev/null || [ ! -w "$APPDIR" ] || [ ! -w "$PREFIX/bin" ]; then
    echo "Fehler: keine Schreibrechte für $APPDIR bzw. $PREFIX – bitte mit sudo aufrufen." >&2
    exit 1
fi

VERSION="$("$PYTHON" -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import anzeiger; print(anzeiger.__version__)' "$SRC")"
echo "Installiere Anzeiger $VERSION mit $PYTHON …"

# Programmdateien (alte Version vorher entfernen, ohne __pycache__ der Arbeitskopie)
rm -rf "${APPDIR:?}/anzeiger"
cp -R "$SRC/anzeiger" "$APPDIR/anzeiger"
find "$APPDIR/anzeiger" -name __pycache__ -type d -prune -exec rm -rf {} +
"$PYTHON" -I -m compileall -q "$APPDIR/anzeiger"
chmod -R u=rwX,go=rX "$APPDIR"
echo "  Programm:    $APPDIR/anzeiger"

# Startbefehl: System-Python im isolierten Modus (-I), damit weder das aktuelle
# Verzeichnis noch PYTHONPATH oder Benutzerpakete Code einschleusen können.
LAUNCHER="$PREFIX/bin/anzeiger"
cat > "$LAUNCHER.tmp" <<EOF
#!/bin/sh
# Startet den Anzeiger (installiert von install.sh, Version $VERSION).
exec "$PYTHON" -I -c 'import sys; sys.path.insert(0, "$APPDIR"); sys.argv[0] = "anzeiger"; from anzeiger.app import main; main()' "\$@"
EOF
chmod 755 "$LAUNCHER.tmp"
mv -f "$LAUNCHER.tmp" "$LAUNCHER"
echo "  Startbefehl: $LAUNCHER"

# Menüeintrag und Symbole
install -D -m 644 "$SRC/data/anzeiger.desktop" "$PREFIX/share/applications/anzeiger.desktop"
for size in 16 24 32 48 64 128 256; do
    install -D -m 644 "$SRC/anzeiger/icons/anzeiger-$size.png" \
        "$PREFIX/share/icons/hicolor/${size}x${size}/apps/anzeiger.png"
done
install -D -m 644 "$SRC/anzeiger/icons/anzeiger.svg" "$PREFIX/share/icons/hicolor/scalable/apps/anzeiger.svg"
echo "  Menüeintrag: $PREFIX/share/applications/anzeiger.desktop"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$PREFIX/share/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
fi

echo "Fertig. Start über das Anwendungsmenü oder mit: anzeiger [ADRESSE]"
