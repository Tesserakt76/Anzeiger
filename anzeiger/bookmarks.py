"""Lesezeichen im Netscape-Bookmark-Format (bookmarks.html).

Das Format schreiben Chrome und Firefox beim Exportieren und lesen es beim
Importieren. Unbekannte Attribute (Symbole, Schlagwörter, die Markierung der
Lesezeichen-Symbolleiste …) bleiben beim Laden und Speichern erhalten, damit
eine aus einem Browser exportierte Datei verlustfrei weiterverwendet werden kann.
"""

from __future__ import annotations

import html
import os
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from .settings import default_path as _settings_path

HEADER = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
"""


def default_path() -> Path:
    """Liegt neben settings.json: ~/.config/anzeiger/bookmarks.html."""
    return _settings_path().with_name("bookmarks.html")


def _now() -> str:
    return str(int(time.time()))


@dataclass(eq=False)
class Bookmark:
    title: str
    url: str
    attrs: dict[str, str] = field(default_factory=dict)   # ADD_DATE, ICON, TAGS …
    description: str = ""


@dataclass(eq=False)
class Separator:
    pass


@dataclass(eq=False)
class Folder:
    title: str
    children: list[Bookmark | Folder | Separator] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)   # ADD_DATE, PERSONAL_TOOLBAR_FOLDER …
    description: str = ""

    def walk(self, path: tuple[int, ...] = ()):
        """Alle Lesezeichen und Ordner mit ihrem Pfad (Indizes ab der Wurzel)."""
        for i, child in enumerate(self.children):
            yield path + (i,), child
            if isinstance(child, Folder):
                yield from child.walk(path + (i,))

    def find_url(self, url: str) -> tuple[int, ...] | None:
        return next((p for p, node in self.walk() if isinstance(node, Bookmark) and node.url == url), None)

    def node(self, path: tuple[int, ...]) -> Bookmark | Folder | Separator | None:
        node: Bookmark | Folder | Separator = self
        for index in path:
            if not isinstance(node, Folder) or not 0 <= index < len(node.children):
                return None
            node = node.children[index]
        return node

    def remove(self, path: tuple[int, ...]) -> Bookmark | Folder | Separator | None:
        parent = self.node(path[:-1]) if path else None
        if not isinstance(parent, Folder) or not 0 <= path[-1] < len(parent.children):
            return None
        return parent.children.pop(path[-1])

    def count(self) -> int:
        return sum(1 for _, node in self.walk() if isinstance(node, Bookmark))


# -- Lesen ----------------------------------------------------------------------

class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Folder("Lesezeichen")
        self.stack: list[Folder] = []
        self.pending: Folder | None = None      # Ordner aus <H3>, wartet auf sein <DL>
        self.capture: Bookmark | Folder | None = None
        self.text: list[str] = []
        self.described: Bookmark | Folder | None = None
        self.in_dd = False
        self.root_opened = False

    @property
    def current(self) -> Folder:
        return self.stack[-1] if self.stack else self.root

    def _finish_text(self) -> None:
        if self.capture is not None:
            self.capture.title = " ".join("".join(self.text).split())
            self.capture = None
        self.text = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        upper = {name.upper(): value or "" for name, value in attrs}
        if tag in ("dt", "dl", "hr"):
            self._end_description()
        if tag == "dl":
            if self.pending is not None:
                self.stack.append(self.pending)
                self.pending = None
            elif not self.root_opened:
                self.root_opened = True     # äußerste Liste = Wurzel
            else:
                # <DL> ohne vorangehenden Ordnertitel: als namenlosen Ordner übernehmen
                folder = Folder("")
                self.current.children.append(folder)
                self.stack.append(folder)
        elif tag == "h3":
            folder = Folder("", attrs=upper)
            self.current.children.append(folder)
            self.pending = folder
            self.capture = folder
            self.described = folder
        elif tag == "a":
            url = upper.pop("HREF", "")
            bookmark = Bookmark("", url, upper)
            self.current.children.append(bookmark)
            self.capture = bookmark
            self.described = bookmark
        elif tag == "hr":
            self.current.children.append(Separator())
        elif tag == "dd" and self.described is not None:
            self.in_dd = True
            self.text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("a", "h3"):
            self._finish_text()
        elif tag == "dl":
            self._end_description()
            self.pending = None
            if self.stack:
                self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self.capture is not None or self.in_dd:
            self.text.append(data)

    def _end_description(self) -> None:
        if self.in_dd and self.described is not None:
            self.described.description = " ".join("".join(self.text).split())
        self.in_dd = False
        self.text = [] if self.capture is None else self.text


def parse(source: str) -> Folder:
    parser = _Parser()
    parser.feed(source)
    parser.close()
    parser._finish_text()
    parser._end_description()
    return parser.root


def load(path: Path) -> Folder:
    """Liest die Lesezeichen-Datei; fehlt sie, gibt es eine leere Sammlung."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return Folder("Lesezeichen")
    return parse(source)


# -- Schreiben ------------------------------------------------------------------

def _attrs(attrs: dict[str, str]) -> str:
    return "".join(f' {name}="{html.escape(value, quote=True)}"' for name, value in attrs.items())


def _write_folder(folder: Folder, depth: int, out: list[str]) -> None:
    pad = "    " * depth
    out.append(f"{pad}<DL><p>\n")
    for child in folder.children:
        if isinstance(child, Bookmark):
            out.append(f'{pad}    <DT><A HREF="{html.escape(child.url, quote=True)}"{_attrs(child.attrs)}>'
                       f"{html.escape(child.title, quote=False)}</A>\n")
        elif isinstance(child, Folder):
            out.append(f"{pad}    <DT><H3{_attrs(child.attrs)}>{html.escape(child.title, quote=False)}</H3>\n")
        else:
            out.append(f"{pad}    <HR>\n")
            continue
        if child.description:
            out.append(f"{pad}    <DD>{html.escape(child.description, quote=False)}\n")
        if isinstance(child, Folder):
            _write_folder(child, depth + 1, out)
    out.append(f"{pad}</DL><p>\n")


def serialize(root: Folder) -> str:
    out = [HEADER]
    _write_folder(root, 0, out)
    return "".join(out)


def save(root: Folder, path: Path) -> None:
    """Schreibt atomar (erst temporäre Datei, dann umbenennen)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(serialize(root), encoding="utf-8")
    os.replace(tmp, path)


# -- Ändern -------------------------------------------------------------------

def add(path: Path, url: str, title: str) -> bool:
    """Legt ein Lesezeichen am Ende an. False, wenn die Adresse schon vorhanden ist."""
    root = load(path)
    if root.find_url(url) is not None:
        return False
    stamp = _now()
    root.children.append(Bookmark(title.strip() or url, url, {"ADD_DATE": stamp, "LAST_MODIFIED": stamp}))
    save(root, path)
    return True


def remove_url(path: Path, url: str) -> bool:
    """Entfernt das erste Lesezeichen mit dieser Adresse."""
    root = load(path)
    where = root.find_url(url)
    if where is None:
        return False
    root.remove(where)
    save(root, path)
    return True


def identity(node: Bookmark | Folder | Separator | None) -> str:
    """Woran ein Eintrag erkannt wird: Adresse eines Lesezeichens, Name eines Ordners."""
    if isinstance(node, Bookmark):
        return node.url
    if isinstance(node, Folder):
        return node.title
    return ""


def _at(root: Folder, where: tuple[int, ...], key: str) -> Bookmark | Folder | None:
    """Der Eintrag an `where`, aber nur, wenn er noch `key` hat (die Datei kann sich geändert haben)."""
    node = root.node(where) if where else None
    return node if isinstance(node, (Bookmark, Folder)) and identity(node) == key else None


def remove_at(path: Path, where: tuple[int, ...], key: str) -> bool:
    """Entfernt das Lesezeichen oder den Ordner (samt Inhalt) an `where`."""
    root = load(path)
    if _at(root, where, key) is None:
        return False
    root.remove(where)
    save(root, path)
    return True


def rename_at(path: Path, where: tuple[int, ...], key: str, title: str) -> bool:
    root = load(path)
    node = _at(root, where, key)
    if node is None or not title.strip():
        return False
    node.title = " ".join(title.split())
    node.attrs["LAST_MODIFIED"] = _now()
    save(root, path)
    return True


def add_folder(path: Path, parent: tuple[int, ...], title: str) -> bool:
    """Legt einen leeren Ordner am Ende des Ordners `parent` an (() = oberste Ebene)."""
    root = load(path)
    target = root.node(parent)
    if not isinstance(target, Folder) or not title.strip():
        return False
    stamp = _now()
    target.children.append(Folder(" ".join(title.split()), attrs={"ADD_DATE": stamp, "LAST_MODIFIED": stamp}))
    save(root, path)
    return True


def move_at(path: Path, where: tuple[int, ...], key: str, dest: tuple[int, ...]) -> bool:
    """Verschiebt den Eintrag an `where` ans Ende des Ordners `dest`.

    False, wenn der Eintrag nicht mehr da ist; ValueError bei unmöglichem Ziel.
    """
    root = load(path)
    node = _at(root, where, key)
    if node is None:
        return False
    target = root.node(dest)
    if not isinstance(target, Folder):
        raise ValueError("Der Zielordner wurde nicht gefunden.")
    if dest[:len(where)] == where:
        raise ValueError("Ein Ordner kann nicht in sich selbst verschoben werden.")
    root.remove(where)     # `target` ist ein Objekt, verschobene Indizes stören also nicht
    target.children.append(node)
    save(root, path)
    return True


def folders(root: Folder) -> list[tuple[tuple[int, ...], str]]:
    """Alle Ordner mit Pfad und lesbarem Namen, die Wurzel zuerst (für Auswahllisten)."""
    result = [((), root.title or "Lesezeichen")]
    names: dict[tuple[int, ...], str] = {}
    for where, node in root.walk():
        if isinstance(node, Folder):
            name = node.title or "(Ordner ohne Namen)"
            names[where] = f"{names[where[:-1]]} › {name}" if where[:-1] in names else name
            result.append((where, names[where]))
    return result


def format_path(where: tuple[int, ...]) -> str:
    return ".".join(map(str, where))


def parse_path(text: str) -> tuple[int, ...] | None:
    """"1.0" → (1, 0); "" und Ungültiges → None."""
    try:
        where = tuple(int(part) for part in text.split("."))
    except ValueError:
        return None
    return where if where and all(i >= 0 for i in where) else None


def parse_folder(text: str) -> tuple[int, ...] | None:
    """Wie parse_path, aber "" steht für die oberste Ebene ()."""
    return () if text == "" else parse_path(text)
