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


class FolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "bookmarks.html"
        self.path.write_text(FIREFOX, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_folders_list(self):
        self.assertEqual(bm.folders(bm.parse(FIREFOX)), [
            ((), "Lesezeichen"),
            ((2,), "Lesezeichen-Symbolleiste"),
            ((2, 1), "Lesezeichen-Symbolleiste › Unterordner"),
        ])
        self.assertEqual(bm.parse_folder(""), ())
        self.assertEqual(bm.parse_folder("2.1"), (2, 1))

    def test_add_folder_and_nest(self):
        self.assertTrue(bm.add_folder(self.path, (), "  Neu  "))
        self.assertTrue(bm.add_folder(self.path, (3,), "Darin"))
        self.assertFalse(bm.add_folder(self.path, (0,), "Lesezeichen ist kein Ordner"))
        self.assertFalse(bm.add_folder(self.path, (), " "))
        root = bm.load(self.path)
        self.assertEqual(root.node((3,)).title, "Neu")
        self.assertEqual(root.node((3, 0)).title, "Darin")
        self.assertIn("ADD_DATE", root.node((3,)).attrs)

    def test_move_bookmark_and_folder(self):
        bm.add_folder(self.path, (), "Ziel")                       # (3,)
        self.assertTrue(bm.move_at(self.path, (0,), "https://www.mozilla.org/", (2, 1)))
        root = bm.load(self.path)
        # Durch das Verschieben rückt alles eine Stelle nach vorn.
        self.assertEqual(root.node((1, 1, 1)).url, "https://www.mozilla.org/")
        self.assertEqual(root.node((1, 1, 1)).description, "Eine Beschreibung")
        self.assertTrue(bm.move_at(self.path, (1, 1), "Unterordner", (2,)))
        root = bm.load(self.path)
        self.assertEqual(summary(root.node((2,))), [
            ((0,), "H3", "Unterordner"),
            ((0, 0), "A", "B", "https://b.de/"),
            ((0, 1), "A", "Mozilla & Co", "https://www.mozilla.org/"),
        ])

    def test_move_rejects_bad_targets(self):
        with self.assertRaises(ValueError):
            bm.move_at(self.path, (2,), "Lesezeichen-Symbolleiste", (2, 1))
        with self.assertRaises(ValueError):
            bm.move_at(self.path, (2,), "Lesezeichen-Symbolleiste", (0,))   # kein Ordner
        self.assertFalse(bm.move_at(self.path, (2,), "Anderer Name", ()))
        self.assertEqual(bm.serialize(bm.load(self.path)), bm.serialize(bm.parse(FIREFOX)))

    def test_rename_and_remove_folder(self):
        self.assertTrue(bm.rename_at(self.path, (2, 1), "Unterordner", "Umbenannt"))
        self.assertFalse(bm.remove_at(self.path, (2, 1), "Unterordner"))
        self.assertTrue(bm.remove_at(self.path, (2, 1), "Umbenannt"))
        self.assertEqual(bm.load(self.path).count(), 2)


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
        # Fertig, Neuer Ordner, dann je ein Formular für 3 Lesezeichen und 2 Ordner
        self.assertEqual(len(page.forms), 2 + 5)
        self.assertEqual(page.forms[1].id, "new-folder")
        self.assertEqual(page.forms[2].id, "b0")
        self.assertEqual([f.id for f in page.forms[2:]], ["b0", "b2", "b2.0", "b2.1", "b2.1.0"])
        # Ordner 2 kann nicht in sich selbst oder seinen Unterordner 2.1 verschoben werden
        moves = [op for op in page.ops if getattr(op, "kind", None) == "select" and op.form == 3]
        self.assertEqual([o.value for o in moves[0].options], [""])
        self.assertTrue(moves[0].options[0].selected)

    def test_empty_and_start_page(self):
        source = pages.internal_page(pages.BOOKMARKS_URL, pages.PageContext())
        self.assertIn("Noch keine Lesezeichen", source)
        self.assertIn(pages.BOOKMARKS_URL, pages.start_page())
        self.assertTrue(pages.is_internal("about:bookmarks"))


if __name__ == "__main__":
    unittest.main()
