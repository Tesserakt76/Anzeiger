"""Eingebaute Seiten (about:…): Startseite, Änderungsprotokoll, Einstellungen, Lesezeichen,
Fehlerseite und die Seite für direkt aufgerufene Bilder."""

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import __version__
from . import bookmarks as bm
from .settings import Settings, default_path

HOME_URL = "about:start"
CHANGELOG_URL = "about:changelog"
CONFIG_URL = "about:config"
BOOKMARKS_URL = "about:bookmarks"


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
<a href="{BOOKMARKS_URL}">Lesezeichen</a> – gespeicherte Seiten, kompatibel zu Chrome und Firefox.<br>
<a href="{CONFIG_URL}">Einstellungen</a> – Cookies, Listen ein- oder ausgeklappt.</p>
<h2>Tastenkürzel</h2>
<table border="1">
  <tr><th>Taste</th><th>Wirkung</th></tr>
  <tr><td>Strg+L</td><td>Adresszeile auswählen</td></tr>
  <tr><td>Alt+Links / Alt+Rechts</td><td>Zurück / Vor</td></tr>
  <tr><td>Alt+Pos1</td><td>Startseite</td></tr>
  <tr><td>Strg+D</td><td>Lesezeichen für die aktuelle Seite setzen oder entfernen</td></tr>
  <tr><td>Strg+Umschalt+O</td><td>Lesezeichen verwalten</td></tr>
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


def _bookmark_items(folder: bm.Folder, path: tuple[int, ...], edit: bool, forms: list[str]) -> str:
    items = []
    for i, child in enumerate(folder.children):
        where = path + (i,)
        if isinstance(child, bm.Folder):
            inner = _bookmark_items(child, where, edit, forms)
            title = html.escape(child.title or "(Ordner ohne Namen)")
            body = f"<ul>{inner}</ul>" if inner else " <small>(leer)</small>"
            items.append(f"<li><b>{title}</b>{body}</li>")
        elif isinstance(child, bm.Bookmark):
            title = html.escape(child.title or child.url)
            url = html.escape(child.url, quote=True)
            link = f'<a href="{url}">{title}</a>'
            if not edit:
                items.append(f"<li>{link}</li>")
                continue
            # Die Felder stehen in der Liste, das zugehörige Formular am Seitenende.
            form = f"b{bm.format_path(where)}"
            forms.append(f'<form id="{form}" method="post" action="{BOOKMARKS_URL}">'
                         f'<input type="hidden" name="path" value="{bm.format_path(where)}">'
                         f'<input type="hidden" name="url" value="{url}"></form>')
            items.append(
                f'<li>{link}<br><input type="text" name="title" size="40" form="{form}" '
                f'value="{html.escape(child.title, quote=True)}"> '
                f'<input type="submit" name="action" value="Umbenennen" form="{form}"> '
                f'<input type="submit" name="action" value="Entfernen" form="{form}"></li>')
    return "".join(items)


def bookmarks_page(ctx: PageContext | None = None) -> str:
    ctx = ctx or PageContext()
    message = f"<p><b>{html.escape(ctx.message)}</b></p>" if ctx.message else ""
    forms: list[str] = []
    items = _bookmark_items(ctx.bookmarks, (), ctx.bookmarks_edit, forms)
    count = ctx.bookmarks.count()
    if items:
        listing = f"<p>{count} Lesezeichen.</p><ul>{items}</ul>"
    else:
        listing = ("<p>Noch keine Lesezeichen. Mit dem Stern ☆ neben der Adresszeile oder "
                   "<b>Strg+D</b> wird die aktuelle Seite gespeichert.</p>")
    action, label = ("done", "Fertig") if ctx.bookmarks_edit else ("edit", "Bearbeiten")
    toggle = (f'<form method="post" action="{BOOKMARKS_URL}"><input type="hidden" name="action" '
              f'value="{action}"><input type="submit" value="{label}"></form>') if items else ""
    return f"""<title>Lesezeichen</title>
<h1>Lesezeichen</h1>
{message}
{toggle}
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


INTERNAL_PAGES: dict[str, Callable[[PageContext | None], str]] = {
    HOME_URL: lambda _ctx: START_PAGE,
    CHANGELOG_URL: changelog_page,
    CONFIG_URL: config_page,
    BOOKMARKS_URL: bookmarks_page,
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
