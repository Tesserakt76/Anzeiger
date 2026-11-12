"""Eingebaute Seiten (about:…): Startseite, Änderungsprotokoll, Fehlerseite."""

from __future__ import annotations

import html
from importlib import resources

from . import __version__

HOME_URL = "about:start"
CHANGELOG_URL = "about:changelog"

START_PAGE = f"""<title>Anzeiger</title>
<h1>Anzeiger {__version__}</h1>
<p>Ein einfacher Browser, der nur Text darstellt.</p>
<ul>
  <li>Unterstützt werden nur <b>HTTP</b> und <b>HTTPS</b>.</li>
  <li>Kein CSS, kein JavaScript, keine Popups.</li>
  <li>Bilder werden nur geladen, wenn sie auf demselben Server (gleiche Domain, Subdomains zählen mit) wie die Seite liegen
      und im Format PNG, JPEG, GIF, BMP oder WebP vorliegen.</li>
</ul>
<p><a href="{CHANGELOG_URL}">Änderungsprotokoll</a> – was sich in welcher Version geändert hat.</p>
<h2>Tastenkürzel</h2>
<table border="1">
  <tr><th>Taste</th><th>Wirkung</th></tr>
  <tr><td>Strg+L</td><td>Adresszeile auswählen</td></tr>
  <tr><td>Alt+Links / Alt+Rechts</td><td>Zurück / Vor</td></tr>
  <tr><td>Alt+Pos1</td><td>Startseite</td></tr>
  <tr><td>F5</td><td>Neu laden</td></tr>
  <tr><td>Esc</td><td>Laden abbrechen</td></tr>
</table>
"""


def changelog_page() -> str:
    return resources.files(__package__).joinpath("changelog.html").read_text(encoding="utf-8")


INTERNAL_PAGES = {
    HOME_URL: lambda: START_PAGE,
    CHANGELOG_URL: changelog_page,
}


def is_internal(url: str) -> bool:
    return url.split("#", 1)[0].lower() in INTERNAL_PAGES


def internal_page(url: str) -> str:
    """HTML-Quelltext einer eingebauten Seite; KeyError bei unbekannter Adresse."""
    return INTERNAL_PAGES[url.split("#", 1)[0].lower()]()


def error_page(url: str, message: str) -> str:
    return (f"<title>Fehler</title><h1>Seite kann nicht geladen werden</h1>"
            f"<p><code>{html.escape(url)}</code></p><p>{html.escape(message)}</p>")
