"""Eingebaute Seiten (about:…): Startseite, Änderungsprotokoll, Einstellungen, Lesezeichen,
Notizen, Fehlerseite, Warnung vor unverschlüsselter Weiterleitung und die Seite für direkt
aufgerufene Bilder."""

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import __version__
from . import bookmarks as bm
from . import i18n
from . import notes as nt
from .i18n import t, tl, tn
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
    bookmarks: bm.Folder = field(default_factory=lambda: bm.Folder(""))
    bookmarks_path: Path = field(default_factory=bm.default_path)
    bookmarks_edit: bool = False
    notes: str = ""
    notes_path: Path = field(default_factory=nt.default_path)


# Zeilen der Tastenkürzel-Tabelle auf der Startseite ([page.start.rows] der Sprachdatei)
SHORTCUT_ROWS = ("address", "back_forward", "home", "bookmark", "manage", "zoom", "zoom_reset", "notes",
                 "new_tab", "close_tab", "reopen_tab", "cycle_tabs", "select_tab", "link_new_tab", "context_menu",
                 "submit", "find", "reload", "stop")


def start_page(_ctx: PageContext | None = None) -> str:
    rows = "\n".join(f"  <tr><td>{key}</td><td>{effect}</td></tr>"
                     for key, effect in ((tl(f"page.start.rows.{name}") + ["", ""])[:2] for name in SHORTCUT_ROWS))
    return f"""<title>Anzeiger</title>
<h1>Anzeiger {__version__}</h1>
<p>{t("page.start.tagline")}</p>
<ul>
  <li>{t("page.start.protocols")}</li>
  <li>{t("page.start.no_css")}</li>
  <li>{t("page.start.images")}</li>
</ul>
<p><a href="{CHANGELOG_URL}">{t("page.start.changelog")}</a> – {t("page.start.changelog_about")}<br>
<a href="{BOOKMARKS_URL}">{t("page.start.bookmarks")}</a> – {t("page.start.bookmarks_about")}<br>
<a href="{NOTES_URL}">{t("page.start.notes")}</a> – {t("page.start.notes_about")}<br>
<a href="{CONFIG_URL}">{t("page.start.config")}</a> – {t("page.start.config_about")}</p>
<h2>{t("page.start.shortcuts")}</h2>
<table border="1">
  <tr><th>{t("page.start.key")}</th><th>{t("page.start.effect")}</th></tr>
{rows}
</table>
"""


def changelog_page(_ctx: PageContext | None = None) -> str:
    """Das Änderungsprotokoll gibt es nur auf Deutsch; andere Sprachen setzen einen Hinweis darüber."""
    source = resources.files(__package__).joinpath("changelog.html").read_text(encoding="utf-8")
    note = t("page.changelog.note")
    return source.replace("</h1>", "</h1>\n" + note, 1) if note else source


def _checked(value: bool) -> str:
    return " checked" if value else ""


def _language_select(current: str) -> str:
    languages = i18n.available()
    system = languages.get(i18n.system_language(), i18n.system_language())
    options = [("", t("page.config.language_auto", name=html.escape(system)))]
    options += [(code, html.escape(name)) for code, name in languages.items()]
    if current and current not in languages:
        options.append((current, html.escape(current)))
    return "".join(f'<option value="{html.escape(code, quote=True)}"{" selected" if code == current else ""}>'
                   f"{label}</option>" for code, label in options)


def config_page(ctx: PageContext | None = None) -> str:
    ctx = ctx or PageContext()
    s = ctx.settings
    message = f"<p><b>{html.escape(ctx.message)}</b></p>" if ctx.message else ""
    total = sum(ctx.cookies.values())
    if not s.cookies_enabled:
        cookie_list = f"<p>{t('page.config.cookies_off')}</p>"
    elif total:
        items = "".join(f"<li>{html.escape(domain)}: {count}</li>" for domain, count in ctx.cookies.items())
        summary = t("page.config.cookie_summary", cookies=tn("page.config.cookie_count", total),
                    domains=tn("page.config.domain_count", len(ctx.cookies)))
        cookie_list = f"<p>{summary}</p><ul>{items}</ul>"
    else:
        cookie_list = f"<p>{t('page.config.no_cookies')}</p>"
    language_errors = "".join(f"<p><b>{t('page.config.language_error', error=html.escape(error))}</b></p>"
                              for error in i18n.errors)
    language_help = t("page.config.language_help", builtin=html.escape(str(i18n.builtin_dir())),
                      user=html.escape(str(i18n.user_dir())))
    return f"""<title>{t("page.config.title")}</title>
<h1>{t("page.config.title")}</h1>
{message}
<form method="post" action="{CONFIG_URL}">
<input type="hidden" name="action" value="save">
<h2>{t("page.config.language")}</h2>
<p><select name="language">{_language_select(s.language)}</select></p>
<p>{language_help}</p>
{language_errors}
<h2>{t("page.config.cookies")}</h2>
<p><input type="checkbox" name="cookies" value="on"{_checked(s.cookies_enabled)}> {t("page.config.allow_cookies")}</p>
<p>{t("page.config.cookies_help")}</p>
<h2>{t("page.config.lists")}</h2>
<p><input type="checkbox" name="lists" value="on"{_checked(s.lists_collapsed)}> {t("page.config.lists_collapsed")}</p>
<p><input type="checkbox" name="sublists" value="on"{_checked(s.sublists_collapsed)}> {t("page.config.sublists_collapsed")}</p>
<p>{t("page.config.lists_help")}</p>
<h2>{t("page.config.hidden")}</h2>
<p><input type="checkbox" name="hidden" value="on"{_checked(s.hidden_collapsed)}> {t("page.config.hidden_collapsed")}</p>
<p>{t("page.config.hidden_help")}</p>
<p><input type="submit" value="{html.escape(t("page.config.save"), quote=True)}"></p>
</form>
<h2>{t("page.config.stored_cookies")}</h2>
{cookie_list}
<form method="post" action="{CONFIG_URL}">
<input type="hidden" name="action" value="clear-cookies">
<p><input type="submit" value="{html.escape(t("page.config.clear_cookies"), quote=True)}"></p>
</form>
<hr>
<p>{t("page.config.stored_in", path=html.escape(str(ctx.settings_path)))}</p>
<p><a href="{HOME_URL}">{t("page.back_home")}</a></p>
"""


def _button(name: str, key: str, form: str | None = None) -> str:
    """Absendeknopf; erkannt wird er am Namen, die Beschriftung ist übersetzt."""
    form_attr = f' form="{form}"' if form else ""
    return f'<input type="submit" name="{name}" value="{html.escape(t(key), quote=True)}"{form_attr}>'


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
            f'{_button("rename", "page.bookmarks.rename", form)} '
            f'{_button("remove", "page.bookmarks.remove", form)}<br>'
            f'{_folder_select(choices, form, where[:-1], skip)} '
            f'{_button("move", "page.bookmarks.move", form)}')


def _bookmark_items(folder: bm.Folder, path: tuple[int, ...], edit: bool, forms: list[str],
                    choices: list[tuple[tuple[int, ...], str]]) -> str:
    items = []
    for i, child in enumerate(folder.children):
        where = path + (i,)
        if isinstance(child, bm.Folder):
            fields = _edit_fields(child, where, choices, forms) if edit else ""
            inner = _bookmark_items(child, where, edit, forms, choices)
            title = html.escape(child.title or t("bookmarks.unnamed_folder"))
            body = f"<ul>{inner}</ul>" if inner else f" <small>{t('page.bookmarks.empty')}</small>"
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
        in_folders = tn("bookmarks.folders", folder_count) if folder_count else ""
        summary = t("page.bookmarks.summary", bookmarks=tn("bookmarks.count", count), folders=in_folders)
        listing = f"<p>{summary}</p><ul>{items}</ul>"
    else:
        listing = f"<p>{t('page.bookmarks.none_yet')}</p>"
    action, label = ("done", "page.bookmarks.done") if ctx.bookmarks_edit else ("edit", "page.bookmarks.edit")
    toggle = (f'<form method="post" action="{BOOKMARKS_URL}"><input type="hidden" name="action" '
              f'value="{action}"><input type="submit" value="{html.escape(t(label), quote=True)}"></form>')
    new_folder = ""
    if ctx.bookmarks_edit:
        new_folder_form = t("page.bookmarks.new_folder_form", name='<input type="text" name="title" size="30">',
                            folder=_folder_select(choices, "new-folder", ()),
                            button=_button("add-folder", "page.bookmarks.create_folder"))
        new_folder = (f'<h2>{t("page.bookmarks.new_folder")}</h2>'
                      f'<form id="new-folder" method="post" action="{BOOKMARKS_URL}">'
                      f'<p>{new_folder_form}</p></form>'
                      f'<p><small>{t("page.bookmarks.edit_help")}</small></p>'
                      f'<h2>{t("page.bookmarks.all")}</h2>')
    return f"""<title>{t("page.bookmarks.title")}</title>
<h1>{t("page.bookmarks.title")}</h1>
{message}
{toggle}
{new_folder}
{listing}
{"".join(forms)}
<hr>
<h2>{t("page.bookmarks.file")}</h2>
<p>{t("page.bookmarks.file_location", path=html.escape(str(ctx.bookmarks_path)))}</p>
<p>{t("page.bookmarks.file_help")}</p>
<p><a href="{HOME_URL}">{t("page.back_home")}</a></p>
"""


def notes_page(ctx: PageContext | None = None) -> str:
    ctx = ctx or PageContext()
    message = f"<p><b>{html.escape(ctx.message)}</b></p>" if ctx.message else ""
    # Der Zeilenumbruch nach <textarea> wird beim Einlesen entfernt; so bleibt eine
    # Leerzeile am Anfang der Notizen erhalten.
    return f"""<title>{t("page.notes.title")}</title>
<h1>{t("page.notes.title")}</h1>
{message}
<form method="post" action="{NOTES_URL}">
<textarea name="text" cols="72" rows="20">
{html.escape(ctx.notes, quote=False)}</textarea>
<p>{_button("action", "page.notes.save")} <input type="reset" value="{html.escape(t("page.notes.discard"), quote=True)}"></p>
</form>
<p>{t("page.notes.help")}</p>
<p>{t("page.notes.location", path=html.escape(str(ctx.notes_path)))}</p>
<p><a href="{HOME_URL}">{t("page.back_home")}</a></p>
"""


INTERNAL_PAGES: dict[str, Callable[[PageContext | None], str]] = {
    HOME_URL: start_page,
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
    info = t("image.page_info", format=image_format, width=size[0], height=size[1])
    if shown != size:
        info += t("image.page_scaled", width=shown[0], height=shown[1])
    return (f"<title>{html.escape(name)} ({size[0]}×{size[1]})</title>"
            f'<p><img src="{html.escape(url)}" alt="{html.escape(name)}"></p>'
            f"<p><small>{html.escape(info)}</small></p>")


def error_page(url: str, message: str) -> str:
    return (f"<title>{t('page.error.title')}</title><h1>{t('page.error.heading')}</h1>"
            f"<p><code>{html.escape(url)}</code></p><p>{html.escape(message)}</p>")


def insecure_redirect_page(url: str, target: str) -> str:
    """Warnung statt einer Weiterleitung von HTTPS auf HTTP, mit Link zum Weitergehen."""
    return (f"<title>{t('page.insecure_redirect.title')}</title>"
            f"<h1>{t('page.insecure_redirect.heading')}</h1>"
            f"<p>{t('page.insecure_redirect.text', url=html.escape(url), target=html.escape(target))}</p>"
            f'<p><a href="{html.escape(target)}">{t("page.insecure_redirect.continue")}</a></p>')
