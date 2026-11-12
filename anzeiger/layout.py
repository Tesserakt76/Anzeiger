"""Übersetzt den Dokumentbaum in eine flache Folge von Darstellungsanweisungen.

Die Anweisungen (TextOp, MarkerOp, ImageOp, RuleOp, AnchorOp) sind
unabhängig von tkinter, damit sich das Layout ohne Fenster testen lässt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from urllib.parse import urljoin

from .dom import Element, parse_html

BASE_SIZE = 11
HEADING_SIZES = {"h1": 22, "h2": 18, "h3": 15, "h4": 13, "h5": 11, "h6": 10}

# Elemente, deren Inhalt nie angezeigt wird.
SKIP = frozenset({
    "head", "script", "style", "template", "object", "embed", "svg", "math",
    "canvas", "video", "audio", "map", "datalist", "noembed", "frameset",
    "frame", "param", "source", "track", "link", "meta", "base", "title",
    "dialog",
})

INLINE = {
    "b": {"bold": True}, "strong": {"bold": True},
    "i": {"italic": True}, "em": {"italic": True}, "cite": {"italic": True},
    "var": {"italic": True}, "dfn": {"italic": True}, "address": {"italic": True},
    "u": {"underline": True}, "ins": {"underline": True},
    "s": {"strike": True}, "strike": {"strike": True}, "del": {"strike": True},
    "code": {"mono": True}, "kbd": {"mono": True}, "samp": {"mono": True},
    "tt": {"mono": True},
    "mark": {"mark": True},
}

# Blockelemente mit der Anzahl Zeilenumbrüche davor und danach
# (1 = neue Zeile, 2 = Leerzeile).
BLOCK = {
    "p": 2, "blockquote": 2, "figure": 2, "fieldset": 2, "dl": 2,
    "div": 1, "section": 1, "article": 1, "aside": 1, "header": 1,
    "footer": 1, "nav": 1, "main": 1, "hgroup": 1, "address": 1,
    "center": 1, "details": 1, "summary": 1, "figcaption": 1, "form": 1,
    "legend": 1, "dt": 1, "dd": 1, "caption": 1, "body": 1, "html": 1,
    "search": 1, "noscript": 1, "label": 0, "optgroup": 1,
}

_WS = re.compile(r"[ \t\n\r\f]+")
_TOKENS = re.compile(r"\s+|\S+")


@dataclass(frozen=True)
class Style:
    size: int = BASE_SIZE
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    mono: bool = False
    mark: bool = False
    dim: bool = False
    href: str | None = None
    info: str | None = None       # Hinweistext beim Überfahren mit der Maus
    indent: int = 0               # Einrückungsstufe
    align: str = "left"
    pre: bool = False             # Leerraum erhalten
    nowrap: bool = False
    offset: int = 0               # >0 hochgestellt, <0 tiefgestellt


PLAIN = Style()


@dataclass
class TextOp:
    text: str
    style: Style


@dataclass
class MarkerOp:
    """Aufzählungszeichen bzw. Nummer eines Listeneintrags (hängender Einzug).

    `fold` ist gesetzt, wenn der Eintrag Unterlisten hat, die sich einklappen lassen.
    """
    text: str
    style: Style
    fold: int | None = None


@dataclass
class ImageOp:
    src: str | None
    alt: str
    width: int | None
    height: int | None
    style: Style


@dataclass
class RuleOp:
    style: Style


@dataclass
class AnchorOp:
    name: str


@dataclass
class FoldStartOp:
    """Beginn eines einklappbaren Bereichs (Unterliste) des Listeneintrags `fold`."""
    fold: int


@dataclass
class FoldEndOp:
    fold: int


Op = TextOp | MarkerOp | ImageOp | RuleOp | AnchorOp | FoldStartOp | FoldEndOp


@dataclass
class Page:
    url: str
    title: str = ""
    ops: list[Op] = field(default_factory=list)


def render_html(source: str, url: str, columns: int = 100) -> Page:
    """Parst und layoutet eine HTML-Seite. `columns` begrenzt die Tabellenbreite."""
    root = parse_html(source)
    base = url
    base_el = next((e for e in root.iter("base") if e.get("href")), None)
    if base_el is not None:
        base = urljoin(url, base_el.get("href", "").strip())
    renderer = Renderer(base, columns)
    title_el = root.find("title")
    title = _WS.sub(" ", title_el.text()).strip() if title_el is not None else ""

    refresh = _meta_refresh(root, base)
    if refresh:
        renderer.inline("Weiterleitung zu: ", replace(PLAIN, dim=True))
        renderer.inline(refresh, replace(PLAIN, href=refresh))
        renderer.block_break(2)

    renderer.node(root, PLAIN)
    renderer.finish()
    return Page(url, title, renderer.ops)


def render_text(source: str, url: str) -> Page:
    """Stellt reinen Text (text/plain) unverändert in Festbreitenschrift dar."""
    renderer = Renderer(url)
    renderer.text(source, Style(mono=True, pre=True))
    renderer.finish()
    return Page(url, url.rsplit("/", 1)[-1], renderer.ops)


def _meta_refresh(root: Element, base: str) -> str | None:
    for meta in root.iter("meta"):
        if (meta.get("http-equiv") or "").lower() == "refresh":
            match = re.search(r"url\s*=\s*['\"]?([^'\"]+)", meta.get("content") or "", re.I)
            if match:
                return urljoin(base, match.group(1).strip())
    return None


def _int_attr(el: Element, name: str) -> int | None:
    match = re.match(r"\s*(\d+)", el.get(name) or "")
    return int(match.group(1)) if match else None


def _roman(n: int) -> str:
    if not 0 < n < 4000:
        return str(n)
    result = []
    for value, letters in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
                           (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                           (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= value:
            result.append(letters)
            n -= value
    return "".join(result)


def _alpha(n: int) -> str:
    if n <= 0:
        return str(n)
    letters = ""
    while n > 0:
        n, rest = divmod(n - 1, 26)
        letters = chr(ord("a") + rest) + letters
    return letters


def list_number(n: int, kind: str) -> str:
    if kind == "a":
        return _alpha(n)
    if kind == "A":
        return _alpha(n).upper()
    if kind == "i":
        return _roman(n)
    if kind == "I":
        return _roman(n).upper()
    return str(n)


class Renderer:
    def __init__(self, base_url: str, columns: int = 100) -> None:
        self.base_url = base_url
        self.columns = columns
        self.ops: list[Op] = []
        self.pending_break = 0
        self.trailing_nl = 2          # am Dokumentanfang keine Leerzeilen erzeugen
        self.pending_space = False
        self.pending_marker: tuple[str, Style, int | None] | None = None
        self.after_marker = False
        self.pending_anchors: list[str] = []
        self.list_depth = 0
        self.folds = 0
        self.li_folds: list[int | None] = []   # Fold-Nummer je offenem <li>

    # -- Grundoperationen ---------------------------------------------------

    def _emit(self, text: str, style: Style) -> None:
        if not text:
            return
        last = self.ops[-1] if self.ops else None
        if isinstance(last, TextOp) and last.style == style:
            last.text += text
        else:
            self.ops.append(TextOp(text, style))
        stripped = text.rstrip("\n")
        newlines = len(text) - len(stripped)
        self.trailing_nl = self.trailing_nl + newlines if not stripped else newlines

    def block_break(self, n: int) -> None:
        """Fordert vor dem nächsten Inhalt n Zeilenumbrüche an (1 = neue Zeile, 2 = Leerzeile)."""
        if self.pending_marker:
            self._flush()
        if self.after_marker:
            return
        self.pending_break = max(self.pending_break, n)
        self.pending_space = False

    def _flush(self) -> None:
        """Schreibt angeforderte Umbrüche, Anker und Listenmarker aus."""
        if self.pending_break:
            missing = self.pending_break - self.trailing_nl
            if missing > 0:
                self._emit("\n" * missing, PLAIN)
            self.pending_break = 0
            self.pending_space = False
        for name in self.pending_anchors:
            self.ops.append(AnchorOp(name))
        self.pending_anchors.clear()
        if self.pending_marker:
            text, style, fold = self.pending_marker
            self.pending_marker = None
            self.ops.append(MarkerOp(text, style, fold))
            self.trailing_nl = 0
            self.after_marker = True
            self.pending_space = False

    def _space(self) -> None:
        if self.pending_space and self.trailing_nl == 0 and not self.after_marker:
            self._emit(" ", PLAIN)
        self.pending_space = False

    def inline(self, text: str, style: Style) -> None:
        """Gibt fertigen (bereits zusammengefassten) Fließtext aus."""
        if not text:
            return
        self._flush()
        self._space()
        self._emit(text, style)
        self.after_marker = False

    def text(self, text: str, style: Style) -> None:
        if style.pre:
            self._flush()
            self._space()
            self._emit(text.replace("\r\n", "\n").expandtabs(8), style)
            self.after_marker = False
            return
        collapsed = _WS.sub(" ", text)
        if not collapsed:
            return
        core = collapsed.strip(" ")
        if collapsed.startswith(" "):
            self.pending_space = True
        self.inline(core, style)
        if core and collapsed.endswith(" "):
            self.pending_space = True

    def line_break(self) -> None:
        self._flush()
        self._emit("\n", PLAIN)
        self.pending_space = False
        self.after_marker = False

    def finish(self) -> None:
        self.pending_break = 0
        self._flush()

    # -- Baumdurchlauf --------------------------------------------------------

    def node(self, node: Element | str, style: Style) -> None:
        if isinstance(node, str):
            self.text(node, style)
        else:
            self.element(node, style)

    def children(self, el: Element, style: Style) -> None:
        for child in el.children:
            self.node(child, style)

    def element(self, el: Element, style: Style) -> None:
        tag = el.tag
        if tag in SKIP or "hidden" in el.attrs:
            return
        anchor = el.get("id")
        if anchor:
            self.pending_anchors.append(anchor)
        handler = getattr(self, "_tag_" + tag, None) if tag.isalnum() else None
        if handler is not None:
            handler(el, style)
        elif tag in INLINE:
            self.children(el, replace(style, **INLINE[tag]))
        elif tag in BLOCK:
            self._block(el, style, BLOCK[tag])
        else:
            self.children(el, style)

    def _aligned(self, el: Element, style: Style) -> Style:
        align = (el.get("align") or "").lower()
        if el.tag == "center":
            align = "center"
        if align in ("left", "center", "right"):
            return replace(style, align=align)
        return style

    def _block(self, el: Element, style: Style, margin: int) -> None:
        style = self._aligned(el, style)
        if el.tag == "dd":
            style = replace(style, indent=style.indent + 1)
        self.block_break(margin)
        self.children(el, style)
        self.block_break(margin)

    # -- Einzelne Elemente ----------------------------------------------------

    def _heading(self, el: Element, style: Style) -> None:
        style = replace(self._aligned(el, style), size=HEADING_SIZES[el.tag], bold=True)
        self.block_break(2)
        self.children(el, style)
        self.block_break(2)

    _tag_h1 = _tag_h2 = _tag_h3 = _tag_h4 = _tag_h5 = _tag_h6 = _heading

    def _tag_br(self, el: Element, style: Style) -> None:
        self.line_break()

    def _tag_wbr(self, el: Element, style: Style) -> None:
        pass

    def _tag_hr(self, el: Element, style: Style) -> None:
        self.block_break(1)
        self._flush()
        self.ops.append(RuleOp(style))
        self._emit("\n", PLAIN)
        self.after_marker = False
        self.block_break(1)

    def _tag_blockquote(self, el: Element, style: Style) -> None:
        self.block_break(2)
        self.children(el, replace(style, indent=style.indent + 1))
        self.block_break(2)

    def _tag_pre(self, el: Element, style: Style) -> None:
        style = replace(style, pre=True, mono=True, nowrap=True)
        self.block_break(2)
        children = list(el.children)
        if children and isinstance(children[0], str):
            first = children[0]
            if first.startswith("\r\n"):
                first = first[2:]
            elif first.startswith("\n"):
                first = first[1:]
            children[0] = first
        for child in children:
            self.node(child, style)
        self.block_break(2)

    _tag_listing = _tag_xmp = _tag_plaintext = _tag_pre

    def _tag_small(self, el: Element, style: Style) -> None:
        self.children(el, replace(style, size=max(7, style.size - 2)))

    def _tag_big(self, el: Element, style: Style) -> None:
        self.children(el, replace(style, size=style.size + 2))

    def _tag_sup(self, el: Element, style: Style) -> None:
        self.children(el, replace(style, size=max(7, style.size - 2), offset=4))

    def _tag_sub(self, el: Element, style: Style) -> None:
        self.children(el, replace(style, size=max(7, style.size - 2), offset=-3))

    def _tag_q(self, el: Element, style: Style) -> None:
        self.inline("“", style)
        self.children(el, style)
        self.inline("”", style)

    def _tag_abbr(self, el: Element, style: Style) -> None:
        title = el.get("title")
        self.children(el, replace(style, info=title) if title else style)

    _tag_acronym = _tag_abbr

    def _tag_a(self, el: Element, style: Style) -> None:
        name = el.get("name")
        if name:
            self.pending_anchors.append(name)
        href = (el.get("href") or "").strip()
        if href and not href.lower().startswith("javascript:"):
            style = replace(style, href=urljoin(self.base_url, href))
        self.children(el, style)

    def _tag_img(self, el: Element, style: Style) -> None:
        src = (el.get("src") or "").strip()
        if not src or src.startswith("data:"):
            src = (el.get("data-src") or src).strip()
        src_url = urljoin(self.base_url, src) if src else None
        self._flush()
        self._space()
        self.ops.append(ImageOp(src_url, (el.get("alt") or "").strip(),
                                _int_attr(el, "width"), _int_attr(el, "height"), style))
        self.trailing_nl = 0
        self.after_marker = False

    def _tag_iframe(self, el: Element, style: Style) -> None:
        src = (el.get("src") or "").strip()
        if src:
            url = urljoin(self.base_url, src)
            self.inline(f"[Rahmen: {url}]", replace(style, href=url))

    # -- Formulare (nur Anzeige) ---------------------------------------------

    def _tag_input(self, el: Element, style: Style) -> None:
        kind = (el.get("type") or "text").lower()
        value = el.get("value") or ""
        field_style = replace(style, mono=True, dim=True)
        if kind == "hidden":
            return
        if kind in ("submit", "reset", "button"):
            label = value or {"submit": "Absenden", "reset": "Zurücksetzen"}.get(kind, "")
            self.inline(f"[{label}]", field_style)
        elif kind == "checkbox":
            self.inline("[x]" if "checked" in el.attrs else "[ ]", field_style)
        elif kind == "radio":
            self.inline("(•)" if "checked" in el.attrs else "( )", field_style)
        elif kind == "image":
            self.inline(f"[{el.get('alt') or 'Bild-Knopf'}]", field_style)
        else:
            width = min(_int_attr(el, "size") or 20, 40)
            shown = value or el.get("placeholder") or ""
            self.inline("[" + shown[:width].ljust(width, "_") + "]", field_style)

    def _tag_button(self, el: Element, style: Style) -> None:
        field_style = replace(style, dim=True)
        self.inline("[", field_style)
        self.children(el, style)
        self.inline("]", field_style)

    def _tag_select(self, el: Element, style: Style) -> None:
        options = list(el.iter("option"))
        chosen = next((o for o in options if "selected" in o.attrs), options[0] if options else None)
        label = _WS.sub(" ", chosen.text()).strip() if chosen is not None else ""
        self.inline(f"[{label} ▾]", replace(style, mono=True, dim=True))

    def _tag_textarea(self, el: Element, style: Style) -> None:
        content = el.text().strip("\n")
        self.block_break(1)
        self.text("[" + content + "]", replace(style, mono=True, dim=True, pre=True))
        self.block_break(1)

    # -- Listen ---------------------------------------------------------------

    def _tag_ul(self, el: Element, style: Style) -> None:
        self._list(el, style, ordered=False)

    _tag_menu = _tag_dir = _tag_ul

    def _tag_ol(self, el: Element, style: Style) -> None:
        self._list(el, style, ordered=True)

    def _list(self, el: Element, style: Style, ordered: bool) -> None:
        margin = 1 if self.list_depth else 2
        self.block_break(margin)
        # Unterliste eines Eintrags: als einklappbaren Bereich markieren. Die
        # Umbrüche davor und danach stehen noch aus, so dass der Zeilenumbruch
        # vor der Unterliste mit eingeklappt wird.
        fold = self.li_folds[-1] if self.li_folds else None
        if fold is not None:
            self.ops.append(FoldStartOp(fold))
        self.list_depth += 1
        inner = replace(style, indent=style.indent + 1)
        start = (el.get("start") or "").strip()
        counter = int(start) if re.fullmatch(r"-?\d+", start) else 1
        kind = el.get("type") or "1"
        for child in el.children:
            if isinstance(child, Element) and child.tag == "li":
                if "hidden" in child.attrs:
                    continue
                if child.get("id"):
                    self.pending_anchors.append(child.get("id"))
                value = (child.get("value") or "").strip()
                if re.fullmatch(r"-?\d+", value):
                    counter = int(value)
                marker = list_number(counter, kind) + "." if ordered else "*"
                self._li(child, inner, marker)
                counter += 1
            else:
                self.node(child, inner)
        self.list_depth -= 1
        if fold is not None:
            self.ops.append(FoldEndOp(fold))
        self.block_break(margin)

    def _li(self, el: Element, style: Style, marker: str) -> None:
        fold = None
        if any(True for tag in ("ul", "ol", "menu", "dir") for _ in el.iter(tag)):
            fold = self.folds
            self.folds += 1
        self.block_break(1)
        self.pending_marker = (marker, replace(style, href=None, info=None), fold)
        self.li_folds.append(fold)
        self.children(el, style)
        self.li_folds.pop()
        if self.pending_marker:
            self._flush()
        self.after_marker = False
        self.block_break(1)

    def _tag_li(self, el: Element, style: Style) -> None:
        # <li> außerhalb einer Liste
        self._li(el, replace(style, indent=style.indent + 1), "*")

    # -- Tabellen -------------------------------------------------------------

    def _tag_table(self, el: Element, style: Style) -> None:
        rows = _table_rows(el)
        ncols = max((sum(_span(c, "colspan") for c in cells) for cells in rows), default=0)
        caption = next((c for c in el.children if isinstance(c, Element) and c.tag == "caption"), None)
        margin = 1 if self.list_depth else 2
        self.block_break(margin)
        if caption is not None:
            self._block(caption, replace(style, bold=True), 1)
        if el.find("table") is not None or ncols <= 1:
            self._linear_table(rows, style)
        else:
            self._grid_table(rows, style)
        self.block_break(margin)

    def _linear_table(self, rows: list[list[Element]], style: Style) -> None:
        """Layout-Tabellen: jede Zeile als eigene Zeile, Zellen hintereinander."""
        for cells in rows:
            self.block_break(1)
            for cell in cells:
                cell_style = replace(style, bold=True) if cell.tag == "th" else style
                self.children(cell, cell_style)
                self.pending_space = True
            self.block_break(1)

    def _grid_table(self, rows: list[list[Element]], style: Style) -> None:
        cells = []
        for cells_in_row in rows:
            row_cells = []
            for cell in cells_in_row:
                lines = self._cell_lines(cell)
                row_cells.append((cell, lines))
            if any(lines for _, lines in row_cells) or any(_span(c, "rowspan") > 1 for c in cells_in_row):
                cells.append(row_cells)
        if not cells:
            return
        lines = layout_grid(cells, style, self.columns)
        self._flush()
        for runs in lines:
            for text, run_style in runs:
                self._emit(text, run_style)
            self._emit("\n", PLAIN)
        self.after_marker = False

    def _cell_lines(self, cell: Element) -> list[list[tuple[str, Style]]]:
        """Rendert eine Zelle für sich und liefert ihre Zeilen als Textläufe."""
        sub = Renderer(self.base_url, self.columns)
        sub.list_depth = 1   # keine Leerzeilen um Listen innerhalb von Zellen
        sub.children(cell, Style(bold=cell.tag == "th"))
        sub.finish()
        runs: list[tuple[str, Style]] = []
        for op in sub.ops:
            if isinstance(op, (TextOp, MarkerOp)):
                text = op.text + (" " if isinstance(op, MarkerOp) else "")
                runs.append((text, op.style))
            elif isinstance(op, ImageOp):
                runs.append((f"[{op.alt or 'Bild'}]", replace(op.style, dim=True)))
            elif isinstance(op, RuleOp):
                runs.append(("—", op.style))
        lines: list[list[tuple[str, Style]]] = [[]]
        for text, run_style in runs:
            cell_style = replace(run_style, mono=True, size=BASE_SIZE, indent=0,
                                 align="left", pre=False, nowrap=True, offset=0)
            for i, part in enumerate(text.split("\n")):
                if i:
                    lines.append([])
                if part:
                    lines[-1].append((part, cell_style))
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        return lines


def _table_rows(table: Element) -> list[list[Element]]:
    rows = []
    for child in table.children:
        if not isinstance(child, Element):
            continue
        if child.tag == "tr":
            rows.append(child)
        elif child.tag in ("thead", "tbody", "tfoot"):
            rows.extend(c for c in child.children if isinstance(c, Element) and c.tag == "tr")
    return [[c for c in tr.children if isinstance(c, Element) and c.tag in ("td", "th")
             and "hidden" not in c.attrs] for tr in rows]


def _span(cell: Element, name: str) -> int:
    value = _int_attr(cell, name)
    return max(1, min(value, 1000)) if value is not None else 1


# -- Tabellenraster -----------------------------------------------------------

Run = tuple[str, Style]


def _line_width(line: list[Run]) -> int:
    return sum(len(text) for text, _ in line)


def wrap_runs(line: list[Run], width: int) -> list[list[Run]]:
    """Bricht eine Zeile aus Textläufen wortweise auf die Breite `width` um."""
    width = max(1, width)
    result: list[list[Run]] = [[]]
    used = 0

    def newline() -> None:
        nonlocal used
        while result[-1] and result[-1][-1][0] == " ":
            result[-1].pop()
        result.append([])
        used = 0

    for text, style in line:
        for token in _TOKENS.findall(text):
            if token.isspace():
                if used and used < width:
                    result[-1].append((" ", style))
                    used += 1
                continue
            if used + len(token) > width and used:
                newline()
            while len(token) > width:
                result[-1].append((token[:width], style))
                token = token[width:]
                newline()
            if token:
                result[-1].append((token, style))
                used += len(token)
    while result[-1] and result[-1][-1][0] == " ":
        result[-1].pop()
    return result


def layout_grid(rows: list[list[tuple[Element, list[list[Run]]]]], style: Style,
                columns: int) -> list[list[Run]]:
    """Setzt Tabellenzellen in ein Raster mit Rahmenlinien aus Box-Zeichen."""
    # Zellen im Raster platzieren (colspan/rowspan berücksichtigen).
    nrows = len(rows)
    grid: dict[tuple[int, int], int] = {}
    placed = []   # (Zeile, Spalte, colspan, rowspan, Zeilen, Ausrichtung)
    for r, row in enumerate(rows):
        c = 0
        for cell, lines in row:
            while (r, c) in grid:
                c += 1
            colspan = _span(cell, "colspan")
            rowspan = min(_span(cell, "rowspan"), nrows - r)
            if cell.get("rowspan", "").strip() == "0":
                rowspan = nrows - r
            align = (cell.get("align") or "").lower()
            if align not in ("left", "center", "right"):
                align = "center" if cell.tag == "th" else "left"
            for rr in range(r, r + rowspan):
                for cc in range(c, c + colspan):
                    grid[(rr, cc)] = len(placed)
            placed.append((r, c, colspan, rowspan, lines, align))
            c += colspan
    ncols = max(c for _, c in grid) + 1 if grid else 0
    if ncols == 0:
        return []

    def owner(r: int, c: int) -> int:
        # Leere Plätze bekommen eine eigene, eindeutige Kennung.
        return grid.get((r, c), -1 - (r * ncols + c))

    # Spaltenbreiten bestimmen.
    widths = [1] * ncols
    minimum = [1] * ncols
    for _, c, colspan, _, lines, _ in sorted(placed, key=lambda p: p[2]):
        natural = max((_line_width(line) for line in lines), default=0)
        longest = max((len(tok) for line in lines for text, _ in line
                       for tok in text.split()), default=0)
        if colspan == 1:
            widths[c] = max(widths[c], natural)
            minimum[c] = max(minimum[c], min(longest, 15))
        else:
            current = sum(widths[c:c + colspan]) + 3 * (colspan - 1)
            if natural > current:
                widths[c + colspan - 1] += natural - current
    budget = max(3 * ncols, columns - 3 * ncols - 1 - 2 * style.indent)
    excess = sum(widths) - budget
    while excess > 0:
        candidates = [i for i in range(ncols) if widths[i] > minimum[i]]
        if not candidates:
            break
        widest = max(candidates, key=lambda i: widths[i])
        second = max((widths[i] for i in candidates if i != widest), default=minimum[widest])
        step = max(1, min(excess, widths[widest] - max(second, minimum[widest])))
        widths[widest] -= step
        excess -= step

    # Zellinhalte umbrechen und Zeilenhöhen bestimmen.
    wrapped = []
    for _, c, colspan, _, lines, _ in placed:
        inner = sum(widths[c:c + colspan]) + 3 * (colspan - 1)
        out = []
        for line in lines:
            out.extend(wrap_runs(line, inner) if line else [[]])
        wrapped.append(out)
    heights = [1] * nrows
    for (r, _, _, rowspan, _, _), lines in zip(placed, wrapped):
        if rowspan == 1:
            heights[r] = max(heights[r], len(lines))
    for (r, _, _, rowspan, _, _), lines in zip(placed, wrapped):
        if rowspan > 1:
            available = sum(heights[r:r + rowspan]) + rowspan - 1
            if len(lines) > available:
                heights[r + rowspan - 1] += len(lines) - available

    xs = [0]
    for w in widths:
        xs.append(xs[-1] + w + 3)
    ys = [0]
    for h in heights:
        ys.append(ys[-1] + h + 1)
    total_w = xs[-1] + 1
    border = replace(PLAIN, mono=True, dim=True, nowrap=True, indent=style.indent)
    blank = replace(PLAIN, mono=True, nowrap=True, indent=style.indent)
    canvas = [[(" ", blank)] * total_w for _ in range(ys[-1] + 1)]

    def vertical(r: int, j: int) -> bool:
        return j in (0, ncols) or owner(r, j - 1) != owner(r, j)

    def horizontal(r: int, c: int) -> bool:
        return r in (0, nrows) or owner(r - 1, c) != owner(r, c)

    # Senkrechte Linien hätten in Tk Lücken zwischen den Zeilen, deshalb trennen
    # nur waagerechte Linien die Zeilen; Spalten trennt ein Leerraum.
    for r in range(nrows + 1):
        y = ys[r]
        for j in range(ncols + 1):
            joined = (0 < j < ncols and horizontal(r, j - 1) and horizontal(r, j)
                      and not (r > 0 and vertical(r - 1, j)) and not (r < nrows and vertical(r, j)))
            if joined:
                canvas[y][xs[j]] = ("\u2500", border)
            if j < ncols and horizontal(r, j):
                for x in range(xs[j] + 1, xs[j + 1]):
                    canvas[y][x] = ("\u2500", border)

    for (r, c, colspan, _, _, align), lines in zip(placed, wrapped):
        inner = xs[c + colspan] - xs[c] - 3
        for i, line in enumerate(lines):
            pad = inner - _line_width(line)
            x = xs[c] + 2 + {"left": 0, "center": pad // 2, "right": pad}[align]
            y = ys[r] + 1 + i
            for text, run_style in line:
                run_style = replace(run_style, indent=style.indent)
                for ch in text:
                    if x < total_w - 1:
                        canvas[y][x] = (ch, run_style)
                    x += 1

    result = []
    for row in canvas:
        row = row[1:]   # linker Rand ist stets leer
        while row and row[-1][0] == " ":
            row.pop()
        runs: list[Run] = []
        for ch, ch_style in row:
            if runs and runs[-1][1] == ch_style:
                runs[-1] = (runs[-1][0] + ch, ch_style)
            else:
                runs.append((ch, ch_style))
        result.append(runs)
    return result
