"""Darstellung der Layout-Anweisungen in einem tkinter-Textfeld."""

from __future__ import annotations

import base64
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from tkinter import ttk

from .layout import (TEXT_KINDS, AnchorOp, FieldOp, FoldEndOp, FoldStartOp, ImageOp, ListToggleOp,
                     MarkerOp, Page, RuleOp, Style, TextOp)

EXPANDED = "\u25be"   # ▾
COLLAPSED = "\u25b8"  # ▸

LINK_COLOR = "#1a0dab"
DIM_COLOR = "#6b6b6b"
BACKGROUND = "#ffffff"
FOREGROUND = "#1b1b1b"
PAD_X = 18

Entries = list[tuple[str, str]]
# on_submit(Formular-Index oder None, auslösender Knopf oder None, Name/Wert-Paare)
SubmitCallback = Callable[[int | None, FieldOp | None, Entries], None]


class _Field:
    """Ein angezeigtes Formularfeld mit Zugriff auf seinen aktuellen Wert."""

    def __init__(self, op: FieldOp) -> None:
        self.op = op
        self.widget: tk.Widget | None = None
        self.entries: Callable[[FieldOp | None], Entries] = lambda _submitter: []
        self.reset: Callable[[], None] = lambda: None


class PageView(ttk.Frame):
    def __init__(self, master: tk.Misc, on_link: Callable[[str], None],
                 on_hover: Callable[[str | None], None], on_submit: SubmitCallback) -> None:
        super().__init__(master)
        self.on_link = on_link
        self.on_hover = on_hover
        self.on_submit = on_submit

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
        self._fields: list[_Field] = []
        self._radio_groups: dict[tuple, tuple[tk.StringVar, str]] = {}
        self._fold_kinds: dict[str, str] = {}

        style = ttk.Style(self)
        for name in ("TCheckbutton", "TRadiobutton"):
            style.configure("Page." + name, background=BACKGROUND)
        style.configure("Placeholder.TEntry", foreground=DIM_COLOR)

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
        for f in self._fields:
            if f.widget is not None:
                f.widget.destroy()
        self._fields.clear()
        self._radio_groups.clear()
        self._fold_kinds.clear()
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

    def show(self, page: Page, image_note: Callable[[ImageOp], str | None],
             collapse_lists: bool = False, collapse_sublists: bool = False) -> None:
        """Zeigt eine Seite an. `image_note` liefert für nicht ladbare Bilder den Grund.

        `collapse_lists`/`collapse_sublists`: ganze Listen bzw. Unterlisten eingeklappt zeigen.
        """
        self.clear()
        collapsed = {"list": collapse_lists, "sublist": collapse_sublists}
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
                symbol = COLLAPSED if collapse_sublists else EXPANDED
                toggle = f"{symbol} " if op.fold is not None else ""
                hang = max(0, level * self.indent_px - font.measure(toggle + label))
                tag = self._tag(f"hang:{level}:{hang}", lmargin1=hang, lmargin2=level * self.indent_px)
                if toggle:
                    batch.extend((toggle, (tag, f"toggle:{op.fold}", "dim") + self._tags(op.style)[:1]))
                batch.extend((label, (tag,) + self._tags(op.style)[:1]))
            elif isinstance(op, ListToggleOp):
                symbol = COLLAPSED if collapse_lists else EXPANDED
                tags = self._tags(op.style)
                toggle = f"toggle:{op.fold}"
                batch.extend((f"{symbol} ", tags + (toggle, "dim"), op.label, tags + (toggle,), "\n", tags))
            elif isinstance(op, FoldStartOp):
                flush()
                self._fold_kinds[str(op.fold)] = op.kind
                text.mark_set(f"fold{op.fold}", "end-1c")
                text.mark_gravity(f"fold{op.fold}", "left")
            elif isinstance(op, FoldEndOp):
                flush()
                text.tag_add(f"fold:{op.fold}", f"fold{op.fold}", "end-1c")
                if collapsed.get(self._fold_kinds.get(str(op.fold), "sublist")):
                    text.tag_configure(f"fold:{op.fold}", elide=True)
            elif isinstance(op, FieldOp):
                flush()
                self._add_field(op)
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

    # -- Formularfelder ---------------------------------------------------------

    def _add_field(self, op: FieldOp) -> None:
        field = _Field(op)
        self._fields.append(field)
        if op.kind == "hidden":
            field.entries = lambda _s: [(op.name, op.value)] if op.name else []
            return
        widget = self._make_widget(field)
        field.widget = widget
        if op.disabled:
            try:
                widget.configure(state="disabled")
            except tk.TclError:
                pass
            field.entries = lambda _s: []
        self.text.window_create("end", window=widget, align="baseline", padx=1)
        index = self.text.index("end-2c")
        for tag in self._tags(op.style):
            self.text.tag_add(tag, index)

    def _make_widget(self, field: _Field) -> tk.Widget:
        op, text = field.op, self.text
        kind = op.kind
        if kind in TEXT_KINDS:
            return self._make_entry(field)
        if kind == "checkbox":
            var = tk.BooleanVar(value=op.checked)
            field.entries = lambda _s: [(op.name, op.value)] if op.name and var.get() else []
            field.reset = lambda: var.set(op.checked)
            return ttk.Checkbutton(text, variable=var, style="Page.TCheckbutton", takefocus=True)
        if kind == "radio":
            key = (op.form, op.name) if op.name else ("ohne Namen", len(self._fields))
            var, _initial = self._radio_groups.get(key, (None, ""))
            if var is None:
                var = tk.StringVar(value="")
            own = str(len(self._fields))
            if op.checked:
                var.set(own)
            self._radio_groups[key] = (var, var.get())
            field.entries = lambda _s: [(op.name, op.value)] if op.name and var.get() == own else []
            field.reset = lambda: var.set(self._radio_groups[key][1])
            return ttk.Radiobutton(text, variable=var, value=own, style="Page.TRadiobutton")
        if kind in ("submit", "image"):
            def entries(submitter: FieldOp | None) -> Entries:
                if submitter is not op:
                    return []
                if kind == "image":
                    prefix = op.name + "." if op.name else ""
                    return [(prefix + "x", "0"), (prefix + "y", "0")]
                return [(op.name, op.value)] if op.name else []
            field.entries = entries
            return ttk.Button(text, text=op.label, command=lambda: self.submit(op.form, op))
        if kind == "reset":
            return ttk.Button(text, text=op.label, command=lambda: self.reset_form(op.form))
        if kind == "file":
            field.entries = lambda _s: [(op.name, "")] if op.name else []
            button = ttk.Button(text, text="Datei wählen …")
            button.state(["disabled"])
            return button
        if kind == "select":
            return self._make_select(field)
        if kind == "textarea":
            box = tk.Text(text, width=op.size, height=op.rows, wrap="word", font=self.base_font,
                          borderwidth=1, relief="solid", highlightthickness=1, undo=True)
            box.insert("1.0", op.value)
            if op.readonly:
                box.configure(state="disabled")
            box.bind("<Tab>", self._focus_next)

            def reset() -> None:
                state = box.cget("state")
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.insert("1.0", op.value)
                box.configure(state=state)
            field.entries = lambda _s: [(op.name, box.get("1.0", "end-1c"))] if op.name else []
            field.reset = reset
            return box
        # type="button" (nur mit JavaScript sinnvoll)
        button = ttk.Button(text, text=op.label or "Knopf")
        button.state(["disabled"])
        return button

    def _make_entry(self, field: _Field) -> ttk.Entry:
        op = field.op
        var = tk.StringVar(value=op.value)
        entry = ttk.Entry(self.text, textvariable=var, width=op.size, font=self.base_font,
                          show="\u2022" if op.kind == "password" else "")
        placeholder = {"active": False}

        def show_placeholder() -> None:
            try:
                focused = self.focus_get() is entry
            except (KeyError, tk.TclError):
                focused = False
            if op.placeholder and not var.get() and op.kind != "password" and not focused:
                placeholder["active"] = True
                var.set(op.placeholder)
                entry.configure(style="Placeholder.TEntry")

        def hide_placeholder(_event: tk.Event | None = None) -> None:
            if placeholder["active"]:
                placeholder["active"] = False
                var.set("")
                entry.configure(style="TEntry")

        def reset() -> None:
            hide_placeholder()
            var.set(op.value)
            show_placeholder()

        entry.bind("<FocusIn>", hide_placeholder)
        entry.bind("<FocusOut>", lambda _e: show_placeholder())
        entry.bind("<Return>", lambda _e: self.submit(op.form, self._default_button(op.form)))
        entry.bind("<KP_Enter>", lambda _e: self.submit(op.form, self._default_button(op.form)))
        if op.readonly:
            entry.state(["readonly"])
        show_placeholder()
        field.entries = lambda _s: [(op.name, "" if placeholder["active"] else var.get())] if op.name else []
        field.reset = reset
        return entry

    def _make_select(self, field: _Field) -> tk.Widget:
        op = field.op
        labels = [o.label for o in op.options]
        if op.multiple:
            box = tk.Listbox(self.text, selectmode="multiple", exportselection=False,
                             height=max(1, min(len(labels), op.size, 10)), font=self.base_font,
                             width=min(max((len(x) for x in labels), default=10) + 2, 50))
            box.insert("end", *labels)

            def reset() -> None:
                box.selection_clear(0, "end")
                for i, o in enumerate(op.options):
                    if o.selected:
                        box.selection_set(i)

            reset()
            field.entries = lambda _s: [(op.name, op.options[i].value) for i in box.curselection()
                                        if not op.options[i].disabled] if op.name else []
            field.reset = reset
            return box
        combo = ttk.Combobox(self.text, values=labels, state="readonly", font=self.base_font,
                             width=min(max((len(x) for x in labels), default=10) + 2, 50))
        initial = next((i for i, o in enumerate(op.options) if o.selected), -1)

        def reset() -> None:
            if initial >= 0:
                combo.current(initial)

        reset()

        def entries(_s: FieldOp | None) -> Entries:
            i = combo.current()
            if not op.name or i < 0 or op.options[i].disabled:
                return []
            return [(op.name, op.options[i].value)]

        field.entries = entries
        field.reset = reset
        return combo

    @staticmethod
    def _focus_next(event: tk.Event) -> str:
        """Tab im Textbereich wechselt zum nächsten Feld statt ein Tabzeichen einzufügen."""
        following = event.widget.tk_focusNext()
        if following is not None:
            following.focus_set()
        return "break"

    def _default_button(self, form: int | None) -> FieldOp | None:
        """Erster Absendeknopf des Formulars (für Enter in einem Textfeld)."""
        for f in self._fields:
            if f.op.form == form and f.op.kind in ("submit", "image"):
                return f.op
        return None

    def form_entries(self, form: int | None, submitter: FieldOp | None) -> Entries:
        """Name/Wert-Paare eines Formulars in Dokumentreihenfolge."""
        result: Entries = []
        for f in self._fields:
            if f.op.form == form and not f.op.disabled:
                result.extend(f.entries(submitter))
        return result

    def submit(self, form: int | None, submitter: FieldOp | None) -> None:
        if submitter is not None and submitter.disabled:
            return
        self.on_submit(form, submitter, self.form_entries(form, submitter) if form is not None else [])

    def reset_form(self, form: int | None) -> None:
        if form is None:
            return
        for f in self._fields:
            if f.op.form == form:
                f.reset()

    # -- Maus und Tastatur ------------------------------------------------------

    def toggle_fold(self, fold: str) -> None:
        """Klappt eine Liste bzw. die Unterlisten eines Eintrags ein oder aus (fold = "toggle:N")."""
        number = fold.split(":", 1)[1]
        start = self.text.tag_ranges(fold)[0]
        collapsed = self.text.get(start) == EXPANDED
        tags = self.text.tag_names(start)
        # Beim Ausklappen die Option entfernen statt elide=False zu setzen: sonst würde
        # der Bereich auch innerhalb einer eingeklappten äußeren Liste sichtbar.
        self.text.tag_configure(f"fold:{number}", elide=True if collapsed else "")
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
                kind = self._fold_kinds.get(tag.split(":", 1)[1])
                info = "Liste ein- oder ausklappen" if kind == "list" else "Unterliste ein- oder ausklappen"
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
