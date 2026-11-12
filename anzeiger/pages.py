"""Eingebaute Seiten (about:…): Startseite, Änderungsprotokoll, Einstellungen, Fehlerseite."""

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from . import __version__
from .settings import Settings, default_path

HOME_URL = "about:start"
CHANGELOG_URL = "about:changelog"
CONFIG_URL = "about:config"


@dataclass
class PageContext:
    """Was dynamische eingebaute Seiten (about:config) anzeigen."""
    settings: Settings = field(default_factory=Settings)
    settings_path: Path = field(default_factory=default_path)
    cookies: dict[str, int] = field(default_factory=dict)   # Domain → Anzahl
    message: str = ""


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
<a href="{CONFIG_URL}">Einstellungen</a> – Cookies, Listen ein- oder ausgeklappt.</p>
<h2>Tastenkürzel</h2>
<table border="1">
  <tr><th>Taste</th><th>Wirkung</th></tr>
  <tr><td>Strg+L</td><td>Adresszeile auswählen</td></tr>
  <tr><td>Alt+Links / Alt+Rechts</td><td>Zurück / Vor</td></tr>
  <tr><td>Alt+Pos1</td><td>Startseite</td></tr>
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


INTERNAL_PAGES: dict[str, Callable[[PageContext | None], str]] = {
    HOME_URL: lambda _ctx: START_PAGE,
    CHANGELOG_URL: changelog_page,
    CONFIG_URL: config_page,
}


def is_internal(url: str) -> bool:
    return internal_url(url) in INTERNAL_PAGES


def internal_url(url: str) -> str:
    """Normalform einer eingebauten Adresse (ohne Fragment, kleingeschrieben)."""
    return url.split("#", 1)[0].lower()


def internal_page(url: str, ctx: PageContext | None = None) -> str:
    """HTML-Quelltext einer eingebauten Seite; KeyError bei unbekannter Adresse."""
    return INTERNAL_PAGES[internal_url(url)](ctx)


def error_page(url: str, message: str) -> str:
    return (f"<title>Fehler</title><h1>Seite kann nicht geladen werden</h1>"
            f"<p><code>{html.escape(url)}</code></p><p>{html.escape(message)}</p>")
