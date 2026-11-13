"""Hauptfenster: Adresszeile, Tabs, Navigation, Laden im Hintergrund."""

from __future__ import annotations

import base64
import math
import queue
import sys
import time
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from . import bookmarks, forms, i18n, images, net, notes
from .i18n import keys, t, tn
from .layout import FieldOp, ImageOp, Page, render_html, render_text
from .pages import (BOOKMARKS_URL, CONFIG_URL, HOME_URL, NOTES_URL, PageContext, error_page,
                    image_page, internal_page, internal_url, is_internal)
from .settings import ZOOM_LEVELS, Settings, default_path, zoom_step

if TYPE_CHECKING:
    from .view import PageView

MAX_IMAGES_PER_PAGE = 300
POLL_BUDGET = 0.05   # Sekunden pro Runde für Ergebnisse aus dem Hintergrund
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
        return self.current_url or self.address or t("app.new_tab")

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
            self.set_status(t("app.only_http", url=url))
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
            self.set_status(t("app.only_http", url=url))
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
            self.set_status(t("app.cancelled"))
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
            self.set_status(t("form.no_form"))
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
                self.set_status(t("form.internal_rejected"))
            return
        if not net.is_supported(action):
            self.set_status(t("form.unsupported", url=action))
            return
        if urlsplit(page.url).scheme == "https" and urlsplit(action).scheme == "http":
            if not messagebox.askyesno(
                    t("form.insecure_title"), t("form.insecure_question", url=action),
                    icon="warning", parent=self.app.root):
                self.set_status(t("form.cancelled"))
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
        self.set_status(t("app.loading", url=url))
        self._changed()
        if is_internal(url):
            # Eingebaute Seiten sofort anzeigen, ohne Netzzugriff
            self._page_loaded(url, self.app.render_internal(url))
            return
        if submission is not None:
            self.set_status(t("app.sending", url=url))
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
            page = render_html(error_page(response.url, t("app.unsupported_type", type=ctype)),
                               response.url)
        if response.status >= 400 and not page.title:
            page.title = f"{response.status} {response.reason}"
        return page

    @staticmethod
    def _image_page(response: net.Response, max_width: int) -> Page:
        """Direkt aufgerufenes Bild: einmal dekodieren und als fertiges PNG an die Seite hängen."""
        try:
            image_format, size = images.probe(response.body)
            data, shown = images.decode_image(response.body, max_width=max_width)
        except images.ImageError as error:
            return render_html(error_page(response.url, t("image.cannot_show", error=error)),
                               response.url)
        page = render_html(image_page(response.url, image_format, size, shown), response.url)
        page.preloaded[response.url] = data
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
        self.set_status(t("app.done"))
        self._changed()
        self._load_images(page)

    def _show(self, page: Page) -> None:
        self.app.keep_notes(self)
        self.page = page
        settings = self.app.settings
        self.view.show(page, lambda op: self._image_note(page.url, op),
                       collapse_lists=settings.lists_collapsed,
                       collapse_sublists=settings.sublists_collapsed)
        if self.active and self.app.find_visible:
            self.app.find_step(0)

    @staticmethod
    def _image_note(page_url: str, op: ImageOp) -> str | None:
        if not op.src:
            return t("image.no_address")
        if not net.same_server(page_url, op.src):
            return t("image.foreign", url=op.src)
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
                    data, _size = images.decode_image(response.body, op.width, op.height, max_width)
                    results.put((self, generation, "image", (number, data)))
                except Exception as error:
                    results.put((self, generation, "image-error",
                                 (number, t("image.failed", error=error, url=op.src))))

            self.app.image_pool.submit(work)


class App:
    def __init__(self, root: tk.Tk, start_url: str | None = None) -> None:
        self.root = root
        self.settings_path = default_path()
        self.settings = Settings.load(self.settings_path)
        net.set_cookies_enabled(self.settings.cookies_enabled)
        i18n.set_language(self.settings.language)
        net.set_accept_language(i18n.language())
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
        self.go_button = ttk.Button(bar, text=t("app.go"), command=self.go)
        self.bookmark_menu = tk.Menu(root, tearoff=False, postcommand=self._fill_bookmark_menu)
        self.bookmark_button = ttk.Menubutton(bar, text=t("app.bookmarks_menu"), menu=self.bookmark_menu)
        self.zoom_var = tk.IntVar(value=self.settings.zoom)
        self.zoom_icon = _magnifier_icon(root)
        self.zoom_menu = tk.Menu(root, tearoff=False)
        self.zoom_button = ttk.Menubutton(bar, image=self.zoom_icon, compound="left", menu=self.zoom_menu,
                                          text=t("zoom.level", zoom=self.settings.zoom), width=5)
        self._fill_zoom_menu()
        new_tab_button = ttk.Button(bar, text="+", width=3, command=self.new_tab_key)
        self.back_button.pack(side="left")
        self.forward_button.pack(side="left", padx=(2, 0))
        self.home_button.pack(side="left", padx=(2, 0))
        self.reload_button.pack(side="left", padx=(2, 6))
        self.entry.pack(side="left", fill="x", expand=True)
        self.star_button.pack(side="left", padx=(2, 0))
        self.go_button.pack(side="left", padx=(6, 0))
        self.bookmark_button.pack(side="left", padx=(6, 0))
        self.zoom_button.pack(side="left", padx=(6, 0))
        new_tab_button.pack(side="left", padx=(6, 0))

        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, anchor="w", padding=(8, 2)).pack(side="bottom", fill="x")
        self.notebook = ttk.Notebook(root, takefocus=False)
        self.notebook.pack(side="top", fill="both", expand=True)
        self._build_find_bar()
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
        for sequence in ("<Control-f>", "<Control-F>"):
            root.bind(sequence, self.open_find)
        root.bind("<F3>", lambda _e: self.find_step(1))
        root.bind("<Shift-F3>", lambda _e: self.find_step(-1))
        self.bind_tab_keys(root)

        self._tabs: dict[str, Tab] = {}
        self.closed_tabs: list[tuple[list[str], int, int]] = []   # (Verlauf, Position, Tab-Nr.)
        self._opened_from: tuple[Tab, Tab] | None = None   # (Ursprung, zuletzt daraus geöffnet)
        self.results: queue.Queue = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="anzeiger")
        # Eigene Threads für Bilder, damit eine neue Seite nicht hinter langsamen Bildern wartet.
        self.image_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="anzeiger-bild")
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
        self.image_pool.shutdown(wait=False, cancel_futures=True)
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
            self.notebook.insert(position, tab.view, text=t("app.new_tab"))
        else:
            self.notebook.add(tab.view, text=t("app.new_tab"))
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
            current.set_status(t("app.only_http", url=url))
            return
        after = current
        if self._opened_from and self._opened_from[0] is current and not self._opened_from[1].closed:
            after = self._opened_from[1]
        tab = self.new_tab(url, select=False, after=after)
        self._opened_from = (current, tab)
        current.set_status(t("app.opened_in_new_tab", url=url))

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
            self.tab.set_status(t("app.no_closed_tab"))
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
        label = t("app.loading_tab") if tab.loading else _short(tab.title, MAX_TAB_LABEL)
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
        self.root.title(t("app.window_title", title=title) if title else "Anzeiger")

    def _tab_switched(self, _event: tk.Event) -> None:
        if not self._tabs:
            return
        self._opened_from = None
        self._update_chrome()
        if self.find_visible:
            self.find_step(0)
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
            menu.add_command(label=t("tab_menu.reload"), command=tab.reload)
            menu.add_command(label=t("tab_menu.close"), accelerator=keys("ctrl", "W"),
                             command=lambda: self.close_tab(tab))
            menu.add_command(label=t("tab_menu.close_others"), command=lambda: self.close_other_tabs(tab),
                             state="normal" if len(self._tabs) > 1 else "disabled")
            menu.add_separator()
        menu.add_command(label=t("tab_menu.new"), accelerator=keys("ctrl", "T"), command=self.new_tab_key)
        menu.add_command(label=t("tab_menu.reopen"), accelerator=keys("ctrl", "shift", "T"),
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
            message = t("config.cookies_cleared")
        elif action == "save":
            self.settings.cookies_enabled = "cookies" in data
            self.settings.lists_collapsed = "lists" in data
            self.settings.sublists_collapsed = "sublists" in data
            net.set_cookies_enabled(self.settings.cookies_enabled)
            language = data.get("language", self.settings.language)
            if language != self.settings.language:
                self.settings.language = language
                self.set_language(language)
            try:
                self.settings.save(self.settings_path)
                message = t("config.saved")
            except OSError as error:
                message = t("config.save_failed", error=error)
        else:
            message = t("app.unknown_action")
        tab.show_internal(CONFIG_URL, message)
        tab.set_status(message)

    def set_language(self, code: str) -> None:
        """Wechselt die Sprache; Knöpfe, Menüs und Tab-Beschriftungen sofort, Seiten beim nächsten Laden."""
        i18n.set_language(code)
        net.set_accept_language(i18n.language())
        self.go_button.configure(text=t("app.go"))
        self.bookmark_button.configure(text=t("app.bookmarks_menu"))
        self.zoom_button.configure(text=t("zoom.level", zoom=self.settings.zoom))
        self._fill_zoom_menu()
        self.find_label.configure(text=t("find.label"))
        self.find_step(0)
        for tab in self._tabs.values():
            self.tab_changed(tab)

    def render_internal(self, url: str, message: str = "") -> Page:
        notes_text = ""
        if internal_url(url) == NOTES_URL:
            try:
                notes_text = notes.load(self.notes_path)
            except OSError as error:
                message = message or t("notes.unreadable", error=error)
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
                self._set_status(t("bookmarks.unreadable", error=error))
                return bookmarks.Folder("")
        return self._bookmarks_cache[1]

    def _bookmark_key(self, _event: tk.Event) -> str:
        self.toggle_bookmark()
        return "break"

    def toggle_bookmark(self) -> None:
        """Setzt ein Lesezeichen für die aktuelle Seite oder entfernt es nach Rückfrage."""
        tab = self.tab
        url = tab.current_url
        if not url or not net.is_supported(url):
            self._set_status(t("bookmarks.only_web"))
            return
        try:
            if self._bookmarks().find_url(url) is None:
                title = tab.page.title if tab.page and tab.page.title else url
                bookmarks.add(self.bookmarks_path, url, title)
                message = t("bookmarks.saved", title=title)
            elif messagebox.askyesno(t("bookmarks.remove_title"), t("bookmarks.remove_question", url=url),
                                     parent=self.root):
                bookmarks.remove_url(self.bookmarks_path, url)
                message = t("bookmarks.removed")
            else:
                return
        except OSError as error:
            message = t("bookmarks.save_failed", error=error)
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
        menu.add_command(label=t("bookmarks.remove") if marked else t("bookmarks.add"),
                         accelerator=keys("ctrl", "D"), command=self.toggle_bookmark,
                         state="normal" if url and net.is_supported(url) else "disabled")
        menu.add_command(label=t("bookmarks.manage"), accelerator=keys("ctrl", "shift", "O"),
                         command=lambda: self.tab.navigate(BOOKMARKS_URL))
        root = self._bookmarks()
        if root.children:
            menu.add_separator()
            self._add_menu_entries(menu, root)

    def _add_menu_entries(self, menu: tk.Menu, folder: bookmarks.Folder) -> None:
        shown = 0
        for child in folder.children:
            if shown >= MAX_MENU_ENTRIES:
                menu.add_command(label=t("bookmarks.more"),
                                 command=lambda: self.tab.navigate(BOOKMARKS_URL))
                break
            if isinstance(child, bookmarks.Folder):
                submenu = tk.Menu(menu, tearoff=False)
                self._add_menu_entries(submenu, child)
                if not child.children:
                    submenu.add_command(label=t("bookmarks.empty"), state="disabled")
                menu.add_cascade(label=_short(child.title or t("bookmarks.unnamed_folder")), menu=submenu)
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
        # Knöpfe werden am Namen erkannt, ihre Beschriftung hängt von der Sprache ab.
        action = data.get("action") or next(
            (name for name in ("add-folder", "rename", "move", "remove") if name in data), None)
        where = bookmarks.parse_path(data.get("path", ""))
        key = data.get("key", "")
        title = data.get("title", "")
        dest = bookmarks.parse_folder(data.get("dest", ""))
        gone = t("bookmarks.gone")
        try:
            if action == "edit":
                self.bookmarks_edit, message = True, ""
            elif action == "done":
                self.bookmarks_edit, message = False, ""
            elif action == "add-folder" and dest is not None:
                if not title.strip():
                    message = t("bookmarks.folder_name_missing")
                elif bookmarks.add_folder(self.bookmarks_path, dest, title):
                    message = t("bookmarks.folder_created", title=" ".join(title.split()))
                else:
                    message = t("bookmarks.target_missing")
            elif action == "rename" and where is not None:
                if not title.strip():
                    message = t("bookmarks.name_empty")
                elif bookmarks.rename_at(self.bookmarks_path, where, key, title):
                    message = t("bookmarks.renamed")
                else:
                    message = gone
            elif action == "move" and where is not None and dest is not None:
                try:
                    moved = bookmarks.move_at(self.bookmarks_path, where, key, dest)
                    message = t("bookmarks.moved") if moved else gone
                except ValueError as error:
                    message = str(error)
            elif action == "remove" and where is not None:
                node = self._bookmarks().node(where)
                if (isinstance(node, bookmarks.Folder) and node.children and not messagebox.askyesno(
                        t("bookmarks.remove_folder_title"),
                        t("bookmarks.remove_folder_question", title=node.title,
                          bookmarks=tn("bookmarks.count", node.count())),
                        icon="warning", parent=self.root)):
                    message = t("bookmarks.nothing_removed")
                elif bookmarks.remove_at(self.bookmarks_path, where, key):
                    message = t("bookmarks.entry_removed")
                else:
                    message = gone
            else:
                message = t("app.unknown_action")
        except OSError as error:
            message = t("bookmarks.list_failed", error=error)
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

    def save_notes(self, text: str) -> tuple[bool, str]:
        """(gespeichert?, Meldung)"""
        try:
            notes.save(self.notes_path, text)
            return True, t("notes.saved")
        except OSError as error:
            return False, t("notes.save_failed", error=error)

    def keep_notes(self, tab: Tab) -> None:
        """Sichert geänderte Notizen, bevor die Seite verlassen oder der Tab geschlossen wird.

        Unveränderte Notizen werden nicht geschrieben, damit ein zweiter Tab mit
        about:notes nicht den neueren Stand aus einem anderen Tab überschreibt.
        """
        field = self._notes_field(tab)
        if field is not None and field[0] != field[1]:
            saved, message = self.save_notes(field[1])
            if not saved:
                messagebox.showerror(t("notes.dialog_title"), message, parent=self.root)

    def notes_post(self, tab: Tab, entries: list[tuple[str, str]]) -> None:
        text = dict(entries).get("text")
        message = t("app.unknown_action") if text is None else self.save_notes(text)[1]
        tab.show_internal(NOTES_URL, message)
        tab.set_status(message)

    def _save_key(self, _event: tk.Event) -> str | None:
        """Strg+S speichert die Notizen, wenn der sichtbare Tab about:notes zeigt."""
        field = self._notes_field(self.tab)
        if field is None:
            return None
        self.notes_post(self.tab, [("text", field[1])])
        return "break"

    # -- Suchen auf der Seite ------------------------------------------------------

    def _build_find_bar(self) -> None:
        """Suchleiste über der Statuszeile; erscheint mit Strg+F."""
        bar = self.find_bar = ttk.Frame(self.root, padding=(6, 2, 6, 2))
        self.find_label = ttk.Label(bar, text=t("find.label"))
        self.find_var = tk.StringVar()
        self.find_entry = ttk.Entry(bar, textvariable=self.find_var, width=30)
        previous = ttk.Button(bar, text="▲", width=3, command=lambda: self.find_step(-1))
        following = ttk.Button(bar, text="▼", width=3, command=lambda: self.find_step(1))
        self.find_result = ttk.Label(bar)
        close = ttk.Button(bar, text="✕", width=3, command=self.close_find)
        self.find_label.pack(side="left")
        self.find_entry.pack(side="left", padx=(4, 0))
        previous.pack(side="left", padx=(4, 0))
        following.pack(side="left", padx=(2, 0))
        self.find_result.pack(side="left", padx=(8, 0))
        close.pack(side="right")
        self.find_var.trace_add("write", lambda *_: self.find_step(0))

        def key(action: Callable[[], object]) -> Callable[[tk.Event], str]:
            def handler(_event: tk.Event) -> str:
                action()
                return "break"
            return handler

        for sequence, action in (("<Return>", lambda: self.find_step(1)), ("<KP_Enter>", lambda: self.find_step(1)),
                                 ("<Shift-Return>", lambda: self.find_step(-1)),
                                 ("<Shift-KP_Enter>", lambda: self.find_step(-1)),
                                 ("<Escape>", self.close_find)):
            self.find_entry.bind(sequence, key(action))

    @property
    def find_visible(self) -> bool:
        return bool(self.find_bar.winfo_manager())

    def open_find(self, _event: tk.Event | None = None) -> str:
        if not self.find_visible:
            self.find_bar.pack(side="bottom", fill="x", before=self.notebook)
            self.find_step(0)
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")
        self.find_entry.icursor("end")
        return "break"

    def close_find(self) -> None:
        self.find_bar.pack_forget()
        for tab in self._tabs.values():
            tab.view.clear_find()
        self.tab.view.text.focus_set()

    def find_step(self, step: int) -> None:
        """Sucht im sichtbaren Tab; step 1/-1 = nächster/voriger Treffer, 0 = Treffer nur auffrischen."""
        if not self.find_visible:
            if step:
                self.open_find()
            return
        pattern = self.find_var.get()
        current, total = self.tab.view.find(pattern, step)
        if not pattern:
            self.find_result.configure(text="")
        elif total:
            self.find_result.configure(text=t("find.result", current=current, total=total))
        else:
            self.find_result.configure(text=t("find.none"))

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
        self.zoom_button.configure(text=t("zoom.level", zoom=zoom))
        if zoom == self.settings.zoom:
            return
        self.settings.zoom = zoom
        for tab in self._tabs.values():
            tab.view.set_zoom(zoom)
        self._set_status(t("zoom.status", zoom=zoom))
        try:
            self.settings.save(self.settings_path)
        except OSError:
            pass   # gilt dann nur bis zum Beenden

    def _fill_zoom_menu(self) -> None:
        menu = self.zoom_menu
        menu.delete(0, "end")
        menu.add_command(label=t("zoom.larger"), accelerator=keys("ctrl", "+"), command=lambda: self.zoom_step(1))
        menu.add_command(label=t("zoom.smaller"), accelerator=keys("ctrl", "−"), command=lambda: self.zoom_step(-1))
        menu.add_command(label=t("zoom.original"), accelerator=keys("ctrl", "0"), command=lambda: self.zoom_step(0))
        menu.add_separator()
        for level in ZOOM_LEVELS:
            menu.add_radiobutton(label=t("zoom.level", zoom=level), value=level, variable=self.zoom_var,
                                 command=lambda level=level: self.set_zoom(level))

    # -- Ergebnisse aus dem Hintergrund und Anzeige ---------------------------------

    def _poll(self) -> None:
        # Nur so lange am Stück arbeiten, dass Fenster und Scrollbalken bedienbar bleiben;
        # was dann noch in der Schlange liegt, kommt gleich in der nächsten Runde dran.
        deadline = time.monotonic() + POLL_BUDGET
        delay = 40
        try:
            while True:
                tab, generation, kind, payload = self.results.get_nowait()
                if not tab.closed and generation == tab.generation:
                    tab.receive(kind, payload)
                if time.monotonic() > deadline:
                    delay = 1
                    break
        except queue.Empty:
            pass
        self._poll_job = self.root.after(delay, self._poll)

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
