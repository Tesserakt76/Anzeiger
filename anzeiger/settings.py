"""Dauerhafte Einstellungen (about:config), gespeichert als JSON-Datei."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# Stufen der Lupe in Prozent (wie in gängigen Browsern)
ZOOM_LEVELS = (50, 67, 80, 90, 100, 110, 120, 133, 150, 170, 200, 240, 300)


def default_path() -> Path:
    """$XDG_CONFIG_HOME/anzeiger/settings.json, sonst ~/.config/anzeiger/settings.json."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "anzeiger" / "settings.json"


@dataclass
class Settings:
    cookies_enabled: bool = True       # Cookies annehmen und zurückschicken
    lists_collapsed: bool = False      # ganze Listen beim Laden eingeklappt
    sublists_collapsed: bool = False   # Unterlisten beim Laden eingeklappt
    hidden_collapsed: bool = True      # per style versteckte Inhalte eingeklappt statt offen
    zoom: int = 100                    # Vergrößerung der Lupe in Prozent
    language: str = ""                 # Kürzel der Sprachdatei, "" = Systemsprache

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
                if type(value) is type(getattr(settings, f.name)):   # bool ist kein int
                    setattr(settings, f.name, value)
        if settings.zoom not in ZOOM_LEVELS:
            settings.zoom = zoom_step(settings.zoom, 0)
        return settings

    def save(self, path: Path) -> None:
        """Schreibt die Einstellungen atomar (erst temporäre Datei, dann umbenennen)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def zoom_step(current: int, step: int) -> int:
    """Nächste (step=1) bzw. vorige (step=-1) Zoomstufe; step=0 rundet auf die nächstgelegene."""
    nearest = min(range(len(ZOOM_LEVELS)), key=lambda i: abs(ZOOM_LEVELS[i] - current))
    return ZOOM_LEVELS[max(0, min(nearest + step, len(ZOOM_LEVELS) - 1))]
