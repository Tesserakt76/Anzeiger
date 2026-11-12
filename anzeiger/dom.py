"""Fehlertoleranter Aufbau eines einfachen Dokumentbaums aus HTML.

Basiert auf html.parser aus der Standardbibliothek und ergänzt die
wichtigsten impliziten Regeln aus HTML (z.B. schließt ein neues <li> das
vorherige, ein <div> schließt ein offenes <p>).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

# Elemente, deren Beginn ein offenes <p> implizit beendet.
CLOSES_P = frozenset({
    "address", "article", "aside", "blockquote", "center", "details",
    "dialog", "dir", "div", "dl", "fieldset", "figcaption", "figure",
    "footer", "form", "header", "hgroup", "hr", "li", "main", "menu", "nav",
    "ol", "p", "pre", "section", "table", "ul", "dd", "dt",
}) | HEADINGS

# Über diese Elemente hinweg wird beim impliziten Schließen nicht gesucht.
SCOPE = frozenset({
    "table", "td", "th", "caption", "html", "body", "button", "object",
    "template", "#document",
})

LIST_SCOPE = SCOPE | {"ul", "ol", "menu", "dir"}
TABLE_SECTIONS = frozenset({"thead", "tbody", "tfoot"})


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    parent: Element | None = None
    children: list[Element | str] = field(default_factory=list)

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.attrs.get(name, default)

    def iter(self, tag: str | None = None) -> Iterator[Element]:
        """Alle Nachfahren (ohne sich selbst) in Dokumentreihenfolge."""
        for child in self.children:
            if isinstance(child, Element):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.iter(tag)

    def find(self, tag: str) -> Element | None:
        return next(self.iter(tag), None)

    def text(self) -> str:
        parts = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.text())
        return "".join(parts)

    def __repr__(self) -> str:
        return f"<{self.tag} {self.attrs!r} ({len(self.children)} Kinder)>"


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document")
        self.stack: list[Element] = [self.root]

    @property
    def current(self) -> Element:
        return self.stack[-1]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict: dict[str, str] = {}
        for name, value in attrs:
            attr_dict.setdefault(name, value if value is not None else "")
        self._implicit_close(tag)
        element = Element(tag, attr_dict, self.current)
        self.current.children.append(element)
        if tag not in VOID:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.current.tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            if tag == "br":  # </br> verhält sich wie <br>
                self.handle_starttag("br", [])
            return
        if tag in TABLE_SECTIONS or tag in ("table", "tr", "td", "th"):
            boundary = {"table"}
        else:
            boundary = {"table", "td", "th", "caption"}
        for i in range(len(self.stack) - 1, 0, -1):
            open_tag = self.stack[i].tag
            if open_tag == tag:
                del self.stack[i:]
                return
            if open_tag in boundary:
                return

    def handle_data(self, data: str) -> None:
        children = self.current.children
        if children and isinstance(children[-1], str):
            children[-1] += data
        else:
            children.append(data)

    def _close(self, tags: set[str] | frozenset[str], boundary: set[str] | frozenset[str]) -> None:
        """Schließt das oberste offene Element aus `tags`, sofern es vor `boundary` liegt."""
        for i in range(len(self.stack) - 1, 0, -1):
            open_tag = self.stack[i].tag
            if open_tag in tags:
                del self.stack[i:]
                return
            if open_tag in boundary:
                return

    def _implicit_close(self, tag: str) -> None:
        if tag in CLOSES_P:
            self._close({"p"}, SCOPE)
        if tag in HEADINGS and self.current.tag in HEADINGS:
            self.stack.pop()
        if tag == "li":
            self._close({"li"}, LIST_SCOPE)
        elif tag in ("dt", "dd"):
            self._close({"dt", "dd"}, SCOPE | {"dl"})
        elif tag == "tr":
            self._close({"tr"}, {"table"} | TABLE_SECTIONS)
        elif tag in ("td", "th"):
            self._close({"td", "th"}, {"tr", "table"})
        elif tag in TABLE_SECTIONS:
            self._close(TABLE_SECTIONS, {"table"})
        elif tag == "option":
            self._close({"option"}, {"select", "datalist", "optgroup"})
        elif tag == "optgroup":
            self._close({"optgroup", "option"}, {"select"})


def parse_html(source: str) -> Element:
    """Parst HTML-Quelltext und liefert den Wurzelknoten (#document)."""
    builder = _TreeBuilder()
    builder.feed(source)
    builder.close()
    return builder.root
