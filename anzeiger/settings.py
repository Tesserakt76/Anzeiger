"""Dauerhafte Einstellungen (about:config), gespeichert als JSON-Datei."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def default_path() -> Path:
    """$XDG_CONFIG_HOME/anzeiger/settings.json, sonst ~/.config/anzeiger/settings.json."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "anzeiger" / "settings.json"


@dataclass
class Settings:
    cookies_enabled: bool = True       # Cookies annehmen und zurückschicken
    lists_collapsed: bool = False      # ganze Listen beim Laden eingeklappt
    sublists_collapsed: bool = False   # Unterlisten beim Laden eingeklappt

    @classmethod
    def load(cls, path: Path) -> Settings:
        """Liest die Einstellungen; fehlende, defekte oder unbekannte Werte → Standard."""
        settings = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return settings
        if isinstance(data, dict):
            for f in fields(cls):
                value = data.get(f.name)
                if isinstance(value, bool):
                    setattr(settings, f.name, value)
        return settings

    def save(self, path: Path) -> None:
        """Schreibt die Einstellungen atomar (erst temporäre Datei, dann umbenennen)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
