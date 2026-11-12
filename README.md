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

## Voraussetzungen

- Python ≥ 3.10 mit tkinter (Debian/Ubuntu: Paket `python3-tk`)
- Pillow

## Starten

```sh
python3 -m anzeiger                      # Startseite
python3 -m anzeiger https://example.org  # direkt eine Adresse öffnen
```

oder nach `pip install .` mit dem Befehl `anzeiger`.

## Tastenkürzel

| Taste                 | Wirkung               |
|-----------------------|-----------------------|
| Enter / „Los“         | Adresse laden         |
| Strg+L                | Adresszeile auswählen |
| Alt+Links / Alt+Rechts| Zurück / Vor          |
| F5                    | Neu laden             |
| Esc                   | Laden abbrechen       |

## Tests

```sh
python3 -m unittest discover -s tests
```

## Aufbau

| Modul                 | Aufgabe                                                    |
|-----------------------|------------------------------------------------------------|
| `anzeiger/net.py`     | HTTP-GET, nur http/https, Größenlimits, Zeichensatz        |
| `anzeiger/dom.py`     | fehlertoleranter HTML-Baum auf Basis von `html.parser`     |
| `anzeiger/layout.py`  | Baum → Darstellungsanweisungen (Listen, Tabellen …), ohne Tk |
| `anzeiger/images.py`  | sicheres Dekodieren/Skalieren erlaubter Bildformate        |
| `anzeiger/view.py`    | Anzeige im tkinter-Textfeld, Links, Mauszeiger-Hinweise    |
| `anzeiger/app.py`     | Fenster, Adresszeile, Verlauf, Laden im Hintergrund        |
