# Anzeiger

[Deutsch](README.md) · [English](README.en.md) · **Esperanto**

Simpla retumilo verkita en Python, kiu montras retpaĝojn kiel puran tekston.
(*Anzeiger* estas germana vorto por „indikilo“ aŭ „gazeto“.)

- Nur **HTTP** kaj **HTTPS** (ankaŭ ĉe alidirektoj).
- Neniu CSS, neniu JavaScript, neniuj ŝprucfenestroj.
- Titoloj `h1`–`h6`, alineoj, emfazoj, `pre`/`code`, citaĵoj,
  ordigitaj (`1.`, `a.`, `i.` …) kaj neordigitaj (`*`) listoj ajne ingitaj;
  eroj kun sublistoj faldeblas kaj malfaldeblas per klako sur ▾/▸;
  difinlistoj, horizontalaj linioj, tabeloj (kun `colspan`/`rowspan`) kiel krado.
  Aranĝaj tabeloj (tabeloj, kiuj enhavas aliajn tabelojn) estas montrataj vicon post vico.
- Ligiloj estas substrekitaj; ŝvebante super ili oni vidas la adreson en la statobreto.
  Saltoj al `#ankro` ene de la paĝo.
- Bildoj (`img`) estas ŝargataj nur, se ili troviĝas sur la **sama servilo** (sama domajno,
  subdomajnoj inkluzivitaj, ekz. `www.a.de` kaj `cdn.a.de`) kaj estas PNG, JPEG, GIF, BMP aŭ WebP.
  Alie aperas anstataŭaĵo `[Bildo: alt-teksto]`, kies kialon oni vidas ŝvebante super ĝi.
- Rekte malfermitaj bildadresoj (ekz. ligilo al `foto.jpg`) estas montrataj kiel aparta paĝo,
  malgrandigitaj al la larĝo de la fenestro, kun formato kaj originala grandeco sube.
- Tutaj listoj faldeblas per la linio „▾ Listo (n eroj)“.
- Formularoj (teksto, pasvorto, markobutonoj, radiobutonoj, elektolistoj, tekstareoj)
  plenigeblas kaj sendeblas per GET aŭ POST. Neniu alŝuto de dosieroj.
- Langetoj: pluraj paĝoj en unu fenestro, ĉiu kun propra historio. Meza klako aŭ Ctrl+klako
  malfermas ligilojn fone; fermitajn langetojn eblas remalfermi per Ctrl+Shift+T.
  Dekstra klako sur langeto malfermas menuon.
- Legosignoj: stelo ☆ aŭ Ctrl+D, menuo „Legosignoj“, administrado en `about:bookmarks`
  kun ajne ingitaj dosierujoj (krei, renomi, movi, forigi).
  Konservitaj en `~/.config/anzeiger/bookmarks.html` en la legosigna formato de Netscape, kiun
  Chrome kaj Firefox importas kaj eksportas.
- Lupeo: pligrandigi kaj malpligrandigi tekston, krommarĝenojn kaj formularajn kampojn
  (50–300 %) per la lupea butono, Ctrl+Plus/Ctrl+Minus/Ctrl+0 aŭ Ctrl+musrado. La grado validas
  por ĉiuj langetoj kaj restas post restarto.
- Notoj en `about:notes`: simpla notbloko, konservata per butono aŭ Ctrl+S kaj aŭtomate
  ĉe forlaso de la paĝo, en `~/.config/anzeiger/notes.txt`.
- Serĉi en la paĝo per Ctrl+F: ĉiuj trovoj estas markitaj, F3 aŭ Enigklavo saltas al la
  sekva, Shift+F3 aŭ Shift+Enigklavo al la antaŭa.
- Kuketoj nur en la memoro, neniuj kuketoj de eksteraj liverantoj; malŝalteblaj kaj forigeblaj.
- Lingvoj: germana, angla kaj Esperanto, elekteblaj en `about:config` (defaŭlte: la sistema
  lingvo). Ĉiuj tekstoj troviĝas en redakteblaj lingvodosieroj, vidu
  [Lingvoj kaj tradukoj](#lingvoj-kaj-tradukoj).
- Enkonstruitaj paĝoj: komenca paĝo `about:start` (butono ⌂), ŝanĝoprotokolo
  `about:changelog`, legosignoj `about:bookmarks`, notoj `about:notes` kaj agordoj
  `about:config`, ĉiuj ligitaj de la komenca paĝo.
  La agordoj estas konservataj en `~/.config/anzeiger/settings.json`.

## Lingvoj kaj tradukoj

Ĉiuj tekstoj de la fasado kaj de la enkonstruitaj paĝoj troviĝas en lingvodosieroj en
[TOML-formato](https://toml.io/) sub `anzeiger/lang/`: `de.toml` (germana, la kompleta
referenco), `en.toml` (angla) kaj `eo.toml` (Esperanto). La kodo uzas nur ŝlosilojn kiel
`app.go`, kiujn la teksto de la elektita lingvo anstataŭigas dum la montrado.

```toml
[app]
go = "Iru"
loading = "Ŝargado de {url} …"  # {url} estas lokokupilo
```

- La lingvo estas elektata en `about:config`; „Aŭtomata“ uzas la sisteman lingvon
  (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`), alie la anglan. Butonoj kaj menuoj ŝanĝiĝas
  tuj, paĝoj ĉe la sekva ŝargado.
- Propraj ŝanĝoj apartenas en `~/.config/anzeiger/lang/`: samnoma dosiero (ekz. `eo.toml`)
  bezonas nur la ŝanĝitajn ŝlosilojn kaj havas prioritaton antaŭ la liverita.
  Tiel la ŝanĝoj restas ankaŭ post ĝisdatigo.
- Nova lingvo: kopiu `en.toml` aŭ `de.toml` en tiun dosierujon ekz. kiel `fr.toml`,
  agordu `[meta] name` kaj traduku. Ĝi tiam aperas en la elekto en `about:config`.
  Mankantaj tekstoj aperas angle, laŭbezone germane.
- Lokokupiloj en `{…}` devas resti; ŝlosiloj kun `.one`/`.other` estas ununombro kaj
  multenombro. Eraroj en lingvodosiero estas raportataj en `about:config`.
- La ŝanĝoprotokolo (`about:changelog`) ekzistas nur en la germana.

## Versioj kaj ŝanĝoprotokolo

La versinumero (`anzeiger/__init__.py` kaj `pyproject.toml`) sekvas la skemon
Major.Minor.Patch. Ĉiu ŝanĝo estas priskribita (germanlingve) en `anzeiger/changelog.html`.

## Antaŭkondiĉoj

- Python ≥ 3.11 kun tkinter (Debian/Ubuntu: pako `python3-tk`)
- Pillow, prefere kun ImageTk (Debian/Ubuntu: `python3-pil.imagetk`), por ke bildoj aperu pli rapide

## Lanĉo

```sh
python3 -m anzeiger                      # komenca paĝo
python3 -m anzeiger https://example.org  # rekte malfermi adreson
```

aŭ post `pip install .` (ekz. en virtuala medio) per la komando `anzeiger`.

## Instali por la tuta sistemo (ĉiuj uzantoj)

```sh
sudo apt install python3-tk python3-pil python3-pil.imagetk   # se ankoraŭ ne instalitaj
sudo ./install.sh
```

Poste „Anzeiger“ kun gazeta piktogramo aperas en la aplikaĵa menuo, kaj ĉiu uzanto povas
voki `anzeiger [ADRESO]`. La instalado iras al `/opt/anzeiger/` (programo),
`/usr/local/bin/anzeiger` (lanĉokomando), `/usr/local/share/applications/` (menuero) kaj
`/usr/local/share/icons/hicolor/` (piktogramoj); la lokojn eblas ŝanĝi per `APPDIR=…` kaj
`PREFIX=…`. Denova lanĉo ĝisdatigas, `sudo ./uninstall.sh` forigas ĉion.
Agordoj, legosignoj, notoj kaj propraj lingvodosieroj restas por ĉiu uzanto en
`~/.config/anzeiger/`. (La mesaĝoj de la instalaj skriptoj estas germanlingvaj.)

`sudo pip install .` estas intence blokita en aktualaj versioj de Debian/Ubuntu
(PEP 668); `install.sh` bezonas nek pip nek interreton.

## Klavkombinoj

| Klavo                 | Efiko                 |
|-----------------------|-----------------------|
| Enigklavo / „Iru“     | Ŝargi adreson         |
| Ctrl+L                | Elekti la adresbreton |
| Alt+← / Alt+→         | Malantaŭen / Antaŭen  |
| Alt+Home / ⌂          | Komenca paĝo          |
| Ctrl+D / ☆            | Aldoni/forigi legosignon |
| Ctrl+Shift+O          | Administri legosignojn |
| Ctrl+Plus / Ctrl+Minus / Ctrl+musrado | Pligrandigi / malpligrandigi (lupeo) |
| Ctrl+0                | Originala grandeco (100 %) |
| Ctrl+S                | Konservi notojn (en `about:notes`) |
| Ctrl+T / +            | Nova langeto          |
| Ctrl+W / meza klako sur langeto | Fermi langeton |
| Ctrl+Shift+T          | Remalfermi fermitan langeton |
| Ctrl+Tab / Ctrl+Shift+Tab | Sekva / antaŭa langeto |
| Ctrl+1 … 8 / Ctrl+9   | Langeto n-ro 1 … 8 / lasta langeto |
| Meza klako aŭ Ctrl+klako sur ligilo | Malfermi ligilon en nova langeto |
| Enigklavo en tekstkampo | Sendi formularon    |
| Ctrl+F                | Serĉi en la paĝo      |
| F3 / Shift+F3         | Sekva / antaŭa trovo  |
| F5                    | Reŝargi               |
| Esc                   | Ĉesigi ŝargadon       |

## Testoj

```sh
python3 -m unittest discover -s tests
```

## Strukturo

| Modulo                | Tasko                                                      |
|-----------------------|------------------------------------------------------------|
| `anzeiger/net.py`     | HTTP-GET/POST, nur http/https, kuketoj, grandolimoj, signaro |
| `anzeiger/dom.py`     | erartolerema HTML-arbo surbaze de `html.parser`            |
| `anzeiger/layout.py`  | arbo → montraj instrukcioj (listoj, tabeloj …), sen Tk     |
| `anzeiger/pages.py`   | enkonstruitaj paĝoj (komenco, ŝanĝoprotokolo, legosignoj, notoj, agordoj, eraro) |
| `anzeiger/forms.py`   | kodi formularajn datumojn, difini GET-/POST-peton          |
| `anzeiger/bookmarks.py`| legosigna dosiero en Netscape-formato (Chrome/Firefox)    |
| `anzeiger/notes.py`   | notoj en `~/.config/anzeiger/notes.txt`                    |
| `anzeiger/settings.py`| agordoj en `~/.config/anzeiger/settings.json`, lupeaj gradoj |
| `anzeiger/i18n.py`    | tradukoj: legi lingvodosierojn, liveri tekstojn laŭ ŝlosilo |
| `anzeiger/lang/`      | lingvodosieroj `de.toml`, `en.toml`, `eo.toml`             |
| `anzeiger/changelog.html` | ŝanĝoprotokolo (germanlingva)                          |
| `anzeiger/icons/`     | programa piktogramo (SVG, PNG 16–256 px)                   |
| `install.sh`, `uninstall.sh`, `data/anzeiger.desktop` | sistemvasta instalado, menuero |
| `anzeiger/images.py`  | sekura malkodado/skalado de permesitaj bildformatoj        |
| `anzeiger/view.py`    | montrado en tkinter-tekstkampo, ligiloj, formularaj kampoj, faldado |
| `anzeiger/app.py`     | fenestro, adresbreto, historio, fona ŝargado               |
