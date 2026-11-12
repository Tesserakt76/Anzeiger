import unittest

from anzeiger.dom import parse_html
from anzeiger.layout import (FoldEndOp, FoldStartOp, ImageOp, MarkerOp, RuleOp, TextOp, list_number,
                             render_html)

URL = "http://example.org/dir/seite.html"


def plain(source: str, columns: int = 100) -> str:
    """Gibt die Seite als einfachen Text aus (Marker mit Einrückung)."""
    out = []
    for op in render_html(source, URL, columns).ops:
        if isinstance(op, TextOp):
            out.append(op.text)
        elif isinstance(op, MarkerOp):
            out.append("  " * (op.style.indent - 1) + op.text + " ")
        elif isinstance(op, ImageOp):
            out.append(f"[IMG {op.src}]")
        elif isinstance(op, RuleOp):
            out.append("----")
    return "".join(out)


class DomTest(unittest.TestCase):
    def test_implicit_close(self):
        root = parse_html("<ul><li>a<li>b</ul><p>x<p>y<div>z</div>")
        self.assertEqual([li.text() for li in root.iter("li")], ["a", "b"])
        self.assertEqual([p.text() for p in root.iter("p")], ["x", "y"])
        self.assertIsNone(root.find("p").find("div"))

    def test_table_cells(self):
        root = parse_html("<table><tr><td>1<td>2<tr><td>3</table>")
        self.assertEqual([len(list(tr.iter("td"))) for tr in root.iter("tr")], [2, 1])

    def test_stray_end_tag_inside_cell(self):
        root = parse_html("<div><table><tr><td>a</div>b</td></tr></table>c</div>")
        self.assertEqual(root.find("td").text(), "ab")


class LayoutTest(unittest.TestCase):
    def test_whitespace_and_paragraphs(self):
        self.assertEqual(plain("<p>  Hallo \n  Welt </p><p>Zwei</p>"), "Hallo Welt\n\nZwei")

    def test_inline_spacing(self):
        self.assertEqual(plain("ein <b>fettes</b> Wort"), "ein fettes Wort")

    def test_nested_lists(self):
        text = plain("<ol><li>eins<ul><li>a</li><li>b</li></ul></li><li>zwei</li></ol>")
        self.assertEqual(text, "1. eins\n  * a\n  * b\n2. zwei")

    def test_sublists_are_foldable(self):
        ops = render_html("<ul><li>a<ul><li>b<ul><li>c</ul></ul><li>d</ul>", URL).ops
        markers = [(op.text, op.fold) for op in ops if isinstance(op, MarkerOp)]
        self.assertEqual(markers, [("*", 0), ("*", 1), ("*", None), ("*", None)])
        kinds = [type(op).__name__ for op in ops if isinstance(op, (FoldStartOp, FoldEndOp))]
        self.assertEqual(kinds, ["FoldStartOp", "FoldStartOp", "FoldEndOp", "FoldEndOp"])
        # Der Zeilenumbruch vor der Unterliste gehört zum einklappbaren Bereich.
        start = next(i for i, op in enumerate(ops) if isinstance(op, FoldStartOp))
        self.assertTrue(ops[start + 1].text.startswith("\n"))

    def test_ordered_start_and_type(self):
        self.assertEqual(plain('<ol start="3" type="a"><li>x<li>y</ol>'), "c. x\nd. y")
        self.assertEqual(list_number(14, "I"), "XIV")

    def test_li_with_paragraph(self):
        self.assertEqual(plain("<ul><li><p>a</p></li><li>b</li></ul>"), "* a\n\n* b")

    def test_heading_style(self):
        ops = render_html("<h2>Titel</h2>", URL).ops
        self.assertEqual(ops[0].style.size, 18)
        self.assertTrue(ops[0].style.bold)

    def test_links_resolved(self):
        ops = render_html('<a href="../x.html">X</a>', URL).ops
        self.assertEqual(ops[0].style.href, "http://example.org/x.html")

    def test_javascript_link_ignored(self):
        ops = render_html('<a href="javascript:alert(1)">X</a>', URL).ops
        self.assertIsNone(ops[0].style.href)

    def test_scripts_and_styles_hidden(self):
        self.assertEqual(plain("<style>p{}</style><script>x=1</script><p>sichtbar"), "sichtbar")

    def test_pre_keeps_whitespace(self):
        self.assertEqual(plain("<pre>\n a  b\n  c</pre>"), " a  b\n  c")

    def test_br_and_hr(self):
        self.assertEqual(plain("a<br>b<hr>c"), "a\nb\n----\nc")

    def test_image(self):
        self.assertEqual(plain('<img src="b.png" alt="B">'), "[IMG http://example.org/dir/b.png]")

    def test_title(self):
        self.assertEqual(render_html("<title> Mein  Titel </title>", URL).title, "Mein Titel")

    def test_grid_table(self):
        text = plain("<table><tr><th>A</th><th>Bee</th></tr><tr><td>1</td><td>2</td></tr></table>")
        self.assertEqual(text.splitlines(), ["─── ─────", " A   Bee", "─── ─────", " 1   2", "─── ─────"])

    def test_colspan(self):
        text = plain("<table><tr><td colspan=2>breit</td></tr><tr><td>a</td><td>b</td></tr></table>")
        self.assertEqual(text.splitlines(), ["───────", " breit", "─── ───", " a   b", "─── ───"])

    def test_rowspan(self):
        text = plain("<table><tr><td rowspan=2>x</td><td>a</td></tr><tr><td>b</td></tr></table>")
        self.assertEqual(text.splitlines(), ["─── ───", " x   a", "    ───", "     b", "─── ───"])

    def test_table_wraps_to_columns(self):
        long = "wort " * 40
        text = plain(f"<table><tr><td>{long}</td><td>kurz</td></tr></table>", columns=40)
        self.assertTrue(all(len(line) <= 40 for line in text.splitlines()))

    def test_layout_table_is_linear(self):
        text = plain("<table><tr><td>a</td><td><table><tr><td>b</td></tr></table></td></tr></table>")
        self.assertNotIn("─", text)
        self.assertIn("a", text)
        self.assertIn("b", text)


if __name__ == "__main__":
    unittest.main()
