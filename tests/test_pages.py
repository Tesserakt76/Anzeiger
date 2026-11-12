import re
import tempfile
import tomllib
import unittest
from pathlib import Path

from anzeiger import __version__, notes, pages, settings
from anzeiger.layout import render_html

ROOT = Path(__file__).resolve().parent.parent


class PagesTest(unittest.TestCase):
    def test_internal_urls(self):
        self.assertTrue(pages.is_internal("about:start"))
        self.assertTrue(pages.is_internal("ABOUT:Changelog#v0.2.0"))
        self.assertFalse(pages.is_internal("about:blank"))
        self.assertFalse(pages.is_internal("https://example.org"))

    def test_start_page_links_changelog(self):
        page = render_html(pages.internal_page(pages.HOME_URL), pages.HOME_URL)
        self.assertIn(pages.CHANGELOG_URL, pages.START_PAGE)
        self.assertEqual(page.title, "Anzeiger")

    def test_changelog_documents_current_version(self):
        source = pages.internal_page(pages.CHANGELOG_URL)
        newest = re.search(r'<h2 id="v([^"]+)"', source)
        self.assertIsNotNone(newest)
        self.assertEqual(newest.group(1), __version__, "neueste Changelog-Version muss __version__ sein")
        self.assertIn('href="about:start"', source)

    def test_pyproject_version_matches(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["version"], __version__)
        self.assertIn("changelog.html", data["tool"]["setuptools"]["package-data"]["anzeiger"])


class NotesTest(unittest.TestCase):
    def test_notes_roundtrip_through_page(self):
        text = "\nErste Zeile <b>&amp; mehr</b>\n  eingerückt\n"
        ctx = pages.PageContext(notes=text)
        page = render_html(pages.internal_page(pages.NOTES_URL, ctx), pages.NOTES_URL)
        self.assertEqual(page.title, "Notizen")
        area = next(op for op in page.ops if getattr(op, "kind", None) == "textarea")
        self.assertEqual((area.name, area.value), ("text", text))
        self.assertEqual(page.forms[area.form].action, pages.NOTES_URL)
        self.assertIn(pages.NOTES_URL, pages.START_PAGE)

    def test_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "notes.txt"
            self.assertEqual(notes.load(path), "")
            notes.save(path, "Äpfel\nBirnen")
            self.assertEqual(notes.load(path), "Äpfel\nBirnen")


class ZoomTest(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(settings.zoom_step(100, 1), 110)
        self.assertEqual(settings.zoom_step(100, -1), 90)
        self.assertEqual(settings.zoom_step(300, 1), 300)
        self.assertEqual(settings.zoom_step(50, -1), 50)
        self.assertEqual(settings.zoom_step(128, 0), 133)

    def test_saved_zoom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            s = settings.Settings(zoom=150, cookies_enabled=False)
            s.save(path)
            self.assertEqual(settings.Settings.load(path), s)
            path.write_text('{"zoom": 1000, "lists_collapsed": 1}', encoding="utf-8")
            loaded = settings.Settings.load(path)
            self.assertEqual((loaded.zoom, loaded.lists_collapsed), (300, False))
            path.write_text('{"zoom": true}', encoding="utf-8")
            self.assertEqual(settings.Settings.load(path).zoom, 100)


if __name__ == "__main__":
    unittest.main()
