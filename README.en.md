# Anzeiger

[Deutsch](README.md) · **English** · [Esperanto](README.eo.md)

A simple web browser written in Python that shows web pages as plain text.
(*Anzeiger* is German for “indicator” or “gazette”.)

- **HTTP** and **HTTPS** only (also for redirects).
- A lock left of the address bar shows whether the page was loaded encrypted (HTTPS, dark lock)
  or unencrypted (HTTP, open red lock). Redirects from HTTPS to HTTP are not followed on their
  own; a warning with a link is shown instead.
- No CSS, no JavaScript, no popups.
- Headings `h1`–`h6`, paragraphs, emphasis, `pre`/`code`, quotes,
  ordered (`1.`, `a.`, `i.` …) and unordered (`*`) lists nested to any depth;
  items with sublists can be expanded and collapsed by clicking ▾/▸;
  definition lists, horizontal rules, tables (with `colspan`/`rowspan`) as a grid.
  Layout tables (tables that contain other tables) are shown row by row.
- Links are underlined; hovering shows the address in the status bar.
  Jumps to `#anchor` within the page.
- Images (`img`) are only loaded if they are on the **same server** (same domain,
  subdomains included, e.g. `www.a.de` and `cdn.a.de`) and are PNG, JPEG, GIF, BMP or WebP.
  Otherwise a placeholder `[Image: alt text]` appears, with the reason shown on hover.
  Tables drawn as a grid have no room for images; there, the placeholder of an image from the
  same server is a link to the image.
- Image addresses opened directly (e.g. a link to `photo.jpg`) are shown as a page of their own,
  scaled down to the window width, with format and original size below.
- Whole lists can be collapsed via the line “▾ List (n items)”.
- Whatever a page hides with `style="display:none"` or `visibility:hidden` appears collapsed
  behind “▸ Hidden: …” and can be expanded; can be turned off on `about:config`.
- Forms (text, password, checkboxes, radio buttons, drop-down lists, text areas) can be
  filled in and sent via GET or POST. No file upload.
- Tabs: several pages in one window, each with its own history. Middle-click or Ctrl+click
  opens links in the background; closed tabs can be reopened with Ctrl+Shift+T.
  Right-clicking a tab opens a menu.
- Right-clicking the page opens a context menu: copy selected text, open a link in a new tab,
  save an image or (if it is linked) open it in a new tab, view the page source (`view-source:`).
  In form text fields: copy and paste.
- Bookmarks: star ☆ or Ctrl+D, menu “Bookmarks”, management on `about:bookmarks`
  with folders nested to any depth (create, rename, move, remove).
  Stored in `~/.config/anzeiger/bookmarks.html` in the Netscape bookmark format that Chrome
  and Firefox import and export.
- Magnifier: enlarge and shrink text, indentation and form fields (50–300 %) with the
  magnifier button, Ctrl+Plus/Ctrl+Minus/Ctrl+0 or Ctrl+mouse wheel. The level applies to all
  tabs and is kept after a restart.
- Notes on `about:notes`: a simple notepad, saved with the button or Ctrl+S and
  automatically when leaving the page, in `~/.config/anzeiger/notes.txt`.
- Find on page with Ctrl+F: all matches are highlighted, F3 or Enter jumps to the next,
  Shift+F3 or Shift+Enter to the previous one.
- Cookies in memory only, no third-party cookies; can be turned off and deleted.
- Languages: German, English and Esperanto, selectable on `about:config` (default: system
  language). All texts are in editable language files, see
  [Languages and translations](#languages-and-translations).
- Built-in pages: start page `about:start` (button ⌂), change log `about:changelog`,
  bookmarks `about:bookmarks`, notes `about:notes` and settings `about:config`,
  all linked from the start page.
  The settings are stored in `~/.config/anzeiger/settings.json`.

## Languages and translations

All texts of the user interface and of the built-in pages are kept in language files in
[TOML format](https://toml.io/) under `anzeiger/lang/`: `de.toml` (German, the complete
reference), `en.toml` (English) and `eo.toml` (Esperanto). The code only uses keys such as
`app.go`, which are replaced by the text of the chosen language when displayed.

```toml
[app]
go = "Go"
loading = "Loading {url} …"    # {url} is a placeholder
```

- The language is chosen on `about:config`; “Automatic” uses the system language
  (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`) and falls back to English. Buttons and menus
  switch immediately, pages the next time they are loaded.
- Your own changes belong in `~/.config/anzeiger/lang/`: a file with the same name (e.g.
  `en.toml`) only needs the keys you change and takes precedence over the bundled one.
  This way your changes survive an update.
- New language: copy `en.toml` or `de.toml` into that folder as e.g. `fr.toml`, set
  `[meta] name` and translate. It then appears in the selection on `about:config`.
  Missing texts are shown in English, or in German as a last resort.
- Placeholders in `{…}` must be kept; keys ending in `.one`/`.other` are singular and plural.
  Errors in a language file are reported on `about:config`.
- The change log (`about:changelog`) is only available in German.

## Versions and change log

The version number (`anzeiger/__init__.py` and `pyproject.toml`) follows the scheme
Major.Minor.Patch. Every change is described (in German) in `anzeiger/changelog.html`.

## Requirements

- Python ≥ 3.11 with tkinter (Debian/Ubuntu: package `python3-tk`)
- Pillow, preferably with ImageTk (Debian/Ubuntu: `python3-pil.imagetk`) so that images appear faster

## Running

```sh
python3 -m anzeiger                      # start page
python3 -m anzeiger https://example.org  # open an address directly
```

or, after `pip install .` (e.g. in a virtual environment), with the command `anzeiger`.

## System-wide installation (all users)

```sh
sudo apt install python3-tk python3-pil python3-pil.imagetk   # if not installed yet
sudo ./install.sh
```

Afterwards “Anzeiger” with a newspaper icon appears in the application menu, and every user
can run `anzeiger [ADDRESS]`. It is installed to `/opt/anzeiger/` (program),
`/usr/local/bin/anzeiger` (launcher), `/usr/local/share/applications/` (menu entry) and
`/usr/local/share/icons/hicolor/` (icons); the locations can be changed with `APPDIR=…` and
`PREFIX=…`. Running it again updates the installation, `sudo ./uninstall.sh` removes everything.
Settings, bookmarks, notes and personal language files stay per user in
`~/.config/anzeiger/`. (The messages of the install scripts are in German.)

`sudo pip install .` is deliberately blocked on current Debian/Ubuntu releases
(PEP 668); `install.sh` needs neither pip nor internet access.

## Keyboard shortcuts

| Key                   | Effect                |
|-----------------------|-----------------------|
| Enter / “Go”          | Load address          |
| Ctrl+L                | Select the address bar |
| Alt+Left / Alt+Right  | Back / Forward        |
| Alt+Home / ⌂          | Start page            |
| Ctrl+D / ☆            | Add/remove bookmark   |
| Ctrl+Shift+O          | Manage bookmarks      |
| Ctrl+Plus / Ctrl+Minus / Ctrl+mouse wheel | Zoom in / out (magnifier) |
| Ctrl+0                | Actual size (100 %)   |
| Ctrl+S                | Save notes (on `about:notes`) |
| Ctrl+T / +            | New tab               |
| Ctrl+W / middle-click on tab | Close tab      |
| Ctrl+Shift+T          | Reopen closed tab     |
| Ctrl+Tab / Ctrl+Shift+Tab | Next / previous tab |
| Ctrl+1 … 8 / Ctrl+9   | Tab no. 1 … 8 / last tab |
| Middle-click or Ctrl+click on link | Open link in new tab |
| Right-click on the page | Context menu |
| Enter in text field   | Submit form           |
| Ctrl+F                | Find on page          |
| F3 / Shift+F3         | Next / previous match |
| F5                    | Reload                |
| Esc                   | Stop loading          |

## Tests

```sh
python3 -m unittest discover -s tests
```

## Structure

| Module                | Purpose                                                    |
|-----------------------|------------------------------------------------------------|
| `anzeiger/net.py`     | HTTP GET/POST, http/https only, cookies, size limits, character sets |
| `anzeiger/dom.py`     | error-tolerant HTML tree based on `html.parser`            |
| `anzeiger/layout.py`  | tree → drawing instructions (lists, tables …), without Tk  |
| `anzeiger/pages.py`   | built-in pages (start, change log, bookmarks, notes, settings, error) |
| `anzeiger/forms.py`   | encode form data, determine GET/POST request               |
| `anzeiger/bookmarks.py`| bookmark file in Netscape format (Chrome/Firefox)         |
| `anzeiger/notes.py`   | notes in `~/.config/anzeiger/notes.txt`                    |
| `anzeiger/settings.py`| settings in `~/.config/anzeiger/settings.json`, zoom levels |
| `anzeiger/i18n.py`    | translations: read language files, look up texts by key   |
| `anzeiger/lang/`      | language files `de.toml`, `en.toml`, `eo.toml`             |
| `anzeiger/changelog.html` | change log (German)                                    |
| `anzeiger/icons/`     | program icon (SVG, PNG 16–256 px)                          |
| `install.sh`, `uninstall.sh`, `data/anzeiger.desktop` | system-wide installation, menu entry |
| `anzeiger/images.py`  | safe decoding/scaling of allowed image formats             |
| `anzeiger/view.py`    | display in a tkinter text widget, links, form fields, folding |
| `anzeiger/app.py`     | window, address bar, history, loading in the background   |
