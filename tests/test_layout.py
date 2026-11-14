import unittest

from anzeiger.dom import parse_html
from anzeiger.layout import (FieldOp, FoldEndOp, FoldStartOp, ImageOp, ListToggleOp, MarkerOp, RuleOp,
                             TextOp, hidden_by_style, list_number, render_html)

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


class FormLayoutTest(unittest.TestCase):
    def test_form_and_fields(self):
        page = render_html(
            '<form action="suche" method="POST" enctype="multipart/form-data">'
            '<input type="hidden" name="t" value="1"><input name="q" size="80">'
            '<input type="checkbox" name="c" checked><select name="s"><option>A'
            '<option value="b" selected>B</select><textarea name="x">\nZeile</textarea>'
            '<button>Los</button></form><input name="frei">', URL)
        self.assertEqual(len(page.forms), 1)
        form = page.forms[0]
        self.assertEqual((form.action, form.method, form.enctype),
                         ("http://example.org/dir/suche", "post", "multipart/form-data"))
        fields = [op for op in page.ops if isinstance(op, FieldOp)]
        self.assertEqual([(f.kind, f.name, f.form) for f in fields],
                         [("hidden", "t", 0), ("text", "q", 0), ("checkbox", "c", 0), ("select", "s", 0),
                          ("textarea", "x", 0), ("submit", "", 0), ("text", "frei", None)])
        self.assertEqual(fields[1].size, 60)
        self.assertTrue(fields[2].checked)
        self.assertEqual([(o.value, o.selected) for o in fields[3].options], [("A", False), ("b", True)])
        self.assertEqual(fields[4].value, "Zeile")
        self.assertEqual(fields[5].label, "Los")

    def test_empty_action_is_page_url_and_form_attribute(self):
        page = render_html('<base href="http://cdn.example.org/"><form id="f"></form>'
                           '<input name="a" form="f"><button type="reset">R</button>', URL)
        self.assertEqual(page.forms[0].action, URL)
        fields = [op for op in page.ops if isinstance(op, FieldOp)]
        self.assertEqual([(f.kind, f.form) for f in fields], [("text", 0), ("reset", None)])

    def test_table_with_controls_is_linear(self):
        page = render_html('<form><table><tr><td>Name<td><input name="n"></table></form>', URL)
        self.assertTrue(any(isinstance(op, FieldOp) for op in page.ops))
        self.assertFalse(any(isinstance(op, TextOp) and "\u2500" in op.text for op in page.ops))


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
        # Fold 0 ist die ganze Liste, 1 und 2 sind Unterlisten.
        self.assertEqual(markers, [("*", 1), ("*", 2), ("*", None), ("*", None)])
        folds = [(type(op).__name__, op.fold, getattr(op, "kind", None)) for op in ops
                 if isinstance(op, (FoldStartOp, FoldEndOp))]
        self.assertEqual(folds, [("FoldStartOp", 0, "list"), ("FoldStartOp", 1, "sublist"),
                                 ("FoldStartOp", 2, "sublist"), ("FoldEndOp", 2, None),
                                 ("FoldEndOp", 1, None), ("FoldEndOp", 0, None)])
        # Der Zeilenumbruch vor der Unterliste gehört zum einklappbaren Bereich.
        start = next(i for i, op in enumerate(ops) if isinstance(op, FoldStartOp) and op.kind == "sublist")
        self.assertTrue(ops[start + 1].text.startswith("\n"))

    def test_whole_list_has_toggle_line(self):
        ops = render_html("<p>x</p><ol><li>a<li>b<li hidden>c</ol>", URL).ops
        toggles = [op for op in ops if isinstance(op, ListToggleOp)]
        self.assertEqual([(t.fold, t.label) for t in toggles], [(0, "Liste (2 Einträge)")])
        index = ops.index(toggles[0])
        self.assertIsInstance(ops[index + 1], FoldStartOp)
        self.assertEqual(plain("<p>x</p><ul><li>a</ul>"), "x\n\n* a")

    def test_lists_in_grid_cells_not_foldable(self):
        ops = render_html("<table><tr><td><ul><li>a<ul><li>b</ul></ul><td>z</table>", URL).ops
        self.assertFalse(any(isinstance(op, (ListToggleOp, FoldStartOp)) for op in ops))

    def hidden_toggles(self, source: str) -> list[tuple[str, bool]]:
        ops = render_html(source, URL, fold_hidden=True).ops
        return [(op.label, op.inline) for op in ops if isinstance(op, ListToggleOp) and op.kind == "hidden"]

    def test_hidden_by_style(self):
        el = lambda style: parse_html(f'<span style="{style}">x</span>').find("span")
        self.assertTrue(hidden_by_style(el("display:none")))
        self.assertTrue(hidden_by_style(el("color:red; DISPLAY : None !important")))
        self.assertTrue(hidden_by_style(el("visibility: hidden")))
        self.assertFalse(hidden_by_style(el("display:none; display:block")))   # letzte Angabe gilt
        self.assertFalse(hidden_by_style(el("display:block")))
        self.assertFalse(hidden_by_style(el("")))

    def test_hidden_content_folded(self):
        source = '<p>A <span style="display:none">geheim</span> B</p><div style="visibility:hidden"><p>Block</p></div>'
        self.assertEqual(self.hidden_toggles(source), [("Verborgen: geheim", True), ("Verborgen: Block", False)])
        ops = render_html(source, URL, fold_hidden=True).ops
        folds = [(op.fold, op.kind) for op in ops if isinstance(op, FoldStartOp)]
        self.assertEqual(folds, [(0, "hidden"), (1, "hidden")])
        start = ops.index(next(op for op in ops if isinstance(op, FoldStartOp)))
        self.assertEqual(ops[start + 1].text.strip(), "geheim")
        self.assertIsInstance(ops[start + 2], FoldEndOp)
        # Ohne die Einstellung bleibt alles wie bisher.
        self.assertEqual(plain(source), "A geheim B\n\nBlock")

    def test_hidden_fields_items_and_previews(self):
        long = "Wort " * 20
        self.assertEqual(self.hidden_toggles(f'<form><input name="hp" style="display:none"></form>'
                                             f'<ul><li>a<li style="display:none">{long}</ul>'),
                         [("Verborgen", True), ("Verborgen: " + ("Wort " * 10).strip() + " …", False)])
        # Nichts Sichtbares darin oder schon innerhalb eines verborgenen Bereichs: kein Schalter.
        self.assertEqual(self.hidden_toggles('<div style="display:none"><script>x()</script> '
                                             '<input type="hidden" name="t"></div>'), [])
        self.assertEqual(len(self.hidden_toggles('<div style="display:none">a<p style="display:none">b</p></div>')), 1)
        # In Tabellenzellen (Raster) lässt sich nichts einklappen.
        self.assertEqual(self.hidden_toggles('<table><tr><td><span style="display:none">x</span><td>y</table>'), [])

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

    def test_grid_table_links_images_from_same_server(self):
        page = render_html('<table><tr><td><img src="bild.png" alt="Foto"><td><img src="/b.png">'
                           '<td><img src="https://fremd.de/c.png"><td><a href="/ziel"><img src="d.png"></a>'
                           '</table>', URL)
        runs = {op.text: op.style for op in page.ops if isinstance(op, TextOp) and op.text.startswith("[")}
        self.assertEqual(runs["[Foto]"].href, "http://example.org/dir/bild.png")
        self.assertFalse(runs["[Foto]"].dim)
        self.assertFalse(any(isinstance(op, ImageOp) for op in page.ops))   # Raster bleibt Text
        styles = [op.style for op in page.ops if isinstance(op, TextOp) and op.text == "[Bild]"]
        self.assertEqual([s.href for s in styles], ["http://example.org/b.png", None, "http://example.org/ziel"])
        self.assertEqual([s.dim for s in styles], [False, True, True])

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
