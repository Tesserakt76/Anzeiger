"""HTTP/HTTPS-Zugriff. Andere Protokolle (file:, ftp:, data: …) werden abgelehnt."""

from __future__ import annotations

import codecs
import http.cookiejar
import ipaddress
import re
import ssl
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from urllib.parse import quote, urlsplit, urlunsplit

from . import __version__
from .i18n import t

TIMEOUT = 20
MAX_PAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
USER_AGENT = f"Anzeiger/{__version__} (einfacher Textbrowser)"
ALLOWED_SCHEMES = ("http", "https")
VIEW_SOURCE = "view-source:"   # vor einer http(s)-Adresse: Quelltext der Seite zeigen
_accept_language = "de,en;q=0.7"


class FetchError(Exception):
    pass


class InsecureRedirect(FetchError):
    """Eine HTTPS-Adresse leitet auf eine unverschlüsselte HTTP-Adresse weiter."""

    def __init__(self, url: str) -> None:
        super().__init__(t("net.insecure_redirect", url=url))
        self.url = url


@dataclass
class Response:
    url: str
    status: int
    reason: str
    content_type: str
    charset: str | None
    body: bytes


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = 10

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme.lower() not in ALLOWED_SCHEMES:
            raise FetchError(t("net.redirect_unsupported", url=newurl))
        if is_downgrade(req.full_url, newurl):
            raise InsecureRedirect(newurl)
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            # Nachgeladene Inhalte bleiben auch nach einer Weiterleitung nachgeladen.
            new.first_party = getattr(req, "first_party", None)
        return new


class CookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """Cookies nur für die besuchte Seite selbst, keine Drittanbieter-Cookies.

    Seitenaufrufe (first_party = None) sind immer Erstanbieter. Nachgeladene Inhalte
    (Bilder) tragen die Adresse der Seite als `first_party`; ihre Cookies werden nur
    gesetzt und geschickt, wenn sie zur selben Domain gehören.
    """

    def __init__(self) -> None:
        super().__init__()
        self.enabled = True

    def _allowed(self, request) -> bool:
        if not self.enabled:
            return False
        first_party = getattr(request, "first_party", None)
        return first_party is None or same_server(first_party, request.get_full_url())

    def set_ok(self, cookie, request) -> bool:
        return self._allowed(request) and super().set_ok(cookie, request)

    def return_ok(self, cookie, request) -> bool:
        return self._allowed(request) and super().return_ok(cookie, request)


# Cookies liegen nur im Arbeitsspeicher und sind beim Beenden verloren.
COOKIE_POLICY = CookiePolicy()
COOKIES = http.cookiejar.CookieJar(policy=COOKIE_POLICY)


def set_cookies_enabled(enabled: bool) -> None:
    """Schaltet Cookies ein oder aus; beim Ausschalten werden alle gelöscht."""
    COOKIE_POLICY.enabled = enabled
    if not enabled:
        COOKIES.clear()


def clear_cookies() -> None:
    COOKIES.clear()


def set_accept_language(code: str) -> None:
    """Bevorzugte Sprache der Webseiten (Accept-Language), mit Englisch als zweiter Wahl."""
    global _accept_language
    _accept_language = "en" if code == "en" else f"{code},en;q=0.7"


def cookie_hosts() -> dict[str, int]:
    """Anzahl gespeicherter Cookies je Domain, sortiert."""
    counts: dict[str, int] = {}
    for cookie in COOKIES:
        domain = cookie.domain.lstrip(".")
        counts[domain] = counts.get(domain, 0) + 1
    return dict(sorted(counts.items()))


def _build_opener() -> urllib.request.OpenerDirector:
    # Bewusst kein build_opener(): der würde auch file:, ftp: und data: zulassen.
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.ProxyHandler(),
        urllib.request.UnknownHandler(),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        urllib.request.HTTPDefaultErrorHandler(),
        _RedirectHandler(),
        urllib.request.HTTPCookieProcessor(COOKIES),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    return opener


_OPENER = _build_opener()


def is_supported(url: str) -> bool:
    return urlsplit(url).scheme.lower() in ALLOWED_SCHEMES


# Zweite Ebenen unter Länderkennungen, unter denen Domains vergeben werden
# (z.B. beispiel.co.uk). Ersetzt näherungsweise die Public Suffix List.
_SECOND_LEVEL = frozenset({
    "co", "com", "org", "net", "gov", "edu", "ac", "or", "ne", "go", "gv",
    "ltd", "plc", "nic", "mil", "sch", "gob", "gouv", "nom",
})


def site_domain(host: str) -> str:
    """Liefert die registrierte Domain eines Rechnernamens (www.a.de → a.de)."""
    host = host.lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    labels = host.split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_downgrade(from_url: str, to_url: str) -> bool:
    """True, wenn der Schritt von `from_url` nach `to_url` die Verschlüsselung verliert."""
    return urlsplit(from_url).scheme.lower() == "https" and urlsplit(to_url).scheme.lower() == "http"


def same_server(url_a: str, url_b: str) -> bool:
    """True, wenn beide URLs per HTTP(S) zur selben Domain (inkl. Subdomains) gehören."""
    a, b = urlsplit(url_a).hostname, urlsplit(url_b).hostname
    return (is_supported(url_a) and is_supported(url_b)
            and a is not None and b is not None and site_domain(a) == site_domain(b))


def without_fragment(url: str) -> str:
    return url.split("#", 1)[0]


def source_target(url: str) -> str | None:
    """Die Adresse hinter „view-source:“, falls es eine http(s)-Adresse ist, sonst None."""
    if url[:len(VIEW_SOURCE)].lower() != VIEW_SOURCE:
        return None
    target = url[len(VIEW_SOURCE):]
    return target if is_supported(target) else None


def user_url(text: str) -> str:
    """Macht aus einer Benutzereingabe eine vollständige URL (Standard: https)."""
    text = text.strip()
    if text[:len(VIEW_SOURCE)].lower() == VIEW_SOURCE:
        return VIEW_SOURCE + user_url(text[len(VIEW_SOURCE):])
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        text = "https://" + text
    return text


def normalize_url(url: str) -> str:
    """Kodiert Leerzeichen/Umlaute in Pfad und Query sowie internationale Domainnamen."""
    parts = urlsplit(url.strip())
    netloc = parts.netloc
    host = parts.hostname or ""
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        ascii_host = host
    if ascii_host != host:
        netloc = netloc.replace(host, ascii_host) if host in netloc else ascii_host
    safe = "/%:@!$&'()*+,;=~-._"
    return urlunsplit((
        parts.scheme.lower(), netloc,
        quote(parts.path, safe=safe),
        quote(parts.query, safe=safe + "?"),
        quote(parts.fragment, safe=safe + "?#"),
    ))


def origin(url: str) -> str | None:
    parts = urlsplit(url)
    if not is_supported(url) or not parts.hostname:
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def fetch(url: str, accept: str = "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
          max_bytes: int = MAX_PAGE_BYTES, *, data: bytes | None = None,
          content_type: str | None = None, from_page: str | None = None,
          first_party: str | None = None) -> Response:
    """Führt ein HTTP GET aus, mit `data` ein POST (Formular).

    HTTP-Fehlerseiten (404 …) werden als Antwort geliefert. `from_page` ist die Seite,
    deren Formular abgeschickt wird (für den Origin-Kopf); `first_party` die Seite,
    für die ein Inhalt nachgeladen wird (Drittanbieter-Cookies).
    """
    if not is_supported(url):
        raise FetchError(t("net.only_http"))
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": _accept_language,
    }
    if data is not None:
        headers["Content-Type"] = content_type or "application/x-www-form-urlencoded"
        page_origin = origin(from_page) if from_page else None
        headers["Origin"] = page_origin or "null"
    request = urllib.request.Request(normalize_url(url), data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
    request.first_party = first_party
    try:
        response = _OPENER.open(request, timeout=TIMEOUT)
    except urllib.error.HTTPError as error:
        response = error
    except urllib.error.URLError as error:
        raise FetchError(t("net.connection_failed", error=error.reason)) from error
    except (OSError, ValueError) as error:
        raise FetchError(t("net.connection_failed", error=error)) from error

    with response:
        headers = response.headers
        try:
            body = _read_limited(response, max_bytes)
        except OSError as error:
            raise FetchError(t("net.read_failed", error=error)) from error
        body = _decode_content(body, (headers.get("Content-Encoding") or "").lower(), max_bytes)
        return Response(
            url=response.geturl(),
            status=getattr(response, "status", None) or response.code,
            reason=str(getattr(response, "reason", "") or ""),
            content_type=headers.get_content_type(),
            charset=headers.get_content_charset(),
            body=body,
        )


def _read_limited(response, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while chunk := response.read(64 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise FetchError(t("net.too_large", mb=max_bytes // (1024 * 1024)))
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_content(body: bytes, encoding: str, max_bytes: int) -> bytes:
    if encoding in ("gzip", "x-gzip"):
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif encoding == "deflate":
        # "deflate" kommt in freier Wildbahn mit und ohne zlib-Kopf vor.
        decompressor = zlib.decompressobj(zlib.MAX_WBITS if body[:1] == b"\x78" else -zlib.MAX_WBITS)
    else:
        return body
    try:
        data = decompressor.decompress(body, max_bytes + 1)
    except zlib.error as error:
        raise FetchError(t("net.unpack_failed", error=error)) from error
    if len(data) > max_bytes:
        raise FetchError(t("net.unpacked_too_large"))
    return data


_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_.:-]+)""", re.I)

# Wie in Browsern üblich: Latin-1-Angaben als Windows-1252 interpretieren.
_CHARSET_ALIASES = {"iso-8859-1": "cp1252", "latin1": "cp1252", "latin-1": "cp1252",
                    "us-ascii": "cp1252", "ascii": "cp1252"}


def decode_body(body: bytes, declared: str | None) -> str:
    """Wandelt den Antwortkörper anhand von BOM, HTTP-Kopf oder <meta charset> in Text."""
    for bom, encoding in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"),
                          (codecs.BOM_UTF16_BE, "utf-16")):
        if body.startswith(bom):
            return body.decode(encoding, errors="replace")
    candidates = []
    if declared:
        candidates.append(declared)
    match = _META_CHARSET.search(body[:4096])
    if match:
        candidates.append(match.group(1).decode("ascii", "ignore"))
    for name in candidates:
        name = _CHARSET_ALIASES.get(name.strip().lower(), name.strip().lower())
        try:
            codecs.lookup(name)
        except LookupError:
            continue
        return body.decode(name, errors="replace")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("cp1252", errors="replace")
