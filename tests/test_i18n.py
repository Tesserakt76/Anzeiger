import os
import string
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from anzeiger import bookmarks as bm
from anzeiger import i18n, pages
from anzeiger.layout import render_html
from anzeiger.settings import Settings


def placeholders(text) -> set[str]:
    parts = text if isinstance(text, list) else [text]
    return {name for part in parts for _, name, _, _ in string.Formatter().parse(part) if name}


class LanguageFilesTest(unittest.TestCase):
    """Die mitgelieferten Sprachdateien passen zur deutschen Referenz."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(i18n.set_language, i18n.SOURCE)
        self.config = Path(tmp.name) / "anzeiger"

    def test_builtin_languages(self):
        self.assertEqual(i18n.available(), {"de": "Deutsch", "en": "English", "eo": "Esperanto"})

    def test_same_keys_and_placeholders(self):
        reference = i18n.read(i18n.SOURCE, user=False)
        self.assertGreater(len(reference), 100)
        for code in ("en", "eo"):
            with self.subTest(code):
                texts = i18n.read(code, user=False)
                self.assertEqual(set(texts), set(reference))
                for key, text in reference.items():
                    self.assertEqual(type(texts[key]), type(text), key)
                    self.assertEqual(placeholders(texts[key]), placeholders(text), key)
        self.assertEqual(i18n.errors, [])

    def test_every_page_renders_in_every_language(self):
        ctx = pages.PageContext(bookmarks=bm.parse('<DL><DT><A HREF="https://a.de/">A</A></DL>'),
                                bookmarks_edit=True, cookies={"a.de": 1})
        for code in i18n.available():
            i18n.set_language(code)
            for url in pages.INTERNAL_PAGES:
                with self.subTest(code=code, url=url):
                    source = pages.internal_page(url, ctx)
                    self.assertNotRegex(source, r"\b(page|app|bookmarks)\.[a-z_]+\.[a-z_.]+\b")
                    render_html(source, url)

    def test_english_and_esperanto(self):
        i18n.set_language("en")
        self.assertEqual(render_html(pages.notes_page(), pages.NOTES_URL).title, "Notes")
        self.assertIn("1 cookie from 1 domain:", pages.config_page(pages.PageContext(cookies={"a.de": 1})))
        self.assertIn("only available in German", pages.changelog_page())
        self.assertEqual(i18n.keys("ctrl", "shift", "T"), "Ctrl+Shift+T")
        i18n.set_language("eo")
        self.assertEqual(i18n.tn("bookmarks.count", 1), "1 legosigno")
        self.assertEqual(i18n.tn("bookmarks.count", 0), "0 legosignoj")
        self.assertEqual(bm.folders(bm.Folder("")), [((), "Legosignoj")])
        i18n.set_language("de")
        self.assertEqual(i18n.keys("ctrl", "D"), "Strg+D")
        self.assertNotIn("nur auf Deutsch", pages.changelog_page())

    def test_user_file_overrides_and_adds_languages(self):
        folder = self.config / "lang"
        folder.mkdir(parents=True)
        (folder / "de.toml").write_text('[app]\ngo = "Öffnen"\n', encoding="utf-8")
        (folder / "fr.toml").write_text('[meta]\nname = "Français"\n[app]\ngo = "Aller"\n'
                                        'loading = "Chargement de {adresse} …"\n', encoding="utf-8")
        i18n.set_language("de")
        self.assertEqual(i18n.t("app.go"), "Öffnen")
        self.assertEqual(i18n.t("app.done"), "Fertig")
        self.assertEqual(i18n.available()["fr"], "Français")
        i18n.set_language("fr")
        self.assertEqual(i18n.t("app.go"), "Aller")
        self.assertEqual(i18n.t("app.done"), "Done")   # fehlt → Englisch
        # falscher Platzhalter: Text ohne Ersetzung statt Absturz
        self.assertEqual(i18n.t("app.loading", url="x"), "Chargement de {adresse} …")
        self.assertEqual(i18n.t("gibt.es.nicht"), "gibt.es.nicht")

    def test_broken_user_file_is_reported(self):
        folder = self.config / "lang"
        folder.mkdir(parents=True)
        (folder / "de.toml").write_text('[app\ngo = "kaputt"\n', encoding="utf-8")
        i18n.set_language("de")
        self.assertEqual(i18n.t("app.go"), "Los")
        self.assertEqual(len(i18n.errors), 1)
        self.assertIn("de.toml", pages.config_page())

    def test_system_language(self):
        for env, expected in (({"LANGUAGE": "eo:de", "LANG": "de_DE.UTF-8"}, "eo"),
                              ({"LANGUAGE": "", "LC_ALL": "", "LC_MESSAGES": "", "LANG": "en_GB.UTF-8"}, "en"),
                              ({"LANGUAGE": "", "LC_ALL": "", "LC_MESSAGES": "", "LANG": "de_AT.UTF-8"}, "de"),
                              ({"LANGUAGE": "", "LC_ALL": "C", "LANG": "de_DE.UTF-8"}, "en"),
                              ({"LANGUAGE": "ja_JP", "LANG": "de_DE.UTF-8"}, "en")):
            with self.subTest(env), mock.patch.dict(os.environ, env):
                self.assertEqual(i18n.system_language(), expected)

    def test_config_page_offers_languages(self):
        source = pages.config_page(pages.PageContext(Settings(language="eo")))
        self.assertIn('<option value="eo" selected>Esperanto</option>', source)
        self.assertIn('<option value="en">English</option>', source)
        self.assertIn('<option value="">Automatisch', source)


if __name__ == "__main__":
    unittest.main()
