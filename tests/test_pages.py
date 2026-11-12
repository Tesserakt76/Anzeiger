import re
import tomllib
import unittest
from pathlib import Path

from anzeiger import __version__, pages
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


if __name__ == "__main__":
    unittest.main()
