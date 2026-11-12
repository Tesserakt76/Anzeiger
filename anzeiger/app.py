"""Hauptfenster: Adresszeile, Navigation, Laden im Hintergrund."""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox, ttk
from urllib.parse import urlsplit

from . import forms, images, net
from .layout import FieldOp, ImageOp, Page, render_html, render_text
from .pages import (CONFIG_URL, HOME_URL, PageContext, error_page, internal_page, internal_url,
                    is_internal)
from .settings import Settings, default_path

MAX_IMAGES_PER_PAGE = 300


class App:
    def __init__(self, root: tk.Tk, start_url: str | None = None) -> None:
        from .view import PageView

        self.root = root
        self.settings_path = default_path()
        self.settings = Settings.load(self.settings_path)
        net.set_cookies_enabled(self.settings.cookies_enabled)
        self.page: Page | None = None
        root.title("Anzeiger")
        root.geometry("1000x750")
        root.minsize(500, 300)

        bar = ttk.Frame(root, padding=(6, 6, 6, 4))
        bar.pack(side="top", fill="x")
        self.back_button = ttk.Button(bar, text="←", width=3, command=self.back)
        self.forward_button = ttk.Button(bar, text="→", width=3, command=self.forward)
        self.home_button = ttk.Button(bar, text="⌂", width=3, command=self.home)
        self.reload_button = ttk.Button(bar, text="↻", width=3, command=self.reload)
        self.url_var = tk.StringVar()
        self.entry = ttk.Entry(bar, textvariable=self.url_var)
        go_button = ttk.Button(bar, text="Los", command=self.go)
        self.back_button.pack(side="left")
        self.forward_button.pack(side="left", padx=(2, 0))
        self.home_button.pack(side="left", padx=(2, 0))
        self.reload_button.pack(side="left", padx=(2, 6))
        self.entry.pack(side="left", fill="x", expand=True)
        go_button.pack(side="left", padx=(6, 0))

        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, anchor="w", padding=(8, 2)).pack(side="bottom", fill="x")
        self.view = PageView(root, on_link=self.follow_link, on_hover=self._on_hover,
                             on_submit=self.submit_form)
        self.view.pack(side="top", fill="both", expand=True)

        self.entry.bind("<Return>", lambda _e: self.go())
        self.entry.bind("<KP_Enter>", lambda _e: self.go())
        root.bind("<Control-l>", self._focus_entry)
        root.bind("<Alt-Left>", lambda _e: self.back())
        root.bind("<Alt-Right>", lambda _e: self.forward())
        root.bind("<Alt-Home>", lambda _e: self.home())
        root.bind("<F5>", lambda _e: self.reload())
        root.bind("<Escape>", lambda _e: self.stop())

        self.history: list[str] = []
        self.position = -1
        self.current_url: str | None = None
        self.generation = 0
        self.loading = False
        self.status_text = ""
        self.results: queue.Queue = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="anzeiger")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(40, self._poll)

        self.navigate(HOME_URL)
        if start_url:
            self.url_var.set(start_url)
            root.after(200, self.go)
        else:
            self.entry.focus_set()

    # -- Navigation -----------------------------------------------------------

    def go(self) -> None:
        text = self.url_var.get().strip()
        if text:
            self.navigate(text.lower() if is_internal(text) else net.user_url(text))

    def navigate(self, url: str, push: bool = True) -> None:
        if not self._allowed(url):
            self._set_status(f"Nur HTTP und HTTPS werden unterstützt: {url}")
            return
        if push:
            del self.history[self.position + 1:]
            self.history.append(url)
            self.position = len(self.history) - 1
        self._load(url)

    def follow_link(self, url: str) -> None:
        if not self._allowed(url):
            self._set_status(f"Nur HTTP und HTTPS werden unterstützt: {url}")
            return
        current = self.current_url
        fragment = urlsplit(url).fragment
        if current and fragment and net.without_fragment(url) == net.without_fragment(current):
            # Sprung innerhalb der Seite, ohne neu zu laden
            del self.history[self.position + 1:]
            self.history.append(url)
            self.position += 1
            self.current_url = url
            self.url_var.set(url)
            self.view.scroll_to(fragment)
            self._update_buttons()
            return
        self.navigate(url)

    @staticmethod
    def _allowed(url: str) -> bool:
        return net.is_supported(url) or is_internal(url)

    def home(self) -> None:
        self.navigate(HOME_URL)

    # -- Formulare --------------------------------------------------------------

    def submit_form(self, form_index: int | None, submitter: FieldOp | None,
                    entries: list[tuple[str, str]]) -> None:
        page = self.page
        if page is None or form_index is None or not 0 <= form_index < len(page.forms):
            self._set_status("Dieses Feld gehört zu keinem Formular.")
            return
        form = page.forms[form_index]
        action = (submitter.formaction if submitter and submitter.formaction else form.action)
        method = (submitter.formmethod if submitter and submitter.formmethod else form.method)
        enctype = (submitter.formenctype if submitter and submitter.formenctype else form.enctype)
        if is_internal(action):
            # Eingebaute Seiten nehmen nur Formulare eingebauter Seiten an, damit
            # keine Webseite Einstellungen ändern kann.
            if is_internal(page.url) and internal_url(action) == CONFIG_URL and method == "post":
                self._config_post(entries)
            else:
                self._set_status("Formular abgelehnt: Ziel ist eine eingebaute Seite.")
            return
        if not net.is_supported(action):
            self._set_status(f"Formular nicht abgeschickt – nur HTTP und HTTPS werden unterstützt: {action}")
            return
        if urlsplit(page.url).scheme == "https" and urlsplit(action).scheme == "http":
            if not messagebox.askyesno(
                    "Unverschlüsselt senden?",
                    f"Die Formulardaten würden unverschlüsselt (HTTP) gesendet an:\n{action}\n\n"
                    "Andere könnten sie mitlesen. Trotzdem senden?", icon="warning", parent=self.root):
                self._set_status("Abschicken abgebrochen.")
                return
        submission = forms.build_submission(action, method, enctype, entries)
        if submission.method == "GET":
            self.navigate(submission.url)
            return
        # POST: im Verlauf steht nur die Adresse; Zurück/Neu laden rufen sie per GET ab
        # und schicken die Formulardaten nicht erneut.
        del self.history[self.position + 1:]
        self.history.append(submission.url)
        self.position = len(self.history) - 1
        self._load(submission.url, submission, page.url)

    def _config_post(self, entries: list[tuple[str, str]]) -> None:
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
        self._show_internal(CONFIG_URL, message)
        self._set_status(message)

    def _render_internal(self, url: str, message: str = "") -> Page:
        ctx = PageContext(self.settings, self.settings_path, net.cookie_hosts(), message)
        return render_html(internal_page(url, ctx), internal_url(url), self.view.columns())

    def _show_internal(self, url: str, message: str = "") -> None:
        self.generation += 1
        self.loading = False
        self._page_loaded(url, self._render_internal(url, message))

    def back(self) -> None:
        if self.position > 0:
            self.position -= 1
            self._load(self.history[self.position])

    def forward(self) -> None:
        if self.position < len(self.history) - 1:
            self.position += 1
            self._load(self.history[self.position])

    def reload(self) -> None:
        if self.current_url:
            self._load(self.current_url)

    def stop(self) -> None:
        if self.loading:
            self.generation += 1
            self.loading = False
            self._set_status("Abgebrochen")

    def close(self) -> None:
        self.generation += 1
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    # -- Laden im Hintergrund -------------------------------------------------

    def _load(self, url: str, submission: forms.Submission | None = None,
              from_page: str | None = None) -> None:
        self.generation += 1
        generation = self.generation
        self.loading = True
        self.url_var.set(url)
        self._update_buttons()
        self._set_status(f"Lade {url} …")
        columns = self.view.columns()
        if is_internal(url):
            # Eingebaute Seiten sofort anzeigen, ohne Netzzugriff
            self._page_loaded(url, self._render_internal(url))
            return
        if submission is not None:
            self._set_status(f"Sende Formular an {url} …")

        def work() -> None:
            try:
                if submission is not None:
                    response = net.fetch(url, data=submission.body, content_type=submission.content_type,
                                         from_page=from_page)
                else:
                    response = net.fetch(url)
                page = self._build_page(response, columns)
                self.results.put((generation, "page", (url, page)))
            except Exception as error:  # Fehler als Seite anzeigen
                self.results.put((generation, "error", (url, str(error) or type(error).__name__)))

        self.pool.submit(work)

    @staticmethod
    def _build_page(response: net.Response, columns: int) -> Page:
        ctype = response.content_type
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

    def _poll(self) -> None:
        try:
            while True:
                generation, kind, payload = self.results.get_nowait()
                if generation != self.generation:
                    continue
                if kind == "page":
                    self._page_loaded(*payload)
                elif kind == "error":
                    url, message = payload
                    self.loading = False
                    self.current_url = url
                    self._show(render_html(error_page(url, message), url))
                    self._set_status(message)
                elif kind == "image":
                    self.view.set_image(*payload)
                elif kind == "image-error":
                    self.view.image_failed(*payload)
        except queue.Empty:
            pass
        self.root.after(40, self._poll)

    def _page_loaded(self, requested: str, page: Page) -> None:
        self.loading = False
        # Bei Weiterleitungen die tatsächliche Adresse anzeigen, Fragment beibehalten.
        fragment = urlsplit(requested).fragment
        url = page.url + ("#" + fragment if fragment and "#" not in page.url else "")
        self.current_url = url
        if 0 <= self.position < len(self.history):
            self.history[self.position] = url
        self.url_var.set(url)
        self._show(page)
        if fragment:
            self.view.scroll_to(fragment)
        self._set_status("Fertig")
        self._load_images(page)

    def _show(self, page: Page) -> None:
        self.page = page
        self.view.show(page, lambda op: self._image_note(page.url, op),
                       collapse_lists=self.settings.lists_collapsed,
                       collapse_sublists=self.settings.sublists_collapsed)
        self.root.title(f"{page.title} – Anzeiger" if page.title else "Anzeiger")

    @staticmethod
    def _image_note(page_url: str, op: ImageOp) -> str | None:
        if not op.src:
            return "Bild ohne Adresse"
        if not net.same_server(page_url, op.src):
            return f"Bild von fremdem Server – nicht geladen: {op.src}"
        return None

    def _load_images(self, page: Page) -> None:
        generation = self.generation
        max_width = self.view.content_width()
        for number, op in self.view.images[:MAX_IMAGES_PER_PAGE]:
            if self._image_note(page.url, op) is not None:
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
                    self.results.put((generation, "image", (number, png)))
                except Exception as error:
                    self.results.put((generation, "image-error",
                                      (number, f"Bild nicht geladen ({error}): {op.src}")))

            self.pool.submit(work)

    # -- Anzeige --------------------------------------------------------------

    def _on_hover(self, message: str | None) -> None:
        self.status.set(message if message else self.status_text)

    def _set_status(self, text: str) -> None:
        self.status_text = text
        self.status.set(text)

    def _update_buttons(self) -> None:
        self.back_button.state(["!disabled"] if self.position > 0 else ["disabled"])
        has_next = self.position < len(self.history) - 1
        self.forward_button.state(["!disabled"] if has_next else ["disabled"])

    def _focus_entry(self, _event: tk.Event | None = None) -> str:
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        self.entry.icursor("end")
        return "break"


def main() -> None:
    root = tk.Tk(className="Anzeiger")
    App(root, sys.argv[1] if len(sys.argv) > 1 else None)
    root.mainloop()


if __name__ == "__main__":
    main()
