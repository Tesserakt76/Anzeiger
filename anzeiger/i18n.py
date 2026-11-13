"""Übersetzungen aus Sprachdateien (TOML).

Die eingebauten Sprachdateien liegen in anzeiger/lang/<Kürzel>.toml. Eine gleichnamige
Datei in ~/.config/anzeiger/lang/ überschreibt einzelne oder alle Texte; dort lassen
sich auch ganz neue Sprachen ablegen. Fehlt ein Text in der gewählten Sprache, gilt
der englische, fehlt er auch dort, der deutsche (Deutsch ist vollständig).

Texte werden über Schlüssel wie "app.go" abgerufen ([app] → go = "Los"). Platzhalter
in geschweiften Klammern ({url}) werden beim Abruf ersetzt.
"""

from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path

from .settings import default_path as _settings_path

SOURCE = "de"     # vollständige Referenzsprache
FALLBACK = "en"   # für fehlende Texte und unbekannte Systemsprachen

Text = str | list[str]

_texts: dict[str, Text] | None = None
_language = SOURCE
errors: list[str] = []   # Fehler beim Lesen der Sprachdateien (für about:config)


def builtin_dir():
    return resources.files(__package__).joinpath("lang")


def user_dir() -> Path:
    """Liegt neben settings.json: ~/.config/anzeiger/lang/."""
    return _settings_path().with_name("lang")


def _flatten(table: dict, prefix: str = "") -> dict[str, Text]:
    result: dict[str, Text] = {}
    for name, value in table.items():
        key = prefix + name
        if isinstance(value, dict):
            result.update(_flatten(value, key + "."))
        elif isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            result[key] = value
    return result


def read(code: str, user: bool = True) -> dict[str, Text]:
    """Texte einer Sprache: eingebaute Datei, überlagert von der Datei im Benutzerordner."""
    texts: dict[str, Text] = {}
    sources = [builtin_dir().joinpath(f"{code}.toml")]
    if user:
        sources.append(user_dir() / f"{code}.toml")
    for source in sources:
        try:
            data = tomllib.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            message = f"{source}: {error}"
            if message not in errors:
                errors.append(message)
            continue
        texts.update(_flatten(data))
    return texts


def available() -> dict[str, str]:
    """Kürzel → Name aller Sprachen (eingebaute und eigene), nach Kürzel sortiert."""
    codes = {entry.name[:-5] for entry in builtin_dir().iterdir() if entry.name.endswith(".toml")}
    try:
        codes |= {path.stem for path in user_dir().glob("*.toml")}
    except OSError:
        pass
    return {code: str(read(code).get("meta.name", code)) for code in sorted(codes)}


def system_language() -> str:
    """Sprache aus LANGUAGE, LC_ALL, LC_MESSAGES oder LANG, sofern es sie gibt, sonst Englisch."""
    codes = available()
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        entries = [entry.split(".")[0].split("@")[0].split("_")[0].lower()
                   for entry in (os.environ.get(variable) or "").split(":") if entry]
        if entries:   # die erste gesetzte Variable entscheidet; LANGUAGE kann eine Liste sein ("de:en")
            return next((code for code in entries if code in codes), FALLBACK)
    return FALLBACK


def set_language(code: str) -> None:
    """Wählt die Sprache; leeres Kürzel = Systemsprache."""
    global _texts, _language
    code = code or system_language()
    errors.clear()
    texts: dict[str, Text] = {}
    for layer in [lang for lang in (SOURCE, FALLBACK) if lang != code] + [code]:
        texts.update(read(layer))
    _texts, _language = texts, code


def language() -> str:
    return _language


def _get(key: str) -> Text | None:
    if _texts is None:
        set_language(SOURCE)
    assert _texts is not None
    return _texts.get(key)


def t(key: str, **values: object) -> str:
    """Text zum Schlüssel mit eingesetzten Platzhaltern; unbekannter Schlüssel → der Schlüssel selbst."""
    text = _get(key)
    if not isinstance(text, str):
        return key
    if not values:
        return text
    try:
        return text.format_map(values)
    except (KeyError, ValueError, IndexError):   # Tippfehler in einer Sprachdatei
        return text


def tn(key: str, count: int, **values: object) -> str:
    """Einzahl (key.one) oder Mehrzahl (key.other) passend zu `count`, das als {count} eingesetzt wird."""
    return t(f"{key}.{'one' if count == 1 else 'other'}", count=count, **values)


def tl(key: str) -> list[str]:
    """Eine Liste von Texten (z.B. eine Tabellenzeile)."""
    text = _get(key)
    if isinstance(text, list):
        return text
    return [key] if text is None else [text]


def keys(*parts: str) -> str:
    """Tastenkürzel in der gewählten Sprache: keys("ctrl", "W") → "Strg+W"."""
    names = {"ctrl", "shift", "alt"}
    return "+".join(t(f"keys.{part}") if part in names else part for part in parts)
