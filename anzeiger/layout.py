"""Übersetzt den Dokumentbaum in eine flache Folge von Darstellungsanweisungen.

Die Anweisungen (TextOp, MarkerOp, ImageOp, RuleOp, AnchorOp, FieldOp …) sind
unabhängig von tkinter, damit sich das Layout ohne Fenster testen lässt.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from urllib.parse import urljoin

from . import net
from .dom import Element, parse_html
from .forms import FormInfo, normalize_enctype, normalize_method
from .i18n import t, tn

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

# Elemente, die als eigener Block dargestellt werden (Klappschalter in eigener Zeile).
BLOCK_TAGS = frozenset(tag for tag, margin in BLOCK.items() if margin) | frozenset({
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "blockquote", "pre", "listing", "xmp",
    "plaintext", "ul", "ol", "menu", "dir", "li", "table",
})
# Elemente, die auch ohne Text etwas anzeigen
CONTENT_TAGS = frozenset({"img", "input", "select", "textarea", "button", "iframe", "hr"})
HIDDEN_PREVIEW = 50   # Zeichen Text in der Schalterzeile verborgener Inhalte

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
class ListToggleOp:
    """Klappschalter vor einem einklappbaren Bereich.

    kind = "list": eigene Zeile vor einer ganzen Liste („▾ Liste (3 Einträge)“),
    kind = "hidden": von der Seite per style versteckter Inhalt; `inline` = mitten im Text.
    """
    fold: int
    label: str
    style: Style
    kind: str = "list"
    inline: bool = False


@dataclass
class FoldStartOp:
    """Beginn eines einklappbaren Bereichs.

    kind = "sublist": Unterliste des Listeneintrags `fold` (Schalter am Marker),
    kind = "list": ganze Liste (Schalter in einer ListToggleOp davor),
    kind = "hidden": verborgener Inhalt (Schalter in einer ListToggleOp davor).
    """
    fold: int
    kind: str = "sublist"


@dataclass
class FoldEndOp:
    fold: int


@dataclass
class Option:
    value: str
    label: str
    selected: bool = False
    disabled: bool = False


@dataclass
class FieldOp:
    """Ein Formularelement (input, button, select, textarea).

    `form` ist der Index in Page.forms oder None, wenn das Feld zu keinem Formular
    gehört. kind ist der (kleingeschriebene) input-Typ bzw. "select"/"textarea";
    <button> wird zu "submit", "reset" oder "button".
    """
    kind: str
    name: str
    value: str
    style: Style
    form: int | None = None
    form_ref: str | None = None      # form="…"-Attribut, wird nach dem Layout aufgelöst
    label: str = ""                  # Beschriftung von Knöpfen
    checked: bool = False
    disabled: bool = False
    readonly: bool = False
    placeholder: str = ""
    size: int = 20                   # Zeichen (Textfeld) bzw. Spalten (textarea)
    rows: int = 2
    multiple: bool = False
    options: list[Option] = field(default_factory=list)
    formaction: str | None = None    # Überschreibungen am Absendeknopf
    formmethod: str | None = None
    formenctype: str | None = None


TEXT_KINDS = frozenset({"text", "search", "email", "url", "tel", "number", "password", "date",
                        "datetime-local", "month", "week", "time", "color", "range"})
BUTTON_KINDS = frozenset({"submit", "reset", "button", "image"})
_CONTROLS = ("input", "select", "textarea", "button")


Op = (TextOp | MarkerOp | ImageOp | RuleOp | AnchorOp | ListToggleOp | FoldStartOp | FoldEndOp
      | FieldOp)


@dataclass
class Page:
    url: str
    title: str = ""
    ops: list[Op] = field(default_factory=list)
    forms: list[FormInfo] = field(default_factory=list)
    preloaded: dict[str, bytes] = field(default_factory=dict)   # Bildadresse → fertiges Bild (PPM)


def render_html(source: str, url: str, columns: int = 100, fold_hidden: bool = False) -> Page:
    """Parst und layoutet eine HTML-Seite. `columns` begrenzt die Tabellenbreite.

    `fold_hidden`: per style="display:none" oder "visibility:hidden" versteckte Elemente
    einklappbar zeigen, statt sie wie sichtbaren Inhalt zu behandeln.
    """
    root = parse_html(source)
    base = url
    base_el = next((e for e in root.iter("base") if e.get("href")), None)
    if base_el is not None:
        base = urljoin(url, base_el.get("href", "").strip())
    renderer = Renderer(base, columns, page_url=url, fold_hidden=fold_hidden)
    title_el = root.find("title")
    title = _WS.sub(" ", title_el.text()).strip() if title_el is not None else ""

    refresh = _meta_refresh(root, base)
    if refresh:
        renderer.inline(t("layout.redirect"), replace(PLAIN, dim=True))
        renderer.inline(refresh, replace(PLAIN, href=refresh))
        renderer.block_break(2)

    renderer.node(root, PLAIN)
    renderer.finish()
    # Felder mit form="id" außerhalb ihres Formulars zuordnen.
    by_id = {form.id: i for i, form in enumerate(renderer.forms) if form.id}
    for op in renderer.ops:
        if isinstance(op, FieldOp) and op.form_ref is not None and op.form_ref in by_id:
            op.form = by_id[op.form_ref]
    return Page(url, title, renderer.ops, renderer.forms)


def render_text(source: str, url: str) -> Page:
    """Stellt reinen Text (text/plain) unverändert in Festbreitenschrift dar."""
    renderer = Renderer(url)
    renderer.text(source, Style(mono=True, pre=True))
    renderer.finish()
    return Page(url, url.rsplit("/", 1)[-1], renderer.ops)


def hidden_by_style(el: Element) -> bool:
    """True, wenn das style-Attribut das Element versteckt (display:none, visibility:hidden).

    Ausgewertet wird nur dieses Attribut; Stylesheets und Klassen bleiben unbeachtet.
    """
    props: dict[str, str] = {}
    for declaration in (el.get("style") or "").split(";"):
        name, colon, value = declaration.partition(":")
        if colon:
            value = value.strip().lower()
            props[name.strip().lower()] = value.removesuffix("!important").strip()
    return props.get("display") == "none" or props.get("visibility") == "hidden"


def _shown_children(el: Element) -> Iterator[Element | str]:
    for child in el.children:
        if isinstance(child, str) or (child.tag not in SKIP and "hidden" not in child.attrs):
            yield child


def _visible_text(el: Element) -> str:
    """Text des Elements ohne Skripte, Stile und Elemente mit hidden-Attribut."""
    parts = []
    for child in _shown_children(el):
        if isinstance(child, str):
            parts.append(child)
        elif child.tag in BLOCK_TAGS or child.tag in ("br", "td", "th"):
            parts.append(f" {_visible_text(child)} ")   # Blöcke nicht aneinanderkleben
        else:
            parts.append(_visible_text(child))
    return "".join(parts)


def _has_content(el: Element) -> bool:
    """Würde das Element Text, ein Bild, ein Formularfeld o. Ä. anzeigen?"""
    for child in _shown_children(el):
        if isinstance(child, str):
            if child.strip():
                return True
        elif child.tag in CONTENT_TAGS and not (child.tag == "input"
                                                and (child.get("type") or "").lower() == "hidden"):
            return True
        elif _has_content(child):
            return True
    return el.tag in CONTENT_TAGS and not (el.tag == "input" and (el.get("type") or "").lower() == "hidden")


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


def _button_label(kind: str) -> str:
    """Beschriftung eines Knopfs ohne eigenen Text."""
    return {"submit": t("form.submit"), "reset": t("form.reset")}.get(kind, "")


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
    def __init__(self, base_url: str, columns: int = 100, page_url: str | None = None,
                 foldable: bool = True, fold_hidden: bool = False) -> None:
        self.base_url = base_url
        self.page_url = page_url or base_url
        self.columns = columns
        self.foldable = foldable      # False in Tabellenzellen (dort nur Text)
        self.fold_hidden = fold_hidden
        self.in_hidden = 0            # > 0 innerhalb eines verborgenen Bereichs
        self.forms: list[FormInfo] = []
        self.current_form: int | None = None
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
        if el.tag in SKIP or "hidden" in el.attrs:
            return
        if self._fold_here(el):
            self._hidden(el, style, lambda: self._element(el, style))
        else:
            self._element(el, style)

    def _element(self, el: Element, style: Style) -> None:
        tag = el.tag
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
            self.inline(t("layout.frame", url=url), replace(style, href=url))

    # -- Formulare -------------------------------------------------------------

    def _tag_form(self, el: Element, style: Style) -> None:
        action = (el.get("action") or "").strip()
        info = FormInfo(
            action=urljoin(self.base_url, action) if action else self.page_url,
            method=normalize_method(el.get("method")),
            enctype=normalize_enctype(el.get("enctype")),
            id=el.get("id"),
        )
        outer = self.current_form
        self.forms.append(info)
        self.current_form = len(self.forms) - 1
        self._block(el, style, BLOCK["form"])
        self.current_form = outer

    def _field(self, el: Element, style: Style, **values) -> FieldOp:
        override = el.get("formaction")
        op = FieldOp(
            name=el.get("name") or "",
            style=replace(style, href=None),
            form=None if el.get("form") else self.current_form,
            form_ref=el.get("form"),
            disabled="disabled" in el.attrs,
            readonly="readonly" in el.attrs,
            formaction=urljoin(self.base_url, override.strip()) if override and override.strip() else None,
            formmethod=normalize_method(el.get("formmethod")) if el.get("formmethod") else None,
            formenctype=normalize_enctype(el.get("formenctype")) if el.get("formenctype") else None,
            **values,
        )
        if op.kind == "hidden":
            self.ops.append(op)   # wird mitgeschickt, aber nicht angezeigt
            return op
        self._flush()
        self._space()
        self.ops.append(op)
        self.trailing_nl = 0
        self.after_marker = False
        return op

    def _tag_input(self, el: Element, style: Style) -> None:
        kind = (el.get("type") or "text").strip().lower()
        value = el.get("value") or ""
        if kind in ("checkbox", "radio"):
            self._field(el, style, kind=kind, value=value or "on", checked="checked" in el.attrs)
        elif kind in BUTTON_KINDS:
            default = _button_label(kind)
            label = (el.get("alt") or t("form.image_button")) if kind == "image" else (value or default)
            self._field(el, style, kind=kind, value=value, label=label)
        elif kind in ("hidden", "file"):
            self._field(el, style, kind=kind, value=value if kind == "hidden" else "")
        else:
            size = _int_attr(el, "size") or 20
            self._field(el, style, kind=kind if kind in TEXT_KINDS else "text", value=value,
                        placeholder=el.get("placeholder") or "", size=max(1, min(size, 60)))

    def _tag_button(self, el: Element, style: Style) -> None:
        kind = (el.get("type") or "submit").strip().lower()
        if kind not in ("submit", "reset", "button"):
            kind = "submit"
        label = _WS.sub(" ", el.text()).strip() or _button_label(kind)
        self._field(el, style, kind=kind, value=el.get("value") or "", label=label)

    def _tag_select(self, el: Element, style: Style) -> None:
        options = []
        for opt in el.iter("option"):
            label = _WS.sub(" ", opt.get("label") or opt.text()).strip()
            value = opt.get("value")
            options.append(Option(_WS.sub(" ", opt.text()).strip() if value is None else value, label,
                                  "selected" in opt.attrs, "disabled" in opt.attrs))
        multiple = "multiple" in el.attrs
        if not multiple and options and not any(o.selected for o in options):
            first = next((o for o in options if not o.disabled), options[0])
            first.selected = True
        if not multiple:
            chosen = [o for o in options if o.selected]
            for o in chosen[:-1]:   # bei mehreren „selected“ gilt das letzte
                o.selected = False
        self._field(el, style, kind="select", value="", options=options, multiple=multiple,
                    size=_int_attr(el, "size") or 4)

    def _tag_textarea(self, el: Element, style: Style) -> None:
        content = el.text()
        if content.startswith("\r\n"):
            content = content[2:]
        elif content.startswith("\n"):
            content = content[1:]
        self.block_break(1)
        self._field(el, style, kind="textarea", value=content, placeholder=el.get("placeholder") or "",
                    size=max(10, min(_int_attr(el, "cols") or 40, 100)),
                    rows=max(1, min(_int_attr(el, "rows") or 3, 20)))
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
        kind = "sublist"
        count = sum(1 for c in el.children if isinstance(c, Element) and c.tag == "li" and "hidden" not in c.attrs)
        if fold is None and self.foldable and count:
            # Eigenständige Liste: Kopfzeile mit Schalter, darunter die ganze Liste.
            fold, kind = self.folds, "list"
            self.folds += 1
            self._flush()
            label = tn("layout.list", count)
            self.ops.append(ListToggleOp(fold, label, replace(style, href=None, info=None, dim=True,
                                                              bold=False, italic=False)))
            self.trailing_nl = 1
            self.after_marker = False
            self.pending_space = False
        if fold is not None:
            self.ops.append(FoldStartOp(fold, kind))
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
                if self._fold_here(child):
                    self._hidden(child, inner, lambda: self._li(child, inner, marker))
                else:
                    self._li(child, inner, marker)
                counter += 1
            else:
                self.node(child, inner)
        self.list_depth -= 1
        if fold is not None:
            self.ops.append(FoldEndOp(fold))
        self.block_break(margin)

    def _fold_here(self, el: Element) -> bool:
        """Verborgenes Element, das einen eigenen Klappschalter bekommt?

        Nicht in Tabellenzellen (dort nur Text), nicht innerhalb eines schon verborgenen
        Bereichs und nicht, wenn das Element ohnehin nichts anzeigen würde.
        """
        return (self.fold_hidden and self.foldable and not self.in_hidden
                and hidden_by_style(el) and _has_content(el))

    def _hidden(self, el: Element, style: Style, render: Callable[[], None]) -> None:
        """Zeigt ein verborgenes Element eingeklappt hinter einem Schalter („▸ Verborgen: …“)."""
        fold = self.folds
        self.folds += 1
        preview = _WS.sub(" ", _visible_text(el)).strip()
        if len(preview) > HIDDEN_PREVIEW:
            preview = preview[:HIDDEN_PREVIEW].rstrip() + " …"
        label = t("layout.hidden_text", text=preview) if preview else t("layout.hidden")
        toggle_style = replace(style, href=None, info=None, dim=True, bold=False, italic=False,
                               underline=False, strike=False, mark=False, pre=False, nowrap=False)
        block = el.tag in BLOCK_TAGS
        if block:
            self.block_break(1)
            self._flush()
            self.ops.append(ListToggleOp(fold, label, toggle_style, "hidden"))
            self.trailing_nl = 1
            self.pending_space = False
        else:
            self._flush()
            self.pending_space = True
            self._space()
            self.ops.append(ListToggleOp(fold, label, toggle_style, "hidden", inline=True))
            self.trailing_nl = 0
            self.pending_space = True   # Abstand zum Inhalt, wird mit eingeklappt
        self.after_marker = False
        self.ops.append(FoldStartOp(fold, "hidden"))
        self.in_hidden += 1
        render()
        self.in_hidden -= 1
        if self.pending_marker:
            self._flush()
        self.ops.append(FoldEndOp(fold))
        if not block:
            self.pending_space = True

    def _li(self, el: Element, style: Style, marker: str) -> None:
        fold = None
        if self.foldable and any(True for tag in ("ul", "ol", "menu", "dir") for _ in el.iter(tag)):
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
        has_controls = any(True for tag in _CONTROLS for _ in el.iter(tag))
        if el.find("table") is not None or ncols <= 1 or has_controls:
            # Formularfelder lassen sich nicht ins Zeichenraster setzen.
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
        sub = Renderer(self.base_url, self.columns, self.page_url, foldable=False)
        sub.list_depth = 1   # keine Leerzeilen um Listen innerhalb von Zellen
        sub.children(cell, Style(bold=cell.tag == "th"))
        sub.finish()
        runs: list[tuple[str, Style]] = []
        for op in sub.ops:
            if isinstance(op, (TextOp, MarkerOp)):
                text = op.text + (" " if isinstance(op, MarkerOp) else "")
                runs.append((text, op.style))
            elif isinstance(op, ImageOp):
                label = f"[{op.alt}]" if op.alt else t("image.table")
                if op.src and op.style.href is None and net.same_server(self.page_url, op.src):
                    # Ins Zeichenraster passt kein Bild; der Platzhalter führt stattdessen zum Bild.
                    runs.append((label, replace(op.style, href=op.src)))
                else:
                    runs.append((label, replace(op.style, dim=True)))
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
