# Anzeiger

Ein einfacher Internet-Browser in Python, der Webseiten als reinen Text darstellt.

- Nur **HTTP** und **HTTPS** (auch bei Weiterleitungen).
- Kein CSS, kein JavaScript, keine Popups.
- Überschriften `h1`–`h6`, Absätze, Hervorhebungen, `pre`/`code`, Zitate,
  geordnete (`1.`, `a.`, `i.` …) und ungeordnete (`*`) Listen beliebig verschachtelt,
  Einträge mit Unterlisten lassen sich per Klick auf ▾/▸ ein- und ausklappen,
  Definitionslisten, Trennlinien, Tabellen (mit `colspan`/`rowspan`) als Raster.
  Layout-Tabellen (Tabellen, die weitere Tabellen enthalten) werden zeilenweise
  dargestellt.
- Links sind unterstrichen; beim Überfahren erscheint die Adresse in der Statuszeile.
  Sprünge zu `#anker` innerhalb der Seite.
- Bilder (`img`) werden nur geladen, wenn sie auf **demselben Server** liegen (gleiche
  Domain, Subdomains zählen mit, z.B. `www.a.de` und `cdn.a.de`) und PNG, JPEG, GIF, BMP oder WebP sind.
  Sonst erscheint ein Platzhalter `[Bild: alt-Text]` mit Begründung beim Überfahren.
- Direkt aufgerufene Bildadressen (z.B. ein Link auf `foto.jpg`) werden als eigene Seite
  angezeigt, auf Fensterbreite verkleinert, darunter Format und Originalgröße.
- Ganze Listen lassen sich über die Zeile „▾ Liste (n Einträge)“ einklappen.
- Formulare (Text, Passwort, Ankreuz-/Optionsfelder, Auswahllisten, Textbereiche) lassen sich
  ausfüllen und per GET oder POST abschicken. Kein Datei-Upload.
- Tabs: mehrere Seiten in einem Fenster, jede mit eigenem Verlauf. Links öffnen per
  Mittelklick oder Strg+Klick im Hintergrund; geschlossene Tabs lassen sich mit
  Strg+Umschalt+T wieder öffnen. Rechtsklick auf einen Tab öffnet ein Menü.
- Lesezeichen: Stern ☆ bzw. Strg+D, Menü „Lesezeichen“, Verwaltung auf `about:bookmarks`.
  Gespeichert in `~/.config/anzeiger/bookmarks.html` im Netscape-Bookmark-Format, das Chrome
  und Firefox importieren und exportieren.
- Cookies nur im Arbeitsspeicher, keine Drittanbieter-Cookies; abschalt- und löschbar.
- Eingebaute Seiten: Startseite `about:start` (Knopf ⌂), Änderungsprotokoll
  `about:changelog`, Lesezeichen `about:bookmarks` und Einstellungen `about:config`,
  auf der Startseite verlinkt.
  Die Einstellungen liegen in `~/.config/anzeiger/settings.json`.

## Versionen und Änderungsprotokoll

Die Versionsnummer (`anzeiger/__init__.py` und `pyproject.toml`) folgt dem Schema
Major.Minor.Patch. Jede Änderung wird in `anzeiger/changelog.html` beschrieben.

## Voraussetzungen

- Python ≥ 3.10 mit tkinter (Debian/Ubuntu: Paket `python3-tk`)
- Pillow

## Starten

```sh
python3 -m anzeiger                      # Startseite
python3 -m anzeiger https://example.org  # direkt eine Adresse öffnen
```

oder nach `pip install .` (z.B. in einer virtuellen Umgebung) mit dem Befehl `anzeiger`.

## Systemweit installieren (alle Benutzer)

```sh
sudo apt install python3-tk python3-pil   # falls noch nicht vorhanden
sudo ./install.sh
```

Danach steht „Anzeiger“ mit Zeitungssymbol im Anwendungsmenü, und jeder Benutzer kann
`anzeiger [ADRESSE]` aufrufen. Installiert wird nach `/opt/anzeiger/` (Programm),
`/usr/local/bin/anzeiger` (Startbefehl), `/usr/local/share/applications/` (Menüeintrag) und
`/usr/local/share/icons/hicolor/` (Symbole); die Orte lassen sich mit `APPDIR=…` und
`PREFIX=…` ändern. Erneutes Ausführen aktualisiert, `sudo ./uninstall.sh` entfernt alles.
Einstellungen und Lesezeichen bleiben pro Benutzer in `~/.config/anzeiger/`.

`sudo pip install .` ist unter aktuellen Debian/Ubuntu-Versionen absichtlich gesperrt
(PEP 668); `install.sh` braucht weder pip noch Internet.

## Tastenkürzel

| Taste                 | Wirkung               |
|-----------------------|-----------------------|
| Enter / „Los“         | Adresse laden         |
| Strg+L                | Adresszeile auswählen |
| Alt+Links / Alt+Rechts| Zurück / Vor          |
| Alt+Pos1 / ⌂          | Startseite            |
| Strg+D / ☆            | Lesezeichen setzen/entfernen |
| Strg+Umschalt+O       | Lesezeichen verwalten |
| Strg+T / +            | Neuer Tab             |
| Strg+W / Mittelklick auf Tab | Tab schließen  |
| Strg+Umschalt+T       | Geschlossenen Tab wieder öffnen |
| Strg+Tab / Strg+Umschalt+Tab | Nächster / vorheriger Tab |
| Strg+1 … 8 / Strg+9   | Tab Nr. 1 … 8 / letzter Tab |
| Mittel- oder Strg+Klick auf Link | Link in neuem Tab öffnen |
| Enter in Textfeld     | Formular abschicken   |
| F5                    | Neu laden             |
| Esc                   | Laden abbrechen       |

## Tests

```sh
python3 -m unittest discover -s tests
```

## Aufbau

| Modul                 | Aufgabe                                                    |
|-----------------------|------------------------------------------------------------|
| `anzeiger/net.py`     | HTTP-GET/POST, nur http/https, Cookies, Größenlimits, Zeichensatz |
| `anzeiger/dom.py`     | fehlertoleranter HTML-Baum auf Basis von `html.parser`     |
| `anzeiger/layout.py`  | Baum → Darstellungsanweisungen (Listen, Tabellen …), ohne Tk |
| `anzeiger/pages.py`   | eingebaute Seiten (Start, Änderungsprotokoll, Lesezeichen, Einstellungen, Fehler) |
| `anzeiger/forms.py`   | Formulardaten kodieren, GET-/POST-Anfrage bestimmen        |
| `anzeiger/bookmarks.py`| Lesezeichen-Datei im Netscape-Format (Chrome/Firefox)    |
| `anzeiger/settings.py`| Einstellungen in `~/.config/anzeiger/settings.json`        |
| `anzeiger/changelog.html` | Änderungsprotokoll                                     |
| `anzeiger/icons/`     | Programmsymbol (SVG, PNG 16–256 px)                        |
| `install.sh`, `uninstall.sh`, `data/anzeiger.desktop` | systemweite Installation, Menüeintrag |
| `anzeiger/images.py`  | sicheres Dekodieren/Skalieren erlaubter Bildformate        |
| `anzeiger/view.py`    | Anzeige im tkinter-Textfeld, Links, Formularfelder, Klappen |
| `anzeiger/app.py`     | Fenster, Adresszeile, Verlauf, Laden im Hintergrund        |
