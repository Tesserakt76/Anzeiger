"""Notizen (about:notes), gespeichert als reine Textdatei."""

from __future__ import annotations

import os
from pathlib import Path

from .settings import default_path as _settings_path


def default_path() -> Path:
    """Liegt neben settings.json: ~/.config/anzeiger/notes.txt."""
    return _settings_path().with_name("notes.txt")


def load(path: Path) -> str:
    """Liest die Notizen; fehlt die Datei, sind sie leer."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def save(path: Path, text: str) -> None:
    """Schreibt atomar (erst temporäre Datei, dann umbenennen)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
