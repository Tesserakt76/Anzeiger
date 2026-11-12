import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from anzeiger import forms, net, pages
from anzeiger.settings import Settings


class _Handler(BaseHTTPRequestHandler):
    received: list[tuple[str, str, str | None, bytes]] = []

    def _reply(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        if self.path.startswith("/set"):
            self.send_header("Set-Cookie", "sitzung=abc; Path=/")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self.received.append(("GET", self.path, self.headers.get("Cookie"), b""))
        self._reply(b"ok")

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.received.append(("POST", self.path, self.headers.get("Origin"), body))
        self._reply(b"posted")

    def log_message(self, *args) -> None:
        pass


class CookieTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.received.clear()
        net.set_cookies_enabled(True)
        net.clear_cookies()

    def tearDown(self):
        net.set_cookies_enabled(True)
        net.clear_cookies()

    def last_cookie(self):
        return _Handler.received[-1][2]

    def test_cookie_stored_and_sent(self):
        net.fetch(self.base + "/set")
        self.assertEqual(net.cookie_hosts(), {"127.0.0.1": 1})
        net.fetch(self.base + "/weiter")
        self.assertEqual(self.last_cookie(), "sitzung=abc")

    def test_clear_cookies(self):
        net.fetch(self.base + "/set")
        net.clear_cookies()
        net.fetch(self.base + "/weiter")
        self.assertIsNone(self.last_cookie())
        self.assertEqual(net.cookie_hosts(), {})

    def test_disabled_cookies(self):
        net.fetch(self.base + "/set")
        net.set_cookies_enabled(False)
        self.assertEqual(net.cookie_hosts(), {})
        net.fetch(self.base + "/set")
        net.fetch(self.base + "/weiter")
        self.assertIsNone(self.last_cookie())
        self.assertEqual(net.cookie_hosts(), {})

    def test_third_party_cookies_blocked(self):
        # Nachgeladen für eine Seite einer anderen Domain: nicht setzen …
        net.fetch(self.base + "/set", first_party="https://andere-seite.example/")
        self.assertEqual(net.cookie_hosts(), {})
        # … und vorhandene Cookies auch nicht mitschicken.
        net.fetch(self.base + "/set")
        net.fetch(self.base + "/bild.png", first_party="https://andere-seite.example/")
        self.assertIsNone(self.last_cookie())
        # Für eine Seite derselben Domain schon.
        net.fetch(self.base + "/bild.png", first_party=self.base + "/seite.html")
        self.assertEqual(self.last_cookie(), "sitzung=abc")

    def test_post(self):
        body, ctype = forms.encode([("name", "Jörg & Co")], forms.URLENCODED)
        response = net.fetch(self.base + "/form", data=body, content_type=ctype,
                             from_page="https://example.org/seite?x=1")
        self.assertEqual(response.body, b"posted")
        method, path, origin, received = _Handler.received[-1]
        self.assertEqual((method, path, origin), ("POST", "/form", "https://example.org"))
        self.assertEqual(received, b"name=J%C3%B6rg+%26+Co")


class FormEncodingTest(unittest.TestCase):
    def test_get_replaces_query(self):
        sub = forms.build_submission("https://a.de/s?alt=1#oben", "get", forms.URLENCODED,
                                     [("q", "a b"), ("x", "1\n2")])
        self.assertEqual((sub.method, sub.url, sub.body), ("GET", "https://a.de/s?q=a+b&x=1%0D%0A2#oben", None))

    def test_multipart(self):
        body, ctype = forms.encode([('a"b', "x\ny")], forms.MULTIPART)
        boundary = ctype.split("boundary=", 1)[1]
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))
        self.assertEqual(body.decode(), f'--{boundary}\r\nContent-Disposition: form-data; name="a%22b"\r\n\r\n'
                                        f"x\r\ny\r\n--{boundary}--\r\n")

    def test_text_plain_and_normalizing(self):
        self.assertEqual(forms.encode([("a", "1")], forms.TEXT_PLAIN)[0], b"a=1\r\n")
        self.assertEqual(forms.normalize_method(" POST "), "post")
        self.assertEqual(forms.normalize_method("dialog"), "get")
        self.assertEqual(forms.normalize_enctype("TEXT/PLAIN"), forms.TEXT_PLAIN)
        self.assertEqual(forms.normalize_enctype("quatsch"), forms.URLENCODED)


class SettingsTest(unittest.TestCase):
    def test_defaults_roundtrip_and_broken_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unter" / "settings.json"
            self.assertEqual(Settings.load(path), Settings(True, False, False))
            Settings(cookies_enabled=False, lists_collapsed=True).save(path)
            self.assertEqual(Settings.load(path), Settings(False, True, False))
            path.write_text('{"cookies_enabled": "nein", "sublists_collapsed": true, "x": 1}')
            self.assertEqual(Settings.load(path), Settings(True, False, True))
            path.write_text("kaputt")
            self.assertEqual(Settings.load(path), Settings())

    def test_config_page_reflects_settings(self):
        ctx = pages.PageContext(Settings(lists_collapsed=True), Path("/x/settings.json"),
                                {"a.de": 2, "<b>.de": 1}, "Gespeichert.")
        source = pages.internal_page("about:config", ctx)
        self.assertIn('name="cookies" value="on" checked', source)
        self.assertIn('name="lists" value="on" checked', source)
        self.assertNotIn('name="sublists" value="on" checked', source)
        self.assertIn("3 Cookies von 2 Domains", source)
        self.assertIn("&lt;b&gt;.de", source)
        self.assertIn("/x/settings.json", source)
        self.assertIn('value="clear-cookies"', source)
        self.assertIn("about:config", pages.START_PAGE)


if __name__ == "__main__":
    unittest.main()
