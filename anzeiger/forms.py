"""Formulare abschicken: Daten kodieren und die Anfrage bestimmen (ohne tkinter)."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit, urlunsplit

URLENCODED = "application/x-www-form-urlencoded"
MULTIPART = "multipart/form-data"
TEXT_PLAIN = "text/plain"

_NEWLINES = re.compile(r"\r\n|\r|\n")


@dataclass
class FormInfo:
    """Ein <form>-Element: Ziel, Methode und Kodierung."""
    action: str            # bereits aufgelöste Ziel-URL
    method: str = "get"    # "get" oder "post"
    enctype: str = URLENCODED
    id: str | None = None


@dataclass
class Submission:
    method: str            # "GET" oder "POST"
    url: str
    body: bytes | None = None
    content_type: str | None = None


def normalize_method(value: str | None) -> str:
    return "post" if (value or "").strip().lower() == "post" else "get"


def normalize_enctype(value: str | None) -> str:
    value = (value or "").strip().lower()
    return value if value in (MULTIPART, TEXT_PLAIN) else URLENCODED


def _crlf(text: str) -> str:
    return _NEWLINES.sub("\r\n", text)


def encode(entries: list[tuple[str, str]], enctype: str) -> tuple[bytes, str]:
    """Kodiert Name/Wert-Paare; liefert (Körper, Content-Type)."""
    entries = [(_crlf(name), _crlf(value)) for name, value in entries]
    if enctype == MULTIPART:
        boundary = "----AnzeigerFormBoundary" + secrets.token_hex(12)
        parts = []
        for name, value in entries:
            quoted = name.replace('"', "%22").replace("\r", "%0D").replace("\n", "%0A")
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{quoted}\"\r\n\r\n"
                         f"{value}\r\n".encode("utf-8"))
        parts.append(f"--{boundary}--\r\n".encode("ascii"))
        return b"".join(parts), f"{MULTIPART}; boundary={boundary}"
    if enctype == TEXT_PLAIN:
        body = "".join(f"{name}={value}\r\n" for name, value in entries)
        return body.encode("utf-8"), f"{TEXT_PLAIN}; charset=UTF-8"
    return urlencode(entries, encoding="utf-8").encode("ascii"), URLENCODED


def build_submission(action: str, method: str, enctype: str,
                     entries: list[tuple[str, str]]) -> Submission:
    """Bestimmt die Anfrage wie ein Browser: GET hängt die Daten als Query an."""
    if method == "post":
        body, content_type = encode(entries, enctype)
        return Submission("POST", action, body, content_type)
    parts = urlsplit(action)
    query = urlencode([(_crlf(n), _crlf(v)) for n, v in entries], encoding="utf-8")
    return Submission("GET", urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment)))

