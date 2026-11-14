import os
import tempfile
import time
import tkinter as tk
import unittest
from unittest import mock

from anzeiger import i18n, notes
from anzeiger.pages import BOOKMARKS_URL, CONFIG_URL, HOME_URL, NOTES_URL


class TabsTest(unittest.TestCase):
    """Tabs im echten Fenster, nur mit eingebauten Seiten (ohne Netz)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Deutsch als Systemsprache, damit die Meldungen unabhängig vom Rechner gleich sind
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name, "LANGUAGE": "de"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(i18n.set_language, i18n.SOURCE)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("keine grafische Anzeige")
        self.root.withdraw()
        from anzeiger.app import App
        self.app = App(self.root)
        self.update()

    def tearDown(self):
        try:
            self.app.close()
        except tk.TclError:
            pass
        self.tmp.cleanup()

    def update(self):
        self.root.update()

    def urls(self):
        return [tab.current_url for tab in self.app.tabs]

    def test_start_with_one_tab(self):
        self.assertEqual(self.urls(), [HOME_URL])
        self.assertEqual(self.app.url_var.get(), HOME_URL)

    def test_new_tab_has_own_history(self):
        first = self.app.tab
        first.navigate(CONFIG_URL)
        self.app.new_tab_key()
        self.update()
        second = self.app.tab
        self.assertIsNot(first, second)
        self.assertEqual(second.history, [HOME_URL])
        second.navigate(BOOKMARKS_URL)
        self.update()
        self.assertEqual(self.app.url_var.get(), BOOKMARKS_URL)
        self.app.select_tab(1)
        self.update()
        self.assertIs(self.app.tab, first)
        self.assertEqual(self.app.url_var.get(), CONFIG_URL)
        self.assertEqual(str(self.app.back_button.state()), "()")   # Zurück möglich
        first.back()
        self.assertEqual(first.current_url, HOME_URL)
        self.assertEqual(second.current_url, BOOKMARKS_URL)

    def test_links_open_in_background_in_order(self):
        origin = self.app.tab
        self.app.open_in_new_tab(CONFIG_URL)
        self.app.open_in_new_tab(BOOKMARKS_URL)
        self.update()
        self.assertIs(self.app.tab, origin)
        self.assertEqual(self.urls(), [HOME_URL, CONFIG_URL, BOOKMARKS_URL])
        self.app.open_in_new_tab("ftp://example.org/")
        self.assertEqual(len(self.app.tabs), 3)

    def test_close_and_reopen(self):
        self.app.new_tab()
        self.app.tab.navigate(CONFIG_URL)
        self.update()
        self.app.close_tab()
        self.update()
        self.assertEqual(self.urls(), [HOME_URL])
        self.assertEqual(self.app.url_var.get(), HOME_URL)
        self.app.reopen_closed_tab()
        self.update()
        self.assertEqual(self.urls(), [HOME_URL, CONFIG_URL])
        self.assertEqual(self.app.tab.history, [HOME_URL, CONFIG_URL])
        self.assertEqual(self.app.tab.position, 1)

    def test_closing_last_tab_leaves_start_page(self):
        only = self.app.tab
        only.navigate(CONFIG_URL)
        self.app.close_tab()
        self.update()
        self.assertTrue(only.closed)
        self.assertEqual(self.urls(), [HOME_URL])

    def test_cycle_and_close_others(self):
        self.app.new_tab(CONFIG_URL)
        self.app.new_tab(BOOKMARKS_URL)
        self.update()
        self.app.cycle_tabs(1)
        self.assertEqual(self.app.tab.current_url, HOME_URL)
        self.app.cycle_tabs(-1)
        self.assertEqual(self.app.tab.current_url, BOOKMARKS_URL)
        self.app.select_tab(9)
        self.assertEqual(self.app.tab.current_url, BOOKMARKS_URL)
        self.app.close_tab(self.app.tabs[1])
        self.app.reopen_closed_tab()
        self.assertEqual(self.urls(), [HOME_URL, CONFIG_URL, BOOKMARKS_URL])
        self.assertEqual(self.app.tab.current_url, CONFIG_URL)
        keep = self.app.tabs[1]
        self.app.close_other_tabs(keep)
        self.update()
        self.assertEqual(self.urls(), [CONFIG_URL])
        self.assertEqual(len(self.app.closed_tabs), 2)

    def test_results_of_closed_tab_are_ignored(self):
        tab = self.app.new_tab(CONFIG_URL)
        self.app.close_tab(tab)
        self.app.results.put((tab, tab.generation, "error", ("https://x.de/", "kaputt")))
        self.app._poll()
        self.assertEqual(tab.current_url, CONFIG_URL)

    def test_tab_label_follows_title(self):
        tab = self.app.new_tab(CONFIG_URL)
        self.update()
        self.assertEqual(self.app.notebook.tab(tab.view, "text"), tab.page.title)

    def test_zoom_applies_to_all_tabs_and_is_saved(self):
        other = self.app.new_tab(CONFIG_URL)
        self.update()
        size = other.view.base_font.cget("size")
        self.app.zoom_step(1)
        self.app.zoom_step(1)
        self.assertEqual(self.app.settings.zoom, 120)
        self.assertEqual(self.app.zoom_button.cget("text"), "120 %")
        self.assertGreater(other.view.base_font.cget("size"), size)
        self.assertEqual(self.app.tabs[0].view.zoom, 120)
        self.assertIn('"zoom": 120', self.app.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(self.app.new_tab().view.zoom, 120)
        self.app.zoom_step(0)
        self.assertEqual(other.view.base_font.cget("size"), size)

    def notes_box(self, tab):
        return next(w for w in tab.view.text.window_names() if self.root.nametowidget(w).winfo_class() == "Text")

    def type_notes(self, tab, text):
        box = self.root.nametowidget(self.notes_box(tab))
        box.delete("1.0", "end")
        box.insert("1.0", text)

    def test_notes_saved_with_key_and_when_leaving(self):
        tab = self.app.tab
        tab.navigate(NOTES_URL)
        self.update()
        self.type_notes(tab, "Einkaufen\nBrot")
        self.app._save_key(None)
        self.assertEqual(notes.load(self.app.notes_path), "Einkaufen\nBrot")
        self.assertEqual(tab.status_text, "Notizen gespeichert.")
        self.type_notes(tab, "Ungespeichert")
        tab.navigate(CONFIG_URL)
        self.assertEqual(notes.load(self.app.notes_path), "Ungespeichert")
        tab.back()
        self.update()
        self.type_notes(tab, "Beim Schließen")
        self.app.close_tab(tab)
        self.assertEqual(notes.load(self.app.notes_path), "Beim Schließen")

    def test_language_switch(self):
        tab = self.app.tab
        tab.navigate(CONFIG_URL)
        self.app.config_post(tab, [("action", "save"), ("language", "eo"), ("cookies", "on")])
        self.assertEqual(self.app.settings.language, "eo")
        self.assertIn('"language": "eo"', self.app.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(i18n.language(), "eo")
        self.assertEqual((tab.status_text, tab.page.title), (i18n.t("config.saved"), i18n.t("page.config.title")))
        self.assertEqual(self.app.go_button.cget("text"), i18n.t("app.go"))
        self.assertEqual(self.app.zoom_menu.entrycget(0, "label"), i18n.t("zoom.larger"))
        # Lesezeichen-Knöpfe werden am Namen erkannt, nicht an der (übersetzten) Beschriftung.
        self.app.bookmarks_post(tab, [("title", "Projektoj"), ("dest", ""), ("add-folder", "Krei dosierujon")])
        self.assertEqual(tab.status_text, i18n.t("bookmarks.folder_created", title="Projektoj"))
        self.app.bookmarks_post(tab, [("path", "0"), ("key", "Projektoj"), ("title", "Projekte"),
                                      ("rename", "Renomi")])
        self.assertEqual(self.app._bookmarks().children[0].title, "Projekte")
        self.app.config_post(tab, [("action", "save"), ("language", "de")])
        self.assertEqual(self.app.bookmark_button.cget("text"), "Lesezeichen")

    def test_find_on_page(self):
        from anzeiger.layout import render_html
        tab = self.app.tab
        tab._show(render_html("<p>Apfel und Birne</p><ul><li>apfel<ul><li>APFEL</li></ul></li></ul>",
                              "https://a.de/"))
        result = lambda: self.app.find_result.cget("text")
        self.app.open_find()
        self.assertTrue(self.app.find_visible)
        self.app.find_var.set("apfel")   # sucht schon beim Tippen
        self.assertEqual(result(), "1 von 3")
        self.app.find_step(1)
        self.app.find_step(1)
        self.assertEqual(result(), "3 von 3")
        text = tab.view.text
        self.assertEqual(text.get(*text.tag_ranges("find:current")), "APFEL")
        self.app.find_step(1)
        self.assertEqual(result(), "1 von 3")   # am Ende geht es von vorn weiter
        self.app.find_step(-1)
        self.assertEqual(result(), "3 von 3")
        # Eingeklappte Unterlisten werden nicht durchsucht.
        tab.view.toggle_fold("toggle:1")
        self.app.find_step(0)
        self.assertEqual(result(), "1 von 2")
        self.app.find_var.set("Kirsche")
        self.assertEqual(result(), "Keine Treffer")
        self.app.find_var.set("birne")
        self.app.close_find()
        self.assertFalse(self.app.find_visible)
        self.assertEqual(text.tag_ranges("find"), ())

    def test_hidden_content_collapsed_until_clicked(self):
        from anzeiger.layout import render_html
        tab = self.app.tab
        tab._show(render_html('<p>Vorher <span style="display:none">Geheimtext</span> nachher</p>'
                              '<form><input name="hp" style="display:none"></form>', "https://a.de/",
                              fold_hidden=True))
        self.update()
        text = tab.view.text
        field = text.window_names()[0]
        elided = lambda: text.tag_cget("fold:1", "elide") == "1" and "fold:1" in text.tag_names(text.index(field))
        self.assertTrue(elided())   # Honeypot-Feld liegt im eingeklappten Bereich
        self.assertEqual(tab.view.find("Geheimtext"), (1, 1))   # nur der Hinweis in der Schalterzeile
        self.assertEqual(tab.view.find("nachher"), (1, 1))
        tab.view.toggle_fold("toggle:1")
        self.update()
        self.assertFalse(elided())
        tab.view.toggle_fold("toggle:0")
        self.assertEqual(tab.view.find("Geheimtext"), (1, 2))

    def test_images_replace_placeholders(self):
        import io
        from PIL import Image
        from anzeiger import images, view
        from anzeiger.layout import render_html
        out = io.BytesIO()
        Image.new("RGBA", (30, 20), (255, 0, 0, 128)).save(out, "PNG")
        data, _size = images.decode_image(out.getvalue())
        tab = self.app.tab
        tab._show(render_html('<p><img src="/a.png" alt="A"> <img src="/b.png" alt="B"></p>', "https://a.de/"))
        tab.view.set_image(0, data)
        with mock.patch.object(view, "ImageTk", None):   # ohne python3-pil.imagetk
            tab.view.set_image(1, data)
        text = tab.view.text
        self.assertEqual(len(text.image_names()), 2)
        self.assertNotIn("[Bild", text.get("1.0", "end"))
        self.assertEqual(self.root.call("image", "width", text.image_names()[0]), 30)

    def test_lock_shows_connection_security(self):
        from anzeiger.layout import render_html
        tab = self.app.tab
        icons = self.app.lock_icons
        self.assertIsNone(tab.secure)   # eingebaute Seite
        self.assertEqual(self.app.lock_label.cget("image")[0], str(icons[None]))
        tab._page_loaded("https://a.de/", render_html("<p>x</p>", "https://a.de/"))
        self.assertIs(tab.secure, True)
        self.assertEqual(self.app.lock_label.cget("image")[0], str(icons[True]))
        self.assertIn("HTTPS", self.app._lock_text())
        tab._page_loaded("https://a.de/", render_html("<p>x</p>", "http://a.de/"))   # weitergeleitet
        self.assertIs(tab.secure, False)
        self.assertEqual(self.app.lock_label.cget("image")[0], str(icons[False]))
        self.assertIn("Unverschlüsselt", self.app._lock_text())
        tab.receive("error", ("https://b.de/", "Zertifikat ungültig"))
        self.assertIsNone(tab.secure)
        self.assertIsNone(self.app._lock_text())

    def test_insecure_redirect_shows_warning_with_link(self):
        tab = self.app.tab
        tab.receive("insecure-redirect", ("https://a.de/", "http://a.de/x"))
        self.assertEqual(tab.current_url, "https://a.de/")
        self.assertIsNone(tab.secure)
        self.assertEqual(tab.page.title, "Unverschlüsselte Weiterleitung")
        links = [op.style.href for op in tab.page.ops if getattr(op, "style", None) and op.style.href]
        self.assertIn("http://a.de/x", links)
        self.assertIn("http://a.de/x", self.app.status.get())

    def wait_loaded(self, tab):
        for _ in range(200):
            self.app._poll()
            self.update()
            if not tab.loading:
                return
            time.sleep(0.01)
        self.fail("Seite lädt nicht fertig")

    def picture(self):
        import io
        from PIL import Image
        from anzeiger import images
        out = io.BytesIO()
        Image.new("RGB", (8, 8), (0, 0, 255)).save(out, "PNG")
        return out.getvalue(), images.decode_image(out.getvalue())[0]

    def test_context_menu_entries(self):
        from anzeiger.layout import render_html
        tab = self.app.tab
        view, text = tab.view, tab.view.text
        tab._show(render_html('<p>Text <a href="/x">Link</a> <a href="/gross"><img src="/b.png"></a>'
                              ' <img src="/c.png"> <img src="/d.png" alt="D"></p>', "https://a.de/"))
        _png, data = self.picture()
        view.set_image(0, data)
        view.set_image(1, data)
        opened = []
        view.on_link_new_tab = opened.append

        def labels(index):
            with mock.patch.object(view, "_index_at", return_value=index):
                self.entries = view.context_entries(None)
            return [entry and entry[0] for entry in self.entries]

        source = "Seitenquelltext anzeigen"
        self.assertEqual(labels("1.0"), [source])
        self.assertEqual(labels(None), [source])   # neben dem Text
        text.tag_add("sel", "1.0", "1.4")
        self.assertEqual(labels("1.0"), ["Kopieren", None, source])
        view.copy_selection()
        self.assertEqual(self.root.clipboard_get(), "Text")
        text.tag_remove("sel", "1.0", "end")
        link = text.tag_ranges("link")[0]
        self.assertEqual(labels(link), ["Link in neuem Tab öffnen", None, source])
        self.entries[0][1]()
        self.assertEqual(opened, ["https://a.de/x"])
        self.assertEqual(labels(text.tag_ranges("img:0")[0]),
                         ["Link in neuem Tab öffnen", "Bild in neuem Tab öffnen", "Bild herunterladen als …",
                          None, source])
        self.entries[1][1]()
        self.assertEqual(opened[-1], "https://a.de/b.png")
        self.assertEqual(labels(text.tag_ranges("img:1")[0]), ["Bild herunterladen als …", None, source])
        self.assertEqual(labels(text.tag_ranges("img:2")[0]), [source])   # Platzhalter, nicht geladen
        tab.navigate(CONFIG_URL)
        self.assertEqual(labels("1.0"), [])   # eingebaute Seite: kein Quelltext

    def test_field_context_menu(self):
        from anzeiger.layout import render_html
        tab = self.app.tab
        tab._show(render_html('<form><input name="q" value="abc"><input type="password" name="p" value="geheim">'
                              '<input name="r" value="fest" readonly></form>', "https://a.de/"))
        self.update()
        query, password, fixed = (tab.view.nametowidget(name) for name in tab.view.text.window_names())
        self.root.clipboard_clear()
        self.root.clipboard_append("neu")
        shown = []
        with mock.patch.object(tab.view, "_popup", lambda _e, entries: shown.append(entries)):
            for widget in (query, password, fixed):
                widget.selection_range(0, "end")
                widget.event_generate("<Button-3>", x=2, y=2)
        self.assertEqual([[entry[0] for entry in entries] for entries in shown],
                         [["Kopieren", "Einfügen"], ["Einfügen"], ["Kopieren"]])
        query.icursor("end")
        query.selection_clear()
        shown[0][1][1]()   # Einfügen
        self.assertEqual(query.get(), "abcneu")

    def test_view_source_in_new_tab(self):
        from anzeiger import net
        from anzeiger.layout import render_html
        tab = self.app.tab
        tab._show(render_html("<p>Hallo</p>", "https://a.de/x#teil"))
        response = net.Response("https://a.de/x", 200, "OK", "text/html", "utf-8", b"<p>Hallo</p>")
        with mock.patch("anzeiger.net.fetch", return_value=response) as fetch:
            tab.view_source()
            source = self.app.tab
            self.assertIsNot(source, tab)
            self.wait_loaded(source)
        fetch.assert_called_once_with("https://a.de/x")
        self.assertEqual(source.current_url, "view-source:https://a.de/x")
        self.assertEqual(source.page.title, "Quelltext: https://a.de/x")
        self.assertIn("<p>Hallo</p>", source.view.text.get("1.0", "end"))
        self.assertIs(source.secure, True)
        self.assertEqual(self.app.tabs.index(source), self.app.tabs.index(tab) + 1)
        self.assertTrue(self.app.allowed("view-source:http://a.de/"))
        picture = net.Response("https://a.de/b.png", 200, "OK", "image/png", None, b"\x89PNG")
        from anzeiger.app import Tab
        self.assertEqual(Tab._source_page(picture).title, "Fehler")

    def test_save_image(self):
        from anzeiger import net
        png, _data = self.picture()
        tab = self.app.tab
        target = os.path.join(self.tmp.name, "bild.png")
        response = net.Response("https://a.de/b.png", 200, "OK", "image/png", None, png)
        with (mock.patch("anzeiger.app.filedialog.asksaveasfilename", return_value=target) as ask,
              mock.patch("anzeiger.net.fetch", return_value=response)):
            tab.save_image("https://a.de/bilder/b%C3%A4r.png")
            for _ in range(200):
                self.app._poll()
                if os.path.exists(target) and "gespeichert" in self.app.status.get():
                    break
                time.sleep(0.01)
        self.assertEqual(ask.call_args.kwargs["initialfile"], "bär.png")
        with open(target, "rb") as file:
            self.assertEqual(file.read(), png)
        self.assertEqual(self.app.status.get(), f"Bild gespeichert: {target}")

    def test_poll_leaves_rest_for_next_round(self):
        tab = self.app.tab
        for _ in range(3):
            self.app.results.put((tab, tab.generation, "image-error", (0, "kaputt")))
        with mock.patch("anzeiger.app.POLL_BUDGET", -1):   # Budget sofort erschöpft
            self.app._poll()
        self.assertEqual(self.app.results.qsize(), 2)
        self.app._poll()
        self.assertEqual(self.app.results.qsize(), 0)

    def test_unchanged_notes_tab_does_not_overwrite(self):
        old = self.app.tab
        old.navigate(NOTES_URL)
        new = self.app.new_tab(NOTES_URL)
        self.update()
        self.type_notes(new, "Neuer Stand")
        self.app._save_key(None)
        old.navigate(CONFIG_URL)
        self.assertEqual(notes.load(self.app.notes_path), "Neuer Stand")


if __name__ == "__main__":
    unittest.main()
