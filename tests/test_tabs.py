import os
import tempfile
import tkinter as tk
import unittest
from unittest import mock

from anzeiger.pages import BOOKMARKS_URL, CONFIG_URL, HOME_URL


class TabsTest(unittest.TestCase):
    """Tabs im echten Fenster, nur mit eingebauten Seiten (ohne Netz)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
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


if __name__ == "__main__":
    unittest.main()
