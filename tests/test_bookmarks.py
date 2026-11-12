import tempfile
import unittest
from pathlib import Path

from anzeiger import bookmarks as bm
from anzeiger import pages
from anzeiger.layout import render_html

# So exportiert Firefox (gekürzt): Beschreibungen in <DD>, Trennlinien, Symbolleisten-Ordner.
FIREFOX = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'none'">
<TITLE>Bookmarks</TITLE>
<H1>Lesezeichen-Menü</H1>

<DL><p>
    <DT><A HREF="https://www.mozilla.org/" ADD_DATE="1700000000" LAST_MODIFIED="1700000001" ICON_URI="https://www.mozilla.org/favicon.ico" TAGS="browser,mozilla">Mozilla &amp; Co</A>
    <DD>Eine Beschreibung
    <HR>
    <DT><H3 ADD_DATE="1700000000" LAST_MODIFIED="1700000002" PERSONAL_TOOLBAR_FOLDER="true">Lesezeichen-Symbolleiste</H3>
    <DL><p>
        <DT><A HREF="https://a.de/?x=1&amp;y=2" ADD_DATE="1700000003">Ä &lt;A&gt;</A>
        <DT><H3>Unterordner</H3>
        <DL><p>
            <DT><A HREF="https://b.de/">B</A>
        </DL><p>
    </DL><p>
</DL>
"""

# So exportiert Chrome: Ordner der Lesezeichenleiste an erster Stelle, keine <DD>.
CHROME = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3 ADD_DATE="1700000000" LAST_MODIFIED="1700000000" PERSONAL_TOOLBAR_FOLDER="true">Lesezeichenleiste</H3>
    <DL><p>
        <DT><A HREF="https://c.de/" ADD_DATE="1700000000" ICON="data:image/png;base64,AAAA">C</A>
    </DL><p>
    <DT><A HREF="https://d.de/" ADD_DATE="1700000000">D</A>
</DL><p>
"""


def summary(folder: bm.Folder) -> list:
    out = []
    for path, node in folder.walk():
        if isinstance(node, bm.Bookmark):
            out.append((path, "A", node.title, node.url))
        elif isinstance(node, bm.Folder):
            out.append((path, "H3", node.title))
        else:
            out.append((path, "HR"))
    return out


class ParseTest(unittest.TestCase):
    def test_firefox(self):
        root = bm.parse(FIREFOX)
        self.assertEqual(summary(root), [
            ((0,), "A", "Mozilla & Co", "https://www.mozilla.org/"),
            ((1,), "HR"),
            ((2,), "H3", "Lesezeichen-Symbolleiste"),
            ((2, 0), "A", "Ä <A>", "https://a.de/?x=1&y=2"),
            ((2, 1), "H3", "Unterordner"),
            ((2, 1, 0), "A", "B", "https://b.de/"),
        ])
        first = root.children[0]
        self.assertEqual(first.description, "Eine Beschreibung")
        self.assertEqual(first.attrs["TAGS"], "browser,mozilla")
        self.assertEqual(root.children[2].attrs["PERSONAL_TOOLBAR_FOLDER"], "true")

    def test_chrome(self):
        root = bm.parse(CHROME)
        self.assertEqual(summary(root), [
            ((0,), "H3", "Lesezeichenleiste"),
            ((0, 0), "A", "C", "https://c.de/"),
            ((1,), "A", "D", "https://d.de/"),
        ])
        self.assertEqual(root.children[0].children[0].attrs["ICON"], "data:image/png;base64,AAAA")

    def test_roundtrip_keeps_everything(self):
        for source in (FIREFOX, CHROME):
            root = bm.parse(source)
            written = bm.serialize(root)
            self.assertTrue(written.startswith("<!DOCTYPE NETSCAPE-Bookmark-file-1>"))
            again = bm.parse(written)
            self.assertEqual(summary(again), summary(root))
            self.assertEqual(bm.serialize(again), written)

    def test_escaping(self):
        root = bm.Folder("x", [bm.Bookmark('a "b" <c> & d', 'https://e.de/?a=1&b="2"')])
        written = bm.serialize(root)
        self.assertIn('HREF="https://e.de/?a=1&amp;b=&quot;2&quot;"', written)
        self.assertIn(">a \"b\" &lt;c&gt; &amp; d</A>", written)
        self.assertEqual(summary(bm.parse(written)), summary(root))

    def test_paths(self):
        self.assertEqual(bm.parse_path("2.1.0"), (2, 1, 0))
        self.assertIsNone(bm.parse_path("2.x"))
        self.assertIsNone(bm.parse_path(""))
        self.assertEqual(bm.format_path((2, 1, 0)), "2.1.0")


class FileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "bookmarks.html"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_empty(self):
        self.assertEqual(bm.load(self.path).children, [])

    def test_add_remove(self):
        self.assertTrue(bm.add(self.path, "https://a.de/", "A"))
        self.assertFalse(bm.add(self.path, "https://a.de/", "A doppelt"))
        self.assertTrue(bm.add(self.path, "https://b.de/", "  "))
        root = bm.load(self.path)
        self.assertEqual([(b.title, b.url) for _, b in root.walk()],
                         [("A", "https://a.de/"), ("https://b.de/", "https://b.de/")])
        self.assertIn("ADD_DATE", root.children[0].attrs)
        self.assertTrue(bm.remove_url(self.path, "https://a.de/"))
        self.assertFalse(bm.remove_url(self.path, "https://a.de/"))
        self.assertEqual(bm.load(self.path).count(), 1)

    def test_edit_in_existing_browser_file(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(FIREFOX, encoding="utf-8")
        self.assertFalse(bm.rename_at(self.path, (2, 0), "https://falsch.de/", "X"))
        self.assertTrue(bm.rename_at(self.path, (2, 0), "https://a.de/?x=1&y=2", "  Neuer   Name "))
        self.assertTrue(bm.remove_at(self.path, (2, 1, 0), "https://b.de/"))
        self.assertFalse(bm.remove_at(self.path, (1,), ""))   # Trennlinie ist kein Lesezeichen
        root = bm.load(self.path)
        self.assertEqual(root.node((2, 0)).title, "Neuer Name")
        self.assertEqual(root.node((2, 1)).children, [])
        self.assertEqual(root.children[0].attrs["ICON_URI"], "https://www.mozilla.org/favicon.ico")


class PageTest(unittest.TestCase):
    def test_bookmarks_page(self):
        ctx = pages.PageContext(bookmarks=bm.parse(FIREFOX), bookmarks_path=Path("/x/bookmarks.html"))
        page = render_html(pages.internal_page(pages.BOOKMARKS_URL, ctx), pages.BOOKMARKS_URL)
        self.assertEqual(page.title, "Lesezeichen")
        links = {op.style.href for op in page.ops if getattr(op, "style", None) and op.style.href}
        self.assertTrue({"https://www.mozilla.org/", "https://a.de/?x=1&y=2", "https://b.de/"} <= links)
        self.assertEqual(page.forms[0].action, pages.BOOKMARKS_URL)   # Knopf „Bearbeiten“
        self.assertEqual(len(page.forms), 1)

    def test_edit_mode_has_form_per_bookmark(self):
        ctx = pages.PageContext(bookmarks=bm.parse(FIREFOX), bookmarks_edit=True)
        page = render_html(pages.internal_page(pages.BOOKMARKS_URL, ctx), pages.BOOKMARKS_URL)
        self.assertEqual(len(page.forms), 1 + 3)
        self.assertEqual(page.forms[1].id, "b0")

    def test_empty_and_start_page(self):
        source = pages.internal_page(pages.BOOKMARKS_URL, pages.PageContext())
        self.assertIn("Noch keine Lesezeichen", source)
        self.assertIn(pages.BOOKMARKS_URL, pages.START_PAGE)
        self.assertTrue(pages.is_internal("about:bookmarks"))


if __name__ == "__main__":
    unittest.main()
