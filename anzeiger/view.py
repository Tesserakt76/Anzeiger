"""Darstellung der Layout-Anweisungen in einem tkinter-Textfeld."""

from __future__ import annotations

import base64
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from tkinter import ttk

from .layout import (AnchorOp, FoldEndOp, FoldStartOp, ImageOp, MarkerOp, Page, RuleOp,
                     Style, TextOp)

EXPANDED = "\u25be"   # ▾
COLLAPSED = "\u25b8"  # ▸

LINK_COLOR = "#1a0dab"
DIM_COLOR = "#6b6b6b"
BACKGROUND = "#ffffff"
FOREGROUND = "#1b1b1b"
PAD_X = 18


class PageView(ttk.Frame):
    def __init__(self, master: tk.Misc, on_link: Callable[[str], None],
                 on_hover: Callable[[str | None], None]) -> None:
        super().__init__(master)
        self.on_link = on_link
        self.on_hover = on_hover

        self.text = tk.Text(
            self, wrap="word", padx=PAD_X, pady=12, borderwidth=0, highlightthickness=0,
            background=BACKGROUND, foreground=FOREGROUND, cursor="xterm",
            undo=False, takefocus=True, spacing1=1, spacing3=1,
            selectbackground="#b4d5fe", inactiveselectbackground="#d6e6fb",
        )
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        xscroll = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.family = tkfont.nametofont("TkDefaultFont").actual("family")
        self.mono_family = tkfont.nametofont("TkFixedFont").actual("family")
        self.base_font = tkfont.Font(family=self.family, size=11)
        self.text.configure(font=self.base_font)
        self.indent_px = self.base_font.measure("0000")
        self._fonts: dict[tuple, tkfont.Font] = {}
        self._style_tags: dict[Style, tuple[str, ...]] = {}
        self._configured: set[str] = set()
        self._href_ids: dict[str, str] = {}
        self._hrefs: dict[str, str] = {}
        self._info_ids: dict[str, str] = {}
        self._infos: dict[str, str] = {}
        self._anchors: dict[str, str] = {}
        self._rules: list[tk.Frame] = []
        self._photos: list[tk.PhotoImage] = []
        self._pressed: str | None = None
        self._hover: str | None = None
        self.images: list[tuple[int, ImageOp]] = []

        self.text.tag_configure("link", foreground=LINK_COLOR, underline=True)
        self.text.tag_configure("dim", foreground=DIM_COLOR)
        self.text.tag_configure("u", underline=True)
        self.text.tag_configure("s", overstrike=True)
        self.text.tag_configure("mark", background="#fff3a3")
        self.text.tag_configure("nowrap", wrap="none", spacing1=0, spacing3=0)
        self.text.tag_raise("sel")

        self.text.bind("<Motion>", self._on_motion)
        self.text.bind("<Leave>", lambda _e: self._set_hover(None))
        self.text.bind("<Button-1>", self._on_press)
        self.text.bind("<ButtonRelease-1>", self._on_release)
        self.text.bind("<Configure>", self._on_resize)
        # Nur-Lesen, aber Markieren und Kopieren bleiben möglich.
        self.text.bind("<Key>", self._on_key)
        self.text.configure(state="disabled")

    # -- Hilfsfunktionen --------------------------------------------------------

    def columns(self) -> int:
        """Ungefähre Anzahl Festbreitenzeichen pro Zeile (für Tabellen)."""
        self.text.update_idletasks()
        if self.text.winfo_width() <= 1:   # Fenster noch nicht sichtbar
            return 100
        return max(40, self.content_width() // self._font(Style(mono=True)).measure("0"))

    def content_width(self) -> int:
        return max(200, self.text.winfo_width() - 2 * PAD_X - 24)

    def _font(self, style: Style) -> tkfont.Font:
        key = (style.size, style.bold, style.italic, style.mono)
        font = self._fonts.get(key)
        if font is None:
            font = tkfont.Font(
                family=self.mono_family if style.mono else self.family,
                size=style.size - (1 if style.mono else 0),
                weight="bold" if style.bold else "normal",
                slant="italic" if style.italic else "roman",
            )
            self._fonts[key] = font
        return font

    def _tag(self, name: str, **options) -> str:
        if name not in self._configured:
            self.text.tag_configure(name, **options)
            self._configured.add(name)
        return name

    def _tags(self, style: Style) -> tuple[str, ...]:
        tags = self._style_tags.get(style)
        if tags is not None:
            return tags
        font = self._font(style)
        names = [self._tag(f"font:{font.name}", font=font)]
        if style.indent:
            px = style.indent * self.indent_px
            names.append(self._tag(f"ind:{style.indent}", lmargin1=px, lmargin2=px))
        if style.align != "left":
            names.append(self._tag(f"align:{style.align}", justify=style.align))
        if style.nowrap:
            names.append("nowrap")
        if style.offset:
            names.append(self._tag(f"off:{style.offset}", offset=style.offset))
        if style.underline:
            names.append("u")
        if style.strike:
            names.append("s")
        if style.mark:
            names.append("mark")
        if style.dim:
            names.append("dim")
        if style.href:
            names.append("link")
            names.append(self._href_tag(style.href))
        if style.info:
            names.append(self._info_tag(style.info, style.info))
        tags = tuple(names)
        self._style_tags[style] = tags
        return tags

    def _href_tag(self, url: str) -> str:
        tag = self._href_ids.get(url)
        if tag is None:
            tag = f"href:{len(self._href_ids)}"
            self._href_ids[url] = tag
            self._hrefs[tag] = url
        return tag

    def _info_tag(self, key: str, message: str) -> str:
        tag = self._info_ids.get(key)
        if tag is None:
            tag = f"info:{len(self._info_ids)}"
            self._info_ids[key] = tag
        self._infos[tag] = message
        return tag

    # -- Seite anzeigen -------------------------------------------------------

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for name in self.text.mark_names():
            if name.startswith(("anchor", "fold")):
                self.text.mark_unset(name)
        for rule in self._rules:
            rule.destroy()
        self._rules.clear()
        self._photos.clear()
        self._hrefs.clear()
        self._href_ids.clear()
        self._infos.clear()
        self._info_ids.clear()
        self._anchors.clear()
        self._style_tags.clear()
        self.images.clear()
        for tag in self.text.tag_names():
            if tag.startswith(("href:", "info:", "img:", "fold:", "toggle:")):
                self.text.tag_delete(tag)
        self.text.configure(state="disabled")

    def show(self, page: Page, image_note: Callable[[ImageOp], str | None]) -> None:
        """Zeigt eine Seite an. `image_note` liefert für nicht ladbare Bilder den Grund."""
        self.clear()
        text = self.text
        text.configure(state="normal")
        batch: list = []

        def flush() -> None:
            if batch:
                text.insert("end", *batch)
                batch.clear()

        for op in page.ops:
            if isinstance(op, TextOp):
                batch.extend((op.text, self._tags(op.style)))
                if len(batch) > 1000:
                    flush()
            elif isinstance(op, MarkerOp):
                font = self._font(op.style)
                level = max(1, op.style.indent)
                label = op.text + " "
                toggle = f"{EXPANDED} " if op.fold is not None else ""
                hang = max(0, level * self.indent_px - font.measure(toggle + label))
                tag = self._tag(f"hang:{level}:{hang}", lmargin1=hang, lmargin2=level * self.indent_px)
                if toggle:
                    batch.extend((toggle, (tag, f"toggle:{op.fold}", "dim") + self._tags(op.style)[:1]))
                batch.extend((label, (tag,) + self._tags(op.style)[:1]))
            elif isinstance(op, FoldStartOp):
                flush()
                text.mark_set(f"fold{op.fold}", "end-1c")
                text.mark_gravity(f"fold{op.fold}", "left")
            elif isinstance(op, FoldEndOp):
                flush()
                text.tag_add(f"fold:{op.fold}", f"fold{op.fold}", "end-1c")
            elif isinstance(op, ImageOp):
                number = len(self.images)
                self.images.append((number, op))
                note = image_note(op)
                label = f"[Bild: {op.alt}]" if op.alt else "[Bild]"
                message = note or f"Bild wird geladen: {op.src}"
                tags = self._tags(op.style) + ("dim", f"img:{number}",
                                               self._info_tag(f"img:{number}", message))
                batch.extend((label, tags))
            elif isinstance(op, RuleOp):
                flush()
                rule = tk.Frame(text, height=2, background="#c8c8c8",
                                width=self.content_width() - op.style.indent * self.indent_px)
                rule.indent = op.style.indent  # type: ignore[attr-defined]
                text.window_create("end", window=rule, align="center")
                self._rules.append(rule)
            elif isinstance(op, AnchorOp):
                if op.name not in self._anchors:
                    flush()
                    mark = f"anchor{len(self._anchors)}"
                    text.mark_set(mark, "end-1c")
                    text.mark_gravity(mark, "left")
                    self._anchors[op.name] = mark
        flush()
        text.configure(state="disabled")
        text.yview_moveto(0)
        text.xview_moveto(0)

    def set_image(self, number: int, png: bytes) -> None:
        ranges = self.text.tag_ranges(f"img:{number}")
        if not ranges:
            return
        photo = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))
        self._photos.append(photo)
        start, end = ranges[0], ranges[1]
        tags = [t for t in self.text.tag_names(start) if not t.startswith(("info:", "dim"))]
        self.text.configure(state="normal")
        self.text.delete(start, end)
        self.text.image_create(start, image=photo, padx=1, pady=1)
        for tag in tags:
            self.text.tag_add(tag, start)
        self.text.configure(state="disabled")

    def image_failed(self, number: int, message: str) -> None:
        self._info_tag(f"img:{number}", message)

    def scroll_to(self, anchor: str) -> bool:
        mark = self._anchors.get(anchor)
        if mark is None:
            return False
        self.text.yview(mark)
        return True

    # -- Maus und Tastatur ------------------------------------------------------

    def toggle_fold(self, fold: str) -> None:
        """Klappt die Unterlisten eines Listeneintrags ein oder aus (fold = "toggle:N")."""
        number = fold.split(":", 1)[1]
        start = self.text.tag_ranges(fold)[0]
        collapsed = self.text.get(start) == EXPANDED
        tags = self.text.tag_names(start)
        self.text.tag_configure(f"fold:{number}", elide=collapsed)
        self.text.configure(state="normal")
        self.text.delete(start)
        self.text.insert(start, COLLAPSED if collapsed else EXPANDED, tags)
        self.text.configure(state="disabled")

    def _target(self, event: tk.Event) -> tuple[str | None, str | None]:
        """Liefert (Link oder Klappschalter, Hinweis) unter dem Mauszeiger."""
        index = self.text.index(f"@{event.x},{event.y}")
        box = self.text.bbox(index)
        if not box or not (box[0] <= event.x < box[0] + box[2] and box[1] <= event.y < box[1] + box[3]):
            return None, None
        url = info = None
        for tag in self.text.tag_names(index):
            if tag in self._hrefs:
                url = self._hrefs[tag]
            elif tag.startswith("toggle:"):
                url = tag
                info = "Unterliste ein- oder ausklappen"
            elif tag in self._infos:
                info = self._infos[tag]
        return url, info

    def _set_hover(self, message: str | None, is_link: bool = False) -> None:
        self.text.configure(cursor="hand2" if is_link else "xterm")
        if message != self._hover:
            self._hover = message
            self.on_hover(message)

    def _on_motion(self, event: tk.Event) -> None:
        url, info = self._target(event)
        message = info if url and url.startswith("toggle:") else url or info
        self._set_hover(message, is_link=url is not None)

    def _on_press(self, event: tk.Event) -> None:
        self.text.focus_set()
        self._pressed, _ = self._target(event)

    def _on_release(self, event: tk.Event) -> None:
        url, _ = self._target(event)
        if url and url == self._pressed and not self.text.tag_ranges("sel"):
            if url.startswith("toggle:"):
                self.toggle_fold(url)
            else:
                self.on_link(url)
        self._pressed = None

    def _on_resize(self, _event: tk.Event) -> None:
        width = self.content_width()
        for rule in self._rules:
            rule.configure(width=width - rule.indent * self.indent_px)  # type: ignore[attr-defined]

    def _on_key(self, event: tk.Event) -> str | None:
        keys = {"Up": "-1 units", "Down": "1 units", "Prior": "-1 pages", "Next": "1 pages",
                "space": "1 pages"}
        if event.keysym in keys:
            amount, unit = keys[event.keysym].split()
            self.text.yview_scroll(int(amount), unit)
            return "break"
        if event.keysym == "Home":
            self.text.yview_moveto(0)
            return "break"
        if event.keysym == "End":
            self.text.yview_moveto(1)
            return "break"
        return None
