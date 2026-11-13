# Anzeiger

**Deutsch** · [English](README.en.md) · [Esperanto](README.eo.md)

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
- Lesezeichen: Stern ☆ bzw. Strg+D, Menü „Lesezeichen“, Verwaltung auf `about:bookmarks`
  mit beliebig verschachtelten Ordnern (anlegen, umbenennen, verschieben, entfernen).
  Gespeichert in `~/.config/anzeiger/bookmarks.html` im Netscape-Bookmark-Format, das Chrome
  und Firefox importieren und exportieren.
- Lupe: Schrift, Einzüge und Formularfelder vergrößern und verkleinern (50–300 %) über den
  Knopf mit der Lupe, Strg+Plus/Strg+Minus/Strg+0 oder Strg+Mausrad. Die Stufe gilt für alle
  Tabs und bleibt nach einem Neustart erhalten.
- Notizen auf `about:notes`: ein einfacher Notizblock, gespeichert mit Knopf oder Strg+S und
  automatisch beim Verlassen der Seite, in `~/.config/anzeiger/notes.txt`.
- Suchen auf der Seite mit Strg+F: alle Treffer werden markiert, F3 bzw. Enter springt zum
  nächsten, Umschalt+F3 bzw. Umschalt+Enter zum vorigen.
- Cookies nur im Arbeitsspeicher, keine Drittanbieter-Cookies; abschalt- und löschbar.
- Sprachen: Deutsch, Englisch und Esperanto, wählbar auf `about:config` (Standard: Systemsprache).
  Alle Texte stehen in editierbaren Sprachdateien, siehe [Sprachen und Übersetzungen](#sprachen-und-übersetzungen).
- Eingebaute Seiten: Startseite `about:start` (Knopf ⌂), Änderungsprotokoll
  `about:changelog`, Lesezeichen `about:bookmarks`, Notizen `about:notes` und Einstellungen `about:config`,
  auf der Startseite verlinkt.
  Die Einstellungen liegen in `~/.config/anzeiger/settings.json`.

## Sprachen und Übersetzungen

Alle Texte der Oberfläche und der eingebauten Seiten stehen in Sprachdateien im
[TOML-Format](https://toml.io/) unter `anzeiger/lang/`: `de.toml` (Deutsch, vollständige
Referenz), `en.toml` (Englisch) und `eo.toml` (Esperanto). Der Code verwendet nur Schlüssel
wie `app.go`, die beim Anzeigen durch den Text der gewählten Sprache ersetzt werden.

```toml
[app]
go = "Los"
loading = "Lade {url} …"       # {url} ist ein Platzhalter
```

- Die Sprache wird auf `about:config` gewählt; „Automatisch“ nimmt die Systemsprache
  (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`) und sonst Englisch. Knöpfe und Menüs wechseln
  sofort, Seiten beim nächsten Laden.
- Eigene Änderungen gehören nach `~/.config/anzeiger/lang/`: Eine Datei gleichen Namens (z.B.
  `de.toml`) muss nur die geänderten Schlüssel enthalten und hat Vorrang vor der mitgelieferten.
  So bleiben die Änderungen auch nach einer Aktualisierung erhalten.
- Neue Sprache: `de.toml` oder `en.toml` z.B. als `fr.toml` in diesen Ordner kopieren,
  `[meta] name` setzen und übersetzen. Sie erscheint dann in der Auswahl auf `about:config`.
  Fehlende Texte werden auf Englisch, notfalls auf Deutsch angezeigt.
- Platzhalter in `{…}` müssen erhalten bleiben; Schlüssel mit `.one`/`.other` sind Einzahl
  und Mehrzahl. Fehler in einer Sprachdatei werden auf `about:config` gemeldet.
- Das Änderungsprotokoll (`about:changelog`) gibt es nur auf Deutsch.

## Versionen und Änderungsprotokoll

Die Versionsnummer (`anzeiger/__init__.py` und `pyproject.toml`) folgt dem Schema
Major.Minor.Patch. Jede Änderung wird in `anzeiger/changelog.html` beschrieben.

## Voraussetzungen

- Python ≥ 3.11 mit tkinter (Debian/Ubuntu: Paket `python3-tk`)
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
Einstellungen, Lesezeichen, Notizen und eigene Sprachdateien bleiben pro Benutzer in
`~/.config/anzeiger/`.

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
| Strg+Plus / Strg+Minus / Strg+Mausrad | Größer / kleiner darstellen (Lupe) |
| Strg+0                | Originalgröße (100 %) |
| Strg+S                | Notizen speichern (auf `about:notes`) |
| Strg+T / +            | Neuer Tab             |
| Strg+W / Mittelklick auf Tab | Tab schließen  |
| Strg+Umschalt+T       | Geschlossenen Tab wieder öffnen |
| Strg+Tab / Strg+Umschalt+Tab | Nächster / vorheriger Tab |
| Strg+1 … 8 / Strg+9   | Tab Nr. 1 … 8 / letzter Tab |
| Mittel- oder Strg+Klick auf Link | Link in neuem Tab öffnen |
| Enter in Textfeld     | Formular abschicken   |
| Strg+F                | Auf der Seite suchen  |
| F3 / Umschalt+F3      | Nächster / vorheriger Treffer |
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
| `anzeiger/pages.py`   | eingebaute Seiten (Start, Änderungsprotokoll, Lesezeichen, Notizen, Einstellungen, Fehler) |
| `anzeiger/forms.py`   | Formulardaten kodieren, GET-/POST-Anfrage bestimmen        |
| `anzeiger/bookmarks.py`| Lesezeichen-Datei im Netscape-Format (Chrome/Firefox)    |
| `anzeiger/notes.py`   | Notizen in `~/.config/anzeiger/notes.txt`                  |
| `anzeiger/settings.py`| Einstellungen in `~/.config/anzeiger/settings.json`, Zoomstufen |
| `anzeiger/i18n.py`    | Übersetzungen: Sprachdateien lesen, Texte zu Schlüsseln liefern |
| `anzeiger/lang/`      | Sprachdateien `de.toml`, `en.toml`, `eo.toml`              |
| `anzeiger/changelog.html` | Änderungsprotokoll                                     |
| `anzeiger/icons/`     | Programmsymbol (SVG, PNG 16–256 px)                        |
| `install.sh`, `uninstall.sh`, `data/anzeiger.desktop` | systemweite Installation, Menüeintrag |
| `anzeiger/images.py`  | sicheres Dekodieren/Skalieren erlaubter Bildformate        |
| `anzeiger/view.py`    | Anzeige im tkinter-Textfeld, Links, Formularfelder, Klappen |
| `anzeiger/app.py`     | Fenster, Adresszeile, Verlauf, Laden im Hintergrund        |
