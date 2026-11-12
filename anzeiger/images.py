"""Sicheres Dekodieren von Bildern in gängigen Rasterformaten.

Erlaubt sind nur PNG, JPEG, GIF, BMP und WebP (bei GIF nur das erste Bild).
SVG und andere Formate werden nicht geladen. Das Ergebnis wird als PNG
geliefert, weil Tk 8.6 PNG ohne Zusatzmodule anzeigen kann.
"""

from __future__ import annotations

import io

from PIL import Image

ALLOWED_FORMATS = ("PNG", "JPEG", "GIF", "BMP", "WEBP")
# Inhaltstypen, die als eigene Seite angezeigt werden (direkt aufgerufene Bildadresse)
CONTENT_TYPES = ("image/png", "image/jpeg", "image/pjpeg", "image/gif", "image/bmp",
                 "image/x-ms-bmp", "image/webp")
MAX_PIXELS = 40_000_000
MAX_HEIGHT = 4000

# Schutz vor "Dekompressionsbomben": Pillow bricht ab dem Doppelten mit Fehler ab,
# zusätzlich prüfen wir die Größe unten selbst.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageError(Exception):
    pass


def target_size(size: tuple[int, int], width: int | None, height: int | None,
                max_width: int) -> tuple[int, int]:
    """Bestimmt die Anzeigegröße aus Originalgröße, width/height-Attributen und Platz."""
    w, h = size
    if width and height:
        w, h = width, height
    elif width:
        w, h = width, max(1, round(h * width / w))
    elif height:
        w, h = max(1, round(w * height / h)), height
    if max_width > 0 and w > max_width:
        w, h = max_width, max(1, round(h * max_width / w))
    if h > MAX_HEIGHT:
        w, h = max(1, round(w * MAX_HEIGHT / h)), MAX_HEIGHT
    return w, h


def probe(data: bytes) -> tuple[str, tuple[int, int]]:
    """Liefert (Format, (Breite, Höhe)), ohne das Bild zu dekodieren."""
    try:
        image = Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS)
    except Exception as error:
        raise ImageError("kein unterstütztes Bildformat (PNG, JPEG, GIF, BMP, WebP)") from error
    return image.format or "?", image.size


def decode_image(data: bytes, width: int | None = None, height: int | None = None,
                 max_width: int = 0) -> tuple[bytes, tuple[int, int]]:
    """Dekodiert, skaliert und liefert (PNG-Daten, (Breite, Höhe))."""
    try:
        image = Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS)
    except Exception as error:  # Pillow wirft je nach Fehler verschiedene Typen
        raise ImageError("kein unterstütztes Bildformat (PNG, JPEG, GIF, BMP, WebP)") from error
    if image.width * image.height > MAX_PIXELS:
        raise ImageError(f"Bild zu groß ({image.width}×{image.height})")
    try:
        image.load()
    except Exception as error:
        raise ImageError(f"Bild beschädigt: {error}") from error
    has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")
    size = target_size(image.size, width, height, max_width)
    if size != image.size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", compress_level=1)
    return out.getvalue(), size
