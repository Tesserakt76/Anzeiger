"""Hauptfenster: Adresszeile, Tabs, Navigation, Laden im Hintergrund."""

from __future__ import annotations

import base64
import math
import queue
import sys
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from . import bookmarks, forms, images, net, notes
from .layout import FieldOp, ImageOp, Page, render_html, render_text
from .pages import (BOOKMARKS_URL, CONFIG_URL, HOME_URL, NOTES_URL, PageContext, error_page,
                    image_page, internal_page, internal_url, is_internal)
from .settings import ZOOM_LEVELS, Settings, default_path, zoom_step

if TYPE_CHECKING:
    from .view import PageView

MAX_IMAGES_PER_PAGE = 300
MAX_MENU_ENTRIES = 50   # je Ordner im Lesezeichen-Menü
MAX_CLOSED_TABS = 20    # wiederherstellbar mit Strg+Umschalt+T
MAX_TAB_LABEL = 28      # Zeichen in der Tab-Beschriftung


class Tab:
    """Ein Tab: eigene Seitenansicht, eigener Verlauf, eigenes Laden im Hintergrund."""

    def __init__(self, app: App) -> None:
        from .view import PageView

        self.app = app
        self.view = PageView(app.notebook, on_link=self.follow_link, on_hover=app.on_hover,
                             on_submit=self.submit_form, on_link_new_tab=app.open_in_new_tab,
                             on_zoom=app.zoom_step, zoom=app.settings.zoom)
        app.bind_tab_keys(self.view.text)
        self.history: list[str] = []
        self.position = -1
        self.current_url: str | None = None
        self.page: Page | None = None
        self.address = ""        # Inhalt der Adresszeile, wenn der Tab sichtbar ist
        self.status_text = ""
        self.generation = 0
        self.loading = False
        self.closed = False

    @property
    def active(self) -> bool:
        return not self.closed and self.app.notebook.select() == str(self.view)

    @property
    def title(self) -> str:
        if self.page is not None and self.page.title:
            return self.page.title
        return self.current_url or self.address or "Neuer Tab"

    def set_address(self, url: str) -> None:
        self.address = url
        if self.active:
            self.app.url_var.set(url)

    def set_status(self, text: str) -> None:
        self.status_text = text
        if self.active:
            self.app.status.set(text)

    def _changed(self) -> None:
        self.app.tab_changed(self)

    # -- Navigation -----------------------------------------------------------

    def navigate(self, url: str, push: bool = True) -> None:
        if not self.app.allowed(url):
            self.set_status(f"Nur HTTP und HTTPS werden unterstützt: {url}")
            return
        if push:
            self._push(url)
        self.load(url)

    def _push(self, url: str) -> None:
        del self.history[self.position + 1:]
        self.history.append(url)
        self.position = len(self.history) - 1

    def follow_link(self, url: str) -> None:
        if not self.app.allowed(url):
            self.set_status(f"Nur HTTP und HTTPS werden unterstützt: {url}")
            return
        current = self.current_url
        fragment = urlsplit(url).fragment
        if current and fragment and net.without_fragment(url) == net.without_fragment(current):
            # Sprung innerhalb der Seite, ohne neu zu laden
            self._push(url)
            self.current_url = url
            self.set_address(url)
            self.view.scroll_to(fragment)
            self._changed()
            return
        self.navigate(url)

    def back(self) -> None:
        if self.position > 0:
            self.position -= 1
            self.load(self.history[self.position])

    def forward(self) -> None:
        if self.position < len(self.history) - 1:
            self.position += 1
            self.load(self.history[self.position])

    def reload(self) -> None:
        if self.current_url:
            self.load(self.current_url)

    def stop(self) -> None:
        if self.loading:
            self.generation += 1
            self.loading = False
            self.set_status("Abgebrochen")
            self._changed()

    def close(self) -> None:
        """Bricht laufende Ladevorgänge ab und gibt die Anzeige frei."""
        self.app.keep_notes(self)
        self.closed = True
        self.generation += 1
        self.view.destroy()

    # -- Formulare --------------------------------------------------------------

    def submit_form(self, form_index: int | None, submitter: FieldOp | None,
                    entries: list[tuple[str, str]]) -> None:
        page = self.page
        if page is None or form_index is None or not 0 <= form_index < len(page.forms):
            self.set_status("Dieses Feld gehört zu keinem Formular.")
            return
        form = page.forms[form_index]
        action = (submitter.formaction if submitter and submitter.formaction else form.action)
        method = (submitter.formmethod if submitter and submitter.formmethod else form.method)
        enctype = (submitter.formenctype if submitter and submitter.formenctype else form.enctype)
        if is_internal(action):
            # Eingebaute Seiten nehmen nur Formulare eingebauter Seiten an, damit
            # keine Webseite Einstellungen ändern kann.
            target = internal_url(action)
            if is_internal(page.url) and method == "post" and target == CONFIG_URL:
                self.app.config_post(self, entries)
            elif is_internal(page.url) and method == "post" and target == BOOKMARKS_URL:
                self.app.bookmarks_post(self, entries)
            elif is_internal(page.url) and method == "post" and target == NOTES_URL:
                self.app.notes_post(self, entries)
            else:
                self.set_status("Formular abgelehnt: Ziel ist eine eingebaute Seite.")
            return
        if not net.is_supported(action):
            self.set_status(f"Formular nicht abgeschickt – nur HTTP und HTTPS werden unterstützt: {action}")
            return
        if urlsplit(page.url).scheme == "https" and urlsplit(action).scheme == "http":
            if not messagebox.askyesno(
                    "Unverschlüsselt senden?",
                    f"Die Formulardaten würden unverschlüsselt (HTTP) gesendet an:\n{action}\n\n"
                    "Andere könnten sie mitlesen. Trotzdem senden?", icon="warning", parent=self.app.root):
                self.set_status("Abschicken abgebrochen.")
                return
        submission = forms.build_submission(action, method, enctype, entries)
        if submission.method == "GET":
            self.navigate(submission.url)
            return
        # POST: im Verlauf steht nur die Adresse; Zurück/Neu laden rufen sie per GET ab
        # und schicken die Formulardaten nicht erneut.
        self._push(submission.url)
        self.load(submission.url, submission, page.url)

    def show_internal(self, url: str, message: str = "") -> None:
        self.generation += 1
        self._page_loaded(url, self.app.render_internal(url, message))

    # -- Laden im Hintergrund -------------------------------------------------

    def load(self, url: str, submission: forms.Submission | None = None,
             from_page: str | None = None) -> None:
        self.app.keep_notes(self)   # vor dem Lesen der Datei, falls about:notes neu geladen wird
        self.generation += 1
        generation = self.generation
        self.loading = True
        self.set_address(url)
        self.set_status(f"Lade {url} …")
        self._changed()
        if is_internal(url):
            # Eingebaute Seiten sofort anzeigen, ohne Netzzugriff
            self._page_loaded(url, self.app.render_internal(url))
            return
        if submission is not None:
            self.set_status(f"Sende Formular an {url} …")
        columns = self.app.columns()
        max_width = self.app.content_width()
        results = self.app.results

        def work() -> None:
            try:
                if submission is not None:
                    response = net.fetch(url, data=submission.body, content_type=submission.content_type,
                                         from_page=from_page)
                else:
                    response = net.fetch(url)
                page = self._build_page(response, columns, max_width)
                results.put((self, generation, "page", (url, page)))
            except Exception as error:  # Fehler als Seite anzeigen
                results.put((self, generation, "error", (url, str(error) or type(error).__name__)))

        self.app.pool.submit(work)

    @staticmethod
    def _build_page(response: net.Response, columns: int, max_width: int) -> Page:
        ctype = response.content_type
        if ctype in images.CONTENT_TYPES and response.status < 400:
            return Tab._image_page(response, max_width)
        if ctype in ("text/html", "application/xhtml+xml"):
            page = render_html(net.decode_body(response.body, response.charset), response.url, columns)
        elif ctype.startswith("text/"):
            page = render_text(net.decode_body(response.body, response.charset), response.url)
        else:
            page = render_html(error_page(response.url, f"Inhaltstyp „{ctype}“ wird nicht unterstützt."),
                               response.url)
        if response.status >= 400 and not page.title:
            page.title = f"{response.status} {response.reason}"
        return page

    @staticmethod
    def _image_page(response: net.Response, max_width: int) -> Page:
        """Direkt aufgerufenes Bild: einmal dekodieren und als fertiges PNG an die Seite hängen."""
        try:
            image_format, size = images.probe(response.body)
            png, shown = images.decode_image(response.body, max_width=max_width)
        except images.ImageError as error:
            return render_html(error_page(response.url, f"Bild kann nicht angezeigt werden: {error}"),
                               response.url)
        page = render_html(image_page(response.url, image_format, size, shown), response.url)
        page.preloaded[response.url] = png
        return page

    def receive(self, kind: str, payload: tuple) -> None:
        """Verarbeitet ein Ergebnis aus dem Hintergrund (nur aktuelle Generation)."""
        if kind == "page":
            self._page_loaded(*payload)
        elif kind == "error":
            url, message = payload
            self.loading = False
            self.current_url = url
            self._show(render_html(error_page(url, message), url))
            self.set_status(message)
            self._changed()
        elif kind == "image":
            self.view.set_image(*payload)
        elif kind == "image-error":
            self.view.image_failed(*payload)

    def _page_loaded(self, requested: str, page: Page) -> None:
        self.loading = False
        # Bei Weiterleitungen die tatsächliche Adresse anzeigen, Fragment beibehalten.
        fragment = urlsplit(requested).fragment
        url = page.url + ("#" + fragment if fragment and "#" not in page.url else "")
        self.current_url = url
        if 0 <= self.position < len(self.history):
            self.history[self.position] = url
        self.set_address(url)
        self._show(page)
        if fragment:
            self.view.scroll_to(fragment)
        self.set_status("Fertig")
        self._changed()
        self._load_images(page)

    def _show(self, page: Page) -> None:
        self.app.keep_notes(self)
        self.page = page
        settings = self.app.settings
        self.view.show(page, lambda op: self._image_note(page.url, op),
                       collapse_lists=settings.lists_collapsed,
                       collapse_sublists=settings.sublists_collapsed)

    @staticmethod
    def _image_note(page_url: str, op: ImageOp) -> str | None:
        if not op.src:
            return "Bild ohne Adresse"
        if not net.same_server(page_url, op.src):
            return f"Bild von fremdem Server – nicht geladen: {op.src}"
        return None

    def _load_images(self, page: Page) -> None:
        generation = self.generation
        max_width = self.app.content_width()
        results = self.app.results
        for number, op in self.view.images[:MAX_IMAGES_PER_PAGE]:
            if self._image_note(page.url, op) is not None:
                continue
            if op.src in page.preloaded:   # schon mit der Seite geladen
                self.view.set_image(number, page.preloaded[op.src])
                continue

            def work(number: int = number, op: ImageOp = op) -> None:
                if generation != self.generation:
                    return
                try:
                    response = net.fetch(op.src, accept="image/png,image/jpeg,image/gif,image/webp,image/bmp",
                                         max_bytes=net.MAX_IMAGE_BYTES, first_party=page.url)
                    if response.status >= 400:
                        raise images.ImageError(f"HTTP {response.status}")
                    png, _size = images.decode_image(response.body, op.width, op.height, max_width)
                    results.put((self, generation, "image", (number, png)))
                except Exception as error:
                    results.put((self, generation, "image-error",
                                 (number, f"Bild nicht geladen ({error}): {op.src}")))

            self.app.pool.submit(work)


class App:
    def __init__(self, root: tk.Tk, start_url: str | None = None) -> None:
        self.root = root
        self.settings_path = default_path()
        self.settings = Settings.load(self.settings_path)
        net.set_cookies_enabled(self.settings.cookies_enabled)
        self.bookmarks_path = bookmarks.default_path()
        self.bookmarks_edit = False
        self._bookmarks_cache: tuple[float, bookmarks.Folder] | None = None
        self.notes_path = notes.default_path()
        root.title("Anzeiger")
        root.geometry("1000x750")
        root.minsize(500, 300)

        bar = ttk.Frame(root, padding=(6, 6, 6, 4))
        bar.pack(side="top", fill="x")
        self.back_button = ttk.Button(bar, text="←", width=3, command=lambda: self.tab.back())
        self.forward_button = ttk.Button(bar, text="→", width=3, command=lambda: self.tab.forward())
        self.home_button = ttk.Button(bar, text="⌂", width=3, command=self.home)
        self.reload_button = ttk.Button(bar, text="↻", width=3, command=lambda: self.tab.reload())
        self.url_var = tk.StringVar()
        self.entry = ttk.Entry(bar, textvariable=self.url_var)
        self.star_button = ttk.Button(bar, text="☆", width=3, command=self.toggle_bookmark)
        go_button = ttk.Button(bar, text="Los", command=self.go)
        self.bookmark_menu = tk.Menu(root, tearoff=False, postcommand=self._fill_bookmark_menu)
        menu_button = ttk.Menubutton(bar, text="Lesezeichen", menu=self.bookmark_menu)
        self.zoom_var = tk.IntVar(value=self.settings.zoom)
        self.zoom_icon = _magnifier_icon(root)
        self.zoom_menu = tk.Menu(root, tearoff=False)
        self.zoom_button = ttk.Menubutton(bar, image=self.zoom_icon, compound="left", menu=self.zoom_menu,
                                          text=f"{self.settings.zoom} %", width=5)
        self._fill_zoom_menu()
        new_tab_button = ttk.Button(bar, text="+", width=3, command=self.new_tab_key)
        self.back_button.pack(side="left")
        self.forward_button.pack(side="left", padx=(2, 0))
        self.home_button.pack(side="left", padx=(2, 0))
        self.reload_button.pack(side="left", padx=(2, 6))
        self.entry.pack(side="left", fill="x", expand=True)
        self.star_button.pack(side="left", padx=(2, 0))
        go_button.pack(side="left", padx=(6, 0))
        menu_button.pack(side="left", padx=(6, 0))
        self.zoom_button.pack(side="left", padx=(6, 0))
        new_tab_button.pack(side="left", padx=(6, 0))

        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, anchor="w", padding=(8, 2)).pack(side="bottom", fill="x")
        self.notebook = ttk.Notebook(root, takefocus=False)
        self.notebook.pack(side="top", fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._tab_switched)
        self.notebook.bind("<ButtonRelease-2>", self._tab_middle_click)
        self.notebook.bind("<Button-3>", self._tab_context_menu)
        self.notebook.bind("<Double-Button-1>", self._tab_bar_double_click)
        self.tab_menu = tk.Menu(root, tearoff=False)

        self.entry.bind("<Return>", lambda _e: self.go())
        self.entry.bind("<KP_Enter>", lambda _e: self.go())
        root.bind("<Control-l>", self._focus_entry)
        root.bind("<Alt-Left>", lambda _e: self.tab.back())
        root.bind("<Alt-Right>", lambda _e: self.tab.forward())
        root.bind("<Alt-Home>", lambda _e: self.home())
        root.bind("<F5>", lambda _e: self.tab.reload())
        # Auch direkt an der Adresszeile, damit Strg+D dort kein Zeichen löscht.
        for widget in (root, self.entry):
            widget.bind("<Control-d>", self._bookmark_key)
        root.bind("<Control-Shift-O>", lambda _e: self.tab.navigate(BOOKMARKS_URL))
        root.bind("<Control-Shift-o>", lambda _e: self.tab.navigate(BOOKMARKS_URL))
        root.bind("<Escape>", lambda _e: self.tab.stop())
        for sequence, step in (("<Control-plus>", 1), ("<Control-equal>", 1), ("<Control-KP_Add>", 1),
                               ("<Control-minus>", -1), ("<Control-KP_Subtract>", -1),
                               ("<Control-Key-0>", 0), ("<Control-KP_0>", 0), ("<Control-KP_Insert>", 0)):
            root.bind(sequence, lambda _e, step=step: self._zoom_key(step))
        root.bind("<Control-s>", self._save_key)
        self.bind_tab_keys(root)

        self._tabs: dict[str, Tab] = {}
        self.closed_tabs: list[tuple[list[str], int, int]] = []   # (Verlauf, Position, Tab-Nr.)
        self._opened_from: tuple[Tab, Tab] | None = None   # (Ursprung, zuletzt daraus geöffnet)
        self.results: queue.Queue = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="anzeiger")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_job = root.after(40, self._poll)

        self.new_tab(HOME_URL)
        if start_url:
            self.tab.set_address(start_url)   # bleibt auch nach dem ersten Tabwechsel-Ereignis stehen
            root.after(200, self.go)
        else:
            self.entry.focus_set()

    @property
    def tab(self) -> Tab:
        """Der sichtbare Tab."""
        return self._tabs[self.notebook.select()]

    @property
    def tabs(self) -> list[Tab]:
        """Alle Tabs in der angezeigten Reihenfolge."""
        return [self._tabs[name] for name in self.notebook.tabs()]

    # -- Navigation im sichtbaren Tab ------------------------------------------

    def go(self) -> None:
        text = self.url_var.get().strip()
        if text:
            self.tab.navigate(text.lower() if is_internal(text) else net.user_url(text))

    @staticmethod
    def allowed(url: str) -> bool:
        return net.is_supported(url) or is_internal(url)

    def home(self) -> None:
        self.tab.navigate(HOME_URL)

    def close(self) -> None:
        for tab in self._tabs.values():
            self.keep_notes(tab)
            tab.generation += 1
        self.root.after_cancel(self._poll_job)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    # -- Tabs -----------------------------------------------------------------

    def bind_tab_keys(self, widget: tk.Misc) -> None:
        """Tastenkürzel für Tabs; auch am Textfeld, damit dessen eigene Belegung nicht greift."""
        def key(action: Callable[[], object]) -> Callable[[tk.Event], str]:
            def handler(_event: tk.Event) -> str:
                action()
                return "break"
            return handler

        for sequence, action in (
                ("<Control-t>", self.new_tab_key),
                ("<Control-w>", self.close_tab),
                ("<Control-Shift-T>", self.reopen_closed_tab),
                ("<Control-Shift-t>", self.reopen_closed_tab),
                ("<Control-Tab>", lambda: self.cycle_tabs(1)),
                ("<Control-Next>", lambda: self.cycle_tabs(1)),
                ("<Control-Shift-Tab>", lambda: self.cycle_tabs(-1)),
                ("<Control-ISO_Left_Tab>", lambda: self.cycle_tabs(-1)),
                ("<Control-Prior>", lambda: self.cycle_tabs(-1))):
            widget.bind(sequence, key(action))
        for number in range(1, 10):
            widget.bind(f"<Control-Key-{number}>", key(lambda n=number: self.select_tab(n)))

    def new_tab(self, url: str | None = HOME_URL, select: bool = True, after: Tab | None = None) -> Tab:
        """Öffnet einen Tab am Ende oder rechts neben `after` und lädt `url`."""
        tab = Tab(self)
        self._tabs[str(tab.view)] = tab
        if after is not None and not after.closed:
            position = self.notebook.index(after.view) + 1
            if position >= self.notebook.index("end"):
                position = "end"   # ttk lehnt die Anzahl der Tabs als Position ab
            self.notebook.insert(position, tab.view, text="Neuer Tab")
        else:
            self.notebook.add(tab.view, text="Neuer Tab")
        if select:
            self.notebook.select(tab.view)
        if url:
            tab.navigate(url)
        return tab

    def new_tab_key(self) -> None:
        self.new_tab(HOME_URL)
        self._focus_entry()

    def open_in_new_tab(self, url: str) -> None:
        """Link per Mittel- oder Strg+Klick im Hintergrund öffnen, rechts neben dem Ursprung.

        Mehrere Links aus demselben Tab landen in der Reihenfolge des Öffnens nebeneinander.
        """
        current = self.tab
        if not self.allowed(url):
            current.set_status(f"Nur HTTP und HTTPS werden unterstützt: {url}")
            return
        after = current
        if self._opened_from and self._opened_from[0] is current and not self._opened_from[1].closed:
            after = self._opened_from[1]
        tab = self.new_tab(url, select=False, after=after)
        self._opened_from = (current, tab)
        current.set_status(f"In neuem Tab geöffnet: {url}")

    def close_tab(self, tab: Tab | None = None) -> None:
        """Schließt einen Tab; der letzte wird durch einen leeren Tab mit der Startseite ersetzt."""
        tab = tab or self.tab
        if len(self._tabs) == 1:
            self.new_tab(HOME_URL)
        if tab.history:
            self.closed_tabs.append((list(tab.history), tab.position, self.notebook.index(tab.view)))
            del self.closed_tabs[:-MAX_CLOSED_TABS]
        self.notebook.forget(tab.view)
        del self._tabs[str(tab.view)]
        tab.close()

    def close_other_tabs(self, keep: Tab) -> None:
        for tab in self.tabs:
            if tab is not keep:
                self.close_tab(tab)
        self.notebook.select(keep.view)

    def reopen_closed_tab(self) -> None:
        if not self.closed_tabs:
            self.tab.set_status("Es gibt keinen geschlossenen Tab zum Wiederherstellen.")
            return
        history, position, index = self.closed_tabs.pop()
        tab = self.new_tab(None)
        if index < self.notebook.index("end") - 1:
            self.notebook.insert(index, tab.view)   # wieder an die alte Stelle
        tab.history, tab.position = history, position
        tab.load(history[position])

    def select_tab(self, number: int) -> None:
        """Strg+1 … Strg+8 wählen den n-ten Tab, Strg+9 den letzten."""
        names = self.notebook.tabs()
        if names:
            self.notebook.select(names[-1] if number == 9 else names[min(number, len(names)) - 1])

    def cycle_tabs(self, step: int) -> None:
        names = self.notebook.tabs()
        if len(names) > 1:
            self.notebook.select(names[(names.index(self.notebook.select()) + step) % len(names)])

    def tab_changed(self, tab: Tab) -> None:
        """Beschriftung des Tabs und – falls sichtbar – Adresszeile, Knöpfe und Titel nachführen."""
        if tab.closed:
            return
        label = "Lädt …" if tab.loading else _short(tab.title, MAX_TAB_LABEL)
        self.notebook.tab(tab.view, text=label)
        if tab.active:
            self._update_chrome()

    def _update_chrome(self) -> None:
        tab = self.tab
        self.url_var.set(tab.address)
        self.status.set(tab.status_text)
        self._update_buttons()
        self._update_star()
        title = tab.page.title if tab.page is not None and tab.page.title else ""
        self.root.title(f"{title} – Anzeiger" if title else "Anzeiger")

    def _tab_switched(self, _event: tk.Event) -> None:
        if not self._tabs:
            return
        self._opened_from = None
        self._update_chrome()
        # Lag der Fokus in der Seite des vorigen Tabs, wandert er mit in den neuen.
        try:
            focus = self.root.focus_get()
        except KeyError:
            focus = None
        if focus is not None and str(focus).startswith(str(self.notebook) + "."):
            self.tab.view.text.focus_set()

    def _tab_at(self, event: tk.Event) -> Tab | None:
        index = str(self.notebook.tk.call(str(self.notebook), "identify", "tab", event.x, event.y))
        if not index.isdigit():
            return None
        return self._tabs.get(self.notebook.tabs()[int(index)])

    def _tab_middle_click(self, event: tk.Event) -> None:
        tab = self._tab_at(event)
        if tab is not None:
            self.close_tab(tab)

    def _tab_bar_double_click(self, event: tk.Event) -> None:
        if self._tab_at(event) is None:   # freie Fläche neben den Tabs
            self.new_tab_key()

    def _tab_context_menu(self, event: tk.Event) -> None:
        tab = self._tab_at(event)
        menu = self.tab_menu
        menu.delete(0, "end")
        if tab is not None:
            menu.add_command(label="Neu laden", command=tab.reload)
            menu.add_command(label="Tab schließen", accelerator="Strg+W", command=lambda: self.close_tab(tab))
            menu.add_command(label="Andere Tabs schließen", command=lambda: self.close_other_tabs(tab),
                             state="normal" if len(self._tabs) > 1 else "disabled")
            menu.add_separator()
        menu.add_command(label="Neuer Tab", accelerator="Strg+T", command=self.new_tab_key)
        menu.add_command(label="Geschlossenen Tab wieder öffnen", accelerator="Strg+Umschalt+T",
                         command=self.reopen_closed_tab,
                         state="normal" if self.closed_tabs else "disabled")
        menu.tk_popup(event.x_root, event.y_root)

    def _sized_view(self) -> PageView:
        """Eine Seitenansicht mit echter Größe (Tabs im Hintergrund sind nicht ausgemessen)."""
        for tab in (self.tab, *self._tabs.values()):
            if tab.view.text.winfo_width() > 1:
                return tab.view
        return self.tab.view

    def columns(self) -> int:
        return self._sized_view().columns()

    def content_width(self) -> int:
        return self._sized_view().content_width()

    # -- Eingebaute Seiten --------------------------------------------------------

    def config_post(self, tab: Tab, entries: list[tuple[str, str]]) -> None:
        data: dict[str, str] = dict(entries)
        action = data.get("action")
        if action == "clear-cookies":
            net.clear_cookies()
            message = "Alle Cookies wurden gelöscht."
        elif action == "save":
            self.settings.cookies_enabled = "cookies" in data
            self.settings.lists_collapsed = "lists" in data
            self.settings.sublists_collapsed = "sublists" in data
            net.set_cookies_enabled(self.settings.cookies_enabled)
            try:
                self.settings.save(self.settings_path)
                message = "Einstellungen gespeichert."
            except OSError as error:
                message = f"Einstellungen gelten nur bis zum Beenden – Speichern fehlgeschlagen: {error}"
        else:
            message = "Unbekannte Aktion."
        tab.show_internal(CONFIG_URL, message)
        tab.set_status(message)

    def render_internal(self, url: str, message: str = "") -> Page:
        notes_text = ""
        if internal_url(url) == NOTES_URL:
            try:
                notes_text = notes.load(self.notes_path)
            except OSError as error:
                message = message or f"Notizen nicht lesbar: {error}"
        ctx = PageContext(self.settings, self.settings_path, net.cookie_hosts(), message,
                          self._bookmarks(), self.bookmarks_path, self.bookmarks_edit,
                          notes_text, self.notes_path)
        return render_html(internal_page(url, ctx), internal_url(url), self.columns())

    # -- Lesezeichen ---------------------------------------------------------------

    def _bookmarks(self) -> bookmarks.Folder:
        """Lesezeichen aus der Datei; neu gelesen, sobald sie sich geändert hat."""
        try:
            mtime = self.bookmarks_path.stat().st_mtime
        except OSError:
            mtime = -1.0
        if self._bookmarks_cache is None or self._bookmarks_cache[0] != mtime:
            try:
                self._bookmarks_cache = (mtime, bookmarks.load(self.bookmarks_path))
            except OSError as error:
                self._set_status(f"Lesezeichen-Datei nicht lesbar: {error}")
                return bookmarks.Folder("Lesezeichen")
        return self._bookmarks_cache[1]

    def _bookmark_key(self, _event: tk.Event) -> str:
        self.toggle_bookmark()
        return "break"

    def toggle_bookmark(self) -> None:
        """Setzt ein Lesezeichen für die aktuelle Seite oder entfernt es nach Rückfrage."""
        tab = self.tab
        url = tab.current_url
        if not url or not net.is_supported(url):
            self._set_status("Nur Webseiten (HTTP/HTTPS) können als Lesezeichen gespeichert werden.")
            return
        try:
            if self._bookmarks().find_url(url) is None:
                title = tab.page.title if tab.page and tab.page.title else url
                bookmarks.add(self.bookmarks_path, url, title)
                message = f"Lesezeichen gespeichert: {title}"
            elif messagebox.askyesno("Lesezeichen entfernen?",
                                     f"Das Lesezeichen für\n{url}\nentfernen?", parent=self.root):
                bookmarks.remove_url(self.bookmarks_path, url)
                message = "Lesezeichen entfernt."
            else:
                return
        except OSError as error:
            message = f"Lesezeichen konnte nicht gespeichert werden: {error}"
        self._update_star()
        self._set_status(message)

    def _update_star(self) -> None:
        url = self.tab.current_url
        marked = bool(url and net.is_supported(url) and self._bookmarks().find_url(url) is not None)
        self.star_button.configure(text="★" if marked else "☆")

    def _fill_bookmark_menu(self) -> None:
        menu = self.bookmark_menu
        menu.delete(0, "end")
        url = self.tab.current_url
        marked = bool(url and net.is_supported(url) and self._bookmarks().find_url(url) is not None)
        menu.add_command(label="Lesezeichen entfernen" if marked else "Lesezeichen für diese Seite",
                         accelerator="Strg+D", command=self.toggle_bookmark,
                         state="normal" if url and net.is_supported(url) else "disabled")
        menu.add_command(label="Lesezeichen verwalten", accelerator="Strg+Umschalt+O",
                         command=lambda: self.tab.navigate(BOOKMARKS_URL))
        root = self._bookmarks()
        if root.children:
            menu.add_separator()
            self._add_menu_entries(menu, root)

    def _add_menu_entries(self, menu: tk.Menu, folder: bookmarks.Folder) -> None:
        shown = 0
        for child in folder.children:
            if shown >= MAX_MENU_ENTRIES:
                menu.add_command(label="… weitere unter „Lesezeichen verwalten“",
                                 command=lambda: self.tab.navigate(BOOKMARKS_URL))
                break
            if isinstance(child, bookmarks.Folder):
                submenu = tk.Menu(menu, tearoff=False)
                self._add_menu_entries(submenu, child)
                if not child.children:
                    submenu.add_command(label="(leer)", state="disabled")
                menu.add_cascade(label=_short(child.title or "(Ordner ohne Namen)"), menu=submenu)
            elif isinstance(child, bookmarks.Bookmark):
                menu.add_command(label=_short(child.title or child.url),
                                 command=lambda u=child.url: self.tab.follow_link(u))
            else:   # Trennlinie, aber nie zwei hintereinander
                if menu.index("end") is not None and menu.type("end") != "separator":
                    menu.add_separator()
                continue
            shown += 1

    def bookmarks_post(self, tab: Tab, entries: list[tuple[str, str]]) -> None:
        data: dict[str, str] = dict(entries)
        action = data.get("action")
        where = bookmarks.parse_path(data.get("path", ""))
        key = data.get("key", "")
        title = data.get("title", "")
        dest = bookmarks.parse_folder(data.get("dest", ""))
        gone = "Eintrag nicht gefunden – die Datei wurde inzwischen geändert."
        try:
            if action == "edit":
                self.bookmarks_edit, message = True, ""
            elif action == "done":
                self.bookmarks_edit, message = False, ""
            elif action == "Ordner anlegen" and dest is not None:
                if not title.strip():
                    message = "Bitte einen Namen für den neuen Ordner eingeben."
                elif bookmarks.add_folder(self.bookmarks_path, dest, title):
                    message = f"Ordner „{' '.join(title.split())}“ angelegt."
                else:
                    message = "Der Zielordner wurde nicht gefunden."
            elif action == "Umbenennen" and where is not None:
                if not title.strip():
                    message = "Der Name darf nicht leer sein."
                elif bookmarks.rename_at(self.bookmarks_path, where, key, title):
                    message = "Umbenannt."
                else:
                    message = gone
            elif action == "Verschieben" and where is not None and dest is not None:
                try:
                    message = "Verschoben." if bookmarks.move_at(self.bookmarks_path, where, key, dest) else gone
                except ValueError as error:
                    message = str(error)
            elif action == "Entfernen" and where is not None:
                node = self._bookmarks().node(where)
                if (isinstance(node, bookmarks.Folder) and node.children and not messagebox.askyesno(
                        "Ordner entfernen?",
                        f"Der Ordner „{node.title}“ ist nicht leer ({node.count()} Lesezeichen). "
                        "Ihn samt Inhalt entfernen?", icon="warning", parent=self.root)):
                    message = "Nichts entfernt."
                elif bookmarks.remove_at(self.bookmarks_path, where, key):
                    message = "Entfernt."
                else:
                    message = gone
            else:
                message = "Unbekannte Aktion."
        except OSError as error:
            message = f"Lesezeichen konnten nicht gespeichert werden: {error}"
        tab.show_internal(BOOKMARKS_URL, message)
        if message:
            tab.set_status(message)

    # -- Notizen -------------------------------------------------------------------

    def _notes_field(self, tab: Tab) -> tuple[str, str] | None:
        """(gespeicherter, aktueller) Text, wenn der Tab gerade about:notes zeigt."""
        page = tab.page
        if tab.closed or page is None or internal_url(page.url) != NOTES_URL:
            return None
        op = next((op for op in page.ops if isinstance(op, FieldOp) and op.name == "text"), None)
        if op is None:
            return None
        current = dict(tab.view.form_entries(op.form, None)).get("text", op.value)
        return op.value, current

    def save_notes(self, text: str) -> str:
        try:
            notes.save(self.notes_path, text)
            return "Notizen gespeichert."
        except OSError as error:
            return f"Notizen konnten nicht gespeichert werden: {error}"

    def keep_notes(self, tab: Tab) -> None:
        """Sichert geänderte Notizen, bevor die Seite verlassen oder der Tab geschlossen wird.

        Unveränderte Notizen werden nicht geschrieben, damit ein zweiter Tab mit
        about:notes nicht den neueren Stand aus einem anderen Tab überschreibt.
        """
        field = self._notes_field(tab)
        if field is not None and field[0] != field[1]:
            message = self.save_notes(field[1])
            if not message.startswith("Notizen gespeichert"):
                messagebox.showerror("Notizen", message, parent=self.root)

    def notes_post(self, tab: Tab, entries: list[tuple[str, str]]) -> None:
        text = dict(entries).get("text")
        message = "Unbekannte Aktion." if text is None else self.save_notes(text)
        tab.show_internal(NOTES_URL, message)
        tab.set_status(message)

    def _save_key(self, _event: tk.Event) -> str | None:
        """Strg+S speichert die Notizen, wenn der sichtbare Tab about:notes zeigt."""
        field = self._notes_field(self.tab)
        if field is None:
            return None
        self.notes_post(self.tab, [("text", field[1])])
        return "break"

    # -- Lupe ----------------------------------------------------------------------

    def _zoom_key(self, step: int) -> str:
        self.zoom_step(step)
        return "break"

    def zoom_step(self, step: int) -> None:
        """Eine Stufe größer (1) oder kleiner (-1); 0 stellt die Originalgröße her."""
        self.set_zoom(100 if step == 0 else zoom_step(self.settings.zoom, step))

    def set_zoom(self, zoom: int) -> None:
        """Gilt für alle Tabs und bleibt nach einem Neustart erhalten."""
        self.zoom_var.set(zoom)
        self.zoom_button.configure(text=f"{zoom} %")
        if zoom == self.settings.zoom:
            return
        self.settings.zoom = zoom
        for tab in self._tabs.values():
            tab.view.set_zoom(zoom)
        self._set_status(f"Vergrößerung: {zoom} %")
        try:
            self.settings.save(self.settings_path)
        except OSError:
            pass   # gilt dann nur bis zum Beenden

    def _fill_zoom_menu(self) -> None:
        menu = self.zoom_menu
        menu.add_command(label="Vergrößern", accelerator="Strg++", command=lambda: self.zoom_step(1))
        menu.add_command(label="Verkleinern", accelerator="Strg+−", command=lambda: self.zoom_step(-1))
        menu.add_command(label="Originalgröße", accelerator="Strg+0", command=lambda: self.zoom_step(0))
        menu.add_separator()
        for level in ZOOM_LEVELS:
            menu.add_radiobutton(label=f"{level} %", value=level, variable=self.zoom_var,
                                 command=lambda level=level: self.set_zoom(level))

    # -- Ergebnisse aus dem Hintergrund und Anzeige ---------------------------------

    def _poll(self) -> None:
        try:
            while True:
                tab, generation, kind, payload = self.results.get_nowait()
                if not tab.closed and generation == tab.generation:
                    tab.receive(kind, payload)
        except queue.Empty:
            pass
        self._poll_job = self.root.after(40, self._poll)

    def on_hover(self, message: str | None) -> None:
        self.status.set(message if message else self.tab.status_text)

    def _set_status(self, text: str) -> None:
        if self._tabs:
            self.tab.set_status(text)
        else:
            self.status.set(text)

    def _update_buttons(self) -> None:
        tab = self.tab
        self.back_button.state(["!disabled"] if tab.position > 0 else ["disabled"])
        has_next = tab.position < len(tab.history) - 1
        self.forward_button.state(["!disabled"] if has_next else ["disabled"])

    def _focus_entry(self, _event: tk.Event | None = None) -> str:
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        self.entry.icursor("end")
        return "break"


def _short(label: str, limit: int = 60) -> str:
    label = " ".join(label.split())
    return label if len(label) <= limit else label[:limit - 1] + "…"


def _magnifier_icon(root: tk.Misc, size: int = 16) -> tk.PhotoImage:
    """Kleine Lupe für den Zoom-Knopf: Ring mit Griff nach rechts unten."""
    image = tk.PhotoImage(master=root, width=size, height=size)
    center, radius = size * 0.4, size * 0.28
    for y in range(size):
        for x in range(size):
            ring = abs(math.hypot(x + 0.5 - center, y + 0.5 - center) - radius) < size * 0.07
            handle = (x >= center + radius * 0.6 and y >= center + radius * 0.6
                      and abs(x - y) <= 1 and max(x, y) < size - 1)
            if ring or handle:
                image.put("#333333", (x, y))
    return image


def set_window_icon(root: tk.Tk) -> None:
    """Setzt das Zeitungssymbol als Fenstersymbol (fehlt es, bleibt das Standardsymbol)."""
    icons = resources.files(__package__).joinpath("icons")
    photos = []
    for size in (16, 32, 48, 64, 128, 256):
        try:
            data = icons.joinpath(f"anzeiger-{size}.png").read_bytes()
            photos.append(tk.PhotoImage(master=root, data=base64.b64encode(data).decode("ascii")))
        except (OSError, tk.TclError):
            continue
    if photos:
        root.iconphoto(True, *photos)
        root.anzeiger_icons = photos  # type: ignore[attr-defined]  # Referenz halten


def main() -> None:
    root = tk.Tk(className="Anzeiger")
    set_window_icon(root)
    App(root, sys.argv[1] if len(sys.argv) > 1 else None)
    root.mainloop()


if __name__ == "__main__":
    main()
