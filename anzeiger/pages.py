"""Eingebaute Seiten (about:…): Startseite, Änderungsprotokoll, Einstellungen, Lesezeichen,
Notizen, Fehlerseite und die Seite für direkt aufgerufene Bilder."""

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import __version__
from . import bookmarks as bm
from . import notes as nt
from .settings import Settings, default_path

HOME_URL = "about:start"
CHANGELOG_URL = "about:changelog"
CONFIG_URL = "about:config"
BOOKMARKS_URL = "about:bookmarks"
NOTES_URL = "about:notes"


@dataclass
class PageContext:
    """Was dynamische eingebaute Seiten (about:config) anzeigen."""
    settings: Settings = field(default_factory=Settings)
    settings_path: Path = field(default_factory=default_path)
    cookies: dict[str, int] = field(default_factory=dict)   # Domain → Anzahl
    message: str = ""
    bookmarks: bm.Folder = field(default_factory=lambda: bm.Folder("Lesezeichen"))
    bookmarks_path: Path = field(default_factory=bm.default_path)
    bookmarks_edit: bool = False
    notes: str = ""
    notes_path: Path = field(default_factory=nt.default_path)


START_PAGE = f"""<title>Anzeiger</title>
<h1>Anzeiger {__version__}</h1>
<p>Ein einfacher Browser, der nur Text darstellt.</p>
<ul>
  <li>Unterstützt werden nur <b>HTTP</b> und <b>HTTPS</b>.</li>
  <li>Kein CSS, kein JavaScript, keine Popups.</li>
  <li>Bilder werden nur geladen, wenn sie auf demselben Server (gleiche Domain, Subdomains zählen mit) wie die Seite liegen
      und im Format PNG, JPEG, GIF, BMP oder WebP vorliegen.</li>
</ul>
<p><a href="{CHANGELOG_URL}">Änderungsprotokoll</a> – was sich in welcher Version geändert hat.<br>
<a href="{BOOKMARKS_URL}">Lesezeichen</a> – gespeicherte Seiten in Ordnern, kompatibel zu Chrome und Firefox.<br>
<a href="{NOTES_URL}">Notizen</a> – ein einfacher Notizblock, der dauerhaft gespeichert wird.<br>
<a href="{CONFIG_URL}">Einstellungen</a> – Cookies, Listen ein- oder ausgeklappt.</p>
<h2>Tastenkürzel</h2>
<table border="1">
  <tr><th>Taste</th><th>Wirkung</th></tr>
  <tr><td>Strg+L</td><td>Adresszeile auswählen</td></tr>
  <tr><td>Alt+Links / Alt+Rechts</td><td>Zurück / Vor</td></tr>
  <tr><td>Alt+Pos1</td><td>Startseite</td></tr>
  <tr><td>Strg+D</td><td>Lesezeichen für die aktuelle Seite setzen oder entfernen</td></tr>
  <tr><td>Strg+Umschalt+O</td><td>Lesezeichen verwalten</td></tr>
  <tr><td>Strg+Plus / Strg+Minus, Strg+Mausrad</td><td>Größer / kleiner darstellen (Lupe)</td></tr>
  <tr><td>Strg+0</td><td>Originalgröße (100 %)</td></tr>
  <tr><td>Strg+S</td><td>Notizen speichern (auf <code>about:notes</code>)</td></tr>
  <tr><td>Strg+T / +</td><td>Neuer Tab</td></tr>
  <tr><td>Strg+W, Mittelklick auf den Tab</td><td>Tab schließen</td></tr>
  <tr><td>Strg+Umschalt+T</td><td>Geschlossenen Tab wieder öffnen</td></tr>
  <tr><td>Strg+Tab / Strg+Umschalt+Tab</td><td>Nächster / vorheriger Tab (auch Strg+Bild↓ / Strg+Bild↑)</td></tr>
  <tr><td>Strg+1 … Strg+8, Strg+9</td><td>Tab Nummer 1 bis 8, letzter Tab</td></tr>
  <tr><td>Mittelklick oder Strg+Klick auf einen Link</td><td>Link in neuem Tab im Hintergrund öffnen</td></tr>
  <tr><td>Enter in einem Textfeld</td><td>Formular abschicken</td></tr>
  <tr><td>F5</td><td>Neu laden</td></tr>
  <tr><td>Esc</td><td>Laden abbrechen</td></tr>
</table>
"""


def changelog_page(_ctx: PageContext | None = None) -> str:
    return resources.files(__package__).joinpath("changelog.html").read_text(encoding="utf-8")


def _checked(value: bool) -> str:
    return " checked" if value else ""


def config_page(ctx: PageContext | None = None) -> str:
    ctx = ctx or PageContext()
    s = ctx.settings
    message = f"<p><b>{html.escape(ctx.message)}</b></p>" if ctx.message else ""
    total = sum(ctx.cookies.values())
    if not s.cookies_enabled:
        cookie_list = "<p>Cookies sind ausgeschaltet.</p>"
    elif total:
        items = "".join(f"<li>{html.escape(domain)}: {count}</li>" for domain, count in ctx.cookies.items())
        cookie_list = (f"<p>{total} Cookie{'s' if total != 1 else ''} von {len(ctx.cookies)} "
                       f"Domain{'s' if len(ctx.cookies) != 1 else ''}:</p><ul>{items}</ul>")
    else:
        cookie_list = "<p>Zurzeit sind keine Cookies gespeichert.</p>"
    return f"""<title>Einstellungen</title>
<h1>Einstellungen</h1>
{message}
<form method="post" action="{CONFIG_URL}">
<input type="hidden" name="action" value="save">
<h2>Cookies</h2>
<p><input type="checkbox" name="cookies" value="on"{_checked(s.cookies_enabled)}> Cookies zulassen</p>
<p>Cookies werden nur im Arbeitsspeicher gehalten und beim Beenden des Anzeigers gelöscht.
Cookies von Drittanbietern (anderen Domains als der besuchten Seite) werden nie angenommen.
Beim Ausschalten werden alle gespeicherten Cookies sofort gelöscht.</p>
<h2>Listen</h2>
<p><input type="checkbox" name="lists" value="on"{_checked(s.lists_collapsed)}> Ganze Listen eingeklappt anzeigen</p>
<p><input type="checkbox" name="sublists" value="on"{_checked(s.sublists_collapsed)}> Unterlisten eingeklappt anzeigen</p>
<p>Gilt für Seiten, die nach dem Speichern geladen werden. Ein Klick auf ▸ bzw. ▾ klappt
eine Liste jederzeit auf oder zu.</p>
<p><input type="submit" value="Speichern"></p>
</form>
<h2>Gespeicherte Cookies</h2>
{cookie_list}
<form method="post" action="{CONFIG_URL}">
<input type="hidden" name="action" value="clear-cookies">
<p><input type="submit" value="Alle Cookies löschen"></p>
</form>
<hr>
<p>Die Einstellungen werden dauerhaft gespeichert in <code>{html.escape(str(ctx.settings_path))}</code>.</p>
<p><a href="{HOME_URL}">Zurück zur Startseite</a></p>
"""


def _folder_select(choices: list[tuple[tuple[int, ...], str]], form: str, selected: tuple[int, ...],
                   skip: tuple[int, ...] | None = None) -> str:
    """Auswahlliste der Ordner; `skip` lässt einen Ordner samt Unterordnern weg."""
    options = []
    for where, name in choices:
        if skip is not None and where[:len(skip)] == skip:
            continue
        mark = " selected" if where == selected else ""
        options.append(f'<option value="{bm.format_path(where)}"{mark}>{html.escape(name)}</option>')
    return f'<select name="dest" form="{form}">{"".join(options)}</select>'


def _edit_fields(node: bm.Bookmark | bm.Folder, where: tuple[int, ...],
                 choices: list[tuple[tuple[int, ...], str]], forms: list[str]) -> str:
    """Felder zum Umbenennen, Verschieben und Entfernen; das Formular steht am Seitenende."""
    form = f"b{bm.format_path(where)}"
    forms.append(f'<form id="{form}" method="post" action="{BOOKMARKS_URL}">'
                 f'<input type="hidden" name="path" value="{bm.format_path(where)}">'
                 f'<input type="hidden" name="key" value="{html.escape(bm.identity(node), quote=True)}"></form>')
    skip = where if isinstance(node, bm.Folder) else None
    return (f'<br><input type="text" name="title" size="40" form="{form}" '
            f'value="{html.escape(node.title, quote=True)}"> '
            f'<input type="submit" name="action" value="Umbenennen" form="{form}"> '
            f'<input type="submit" name="action" value="Entfernen" form="{form}"><br>'
            f'{_folder_select(choices, form, where[:-1], skip)} '
            f'<input type="submit" name="action" value="Verschieben" form="{form}">')


def _bookmark_items(folder: bm.Folder, path: tuple[int, ...], edit: bool, forms: list[str],
                    choices: list[tuple[tuple[int, ...], str]]) -> str:
    items = []
    for i, child in enumerate(folder.children):
        where = path + (i,)
        if isinstance(child, bm.Folder):
            fields = _edit_fields(child, where, choices, forms) if edit else ""
            inner = _bookmark_items(child, where, edit, forms, choices)
            title = html.escape(child.title or "(Ordner ohne Namen)")
            body = f"<ul>{inner}</ul>" if inner else " <small>(leer)</small>"
            items.append(f"<li><b>{title}</b>{fields}{body}</li>")
        elif isinstance(child, bm.Bookmark):
            title = html.escape(child.title or child.url)
            link = f'<a href="{html.escape(child.url, quote=True)}">{title}</a>'
            fields = _edit_fields(child, where, choices, forms) if edit else ""
            items.append(f"<li>{link}{fields}</li>")
    return "".join(items)


def bookmarks_page(ctx: PageContext | None = None) -> str:
    ctx = ctx or PageContext()
    message = f"<p><b>{html.escape(ctx.message)}</b></p>" if ctx.message else ""
    forms: list[str] = []
    choices = bm.folders(ctx.bookmarks)
    items = _bookmark_items(ctx.bookmarks, (), ctx.bookmarks_edit, forms, choices)
    count = ctx.bookmarks.count()
    if items:
        folder_count = len(choices) - 1
        in_folders = f" in {folder_count} Ordner{'n' if folder_count != 1 else ''}" if folder_count else ""
        listing = f"<p>{count} Lesezeichen{in_folders}.</p><ul>{items}</ul>"
    else:
        listing = ("<p>Noch keine Lesezeichen. Mit dem Stern ☆ neben der Adresszeile oder "
                   "<b>Strg+D</b> wird die aktuelle Seite gespeichert.</p>")
    action, label = ("done", "Fertig") if ctx.bookmarks_edit else ("edit", "Bearbeiten")
    toggle = (f'<form method="post" action="{BOOKMARKS_URL}"><input type="hidden" name="action" '
              f'value="{action}"><input type="submit" value="{label}"></form>')
    new_folder = ""
    if ctx.bookmarks_edit:
        new_folder = (f'<h2>Neuer Ordner</h2>'
                      f'<form id="new-folder" method="post" action="{BOOKMARKS_URL}">'
                      f'<p>Name: <input type="text" name="title" size="30"> in '
                      f'{_folder_select(choices, "new-folder", ())} '
                      f'<input type="submit" name="action" value="Ordner anlegen"></p></form>'
                      f'<p><small>Mit „Verschieben“ wandert ein Lesezeichen oder Ordner samt Inhalt '
                      f'ans Ende des gewählten Ordners. „Entfernen“ bei einem Ordner löscht auch alles, '
                      f'was darin liegt.</small></p><h2>Alle Lesezeichen</h2>')
    return f"""<title>Lesezeichen</title>
<h1>Lesezeichen</h1>
{message}
{toggle}
{new_folder}
{listing}
{"".join(forms)}
<hr>
<h2>Datei</h2>
<p>Die Lesezeichen liegen in <code>{html.escape(str(ctx.bookmarks_path))}</code>.</p>
<p>Die Datei hat das Lesezeichen-Format, das Chrome und Firefox beim Exportieren
schreiben und beim Importieren lesen („Lesezeichen aus HTML-Datei importieren“).
Umgekehrt kann eine aus Chrome oder Firefox exportierte Datei einfach an diese Stelle
kopiert werden. Ordner, Beschreibungen und Symbole bleiben dabei erhalten.</p>
<p><a href="{HOME_URL}">Zurück zur Startseite</a></p>
"""


def notes_page(ctx: PageContext | None = None) -> str:
    ctx = ctx or PageContext()
    message = f"<p><b>{html.escape(ctx.message)}</b></p>" if ctx.message else ""
    # Der Zeilenumbruch nach <textarea> wird beim Einlesen entfernt; so bleibt eine
    # Leerzeile am Anfang der Notizen erhalten.
    return f"""<title>Notizen</title>
<h1>Notizen</h1>
{message}
<form method="post" action="{NOTES_URL}">
<textarea name="text" cols="72" rows="20">
{html.escape(ctx.notes, quote=False)}</textarea>
<p><input type="submit" name="action" value="Speichern"> <input type="reset" value="Änderungen verwerfen"></p>
</form>
<p>Speichern mit dem Knopf oder <b>Strg+S</b>. Ungespeicherte Änderungen werden außerdem
automatisch gesichert, sobald die Seite verlassen, der Tab geschlossen oder der Anzeiger
beendet wird. „Änderungen verwerfen“ stellt den zuletzt gespeicherten Stand wieder her.</p>
<p>Die Notizen liegen als reiner Text in <code>{html.escape(str(ctx.notes_path))}</code>.</p>
<p><a href="{HOME_URL}">Zurück zur Startseite</a></p>
"""


INTERNAL_PAGES: dict[str, Callable[[PageContext | None], str]] = {
    HOME_URL: lambda _ctx: START_PAGE,
    CHANGELOG_URL: changelog_page,
    CONFIG_URL: config_page,
    BOOKMARKS_URL: bookmarks_page,
    NOTES_URL: notes_page,
}


def is_internal(url: str) -> bool:
    return internal_url(url) in INTERNAL_PAGES


def internal_url(url: str) -> str:
    """Normalform einer eingebauten Adresse (ohne Fragment, kleingeschrieben)."""
    return url.split("#", 1)[0].lower()


def internal_page(url: str, ctx: PageContext | None = None) -> str:
    """HTML-Quelltext einer eingebauten Seite; KeyError bei unbekannter Adresse."""
    return INTERNAL_PAGES[internal_url(url)](ctx)


def image_page(url: str, image_format: str, size: tuple[int, int], shown: tuple[int, int]) -> str:
    """Seite für eine direkt aufgerufene Bildadresse: Bild, darunter Format und Größe."""
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or urlsplit(url).hostname or url
    info = f"{image_format}, {size[0]}×{size[1]} Pixel"
    if shown != size:
        info += f" – verkleinert auf {shown[0]}×{shown[1]}"
    return (f"<title>{html.escape(name)} ({size[0]}×{size[1]})</title>"
            f'<p><img src="{html.escape(url)}" alt="{html.escape(name)}"></p>'
            f"<p><small>{html.escape(info)}</small></p>")


def error_page(url: str, message: str) -> str:
    return (f"<title>Fehler</title><h1>Seite kann nicht geladen werden</h1>"
            f"<p><code>{html.escape(url)}</code></p><p>{html.escape(message)}</p>")
