import io
import unittest

from PIL import Image

from anzeiger import images, net


class NetTest(unittest.TestCase):
    def test_user_url(self):
        self.assertEqual(net.user_url("example.org"), "https://example.org")
        self.assertEqual(net.user_url(" http://a.b/ "), "http://a.b/")

    def test_only_http(self):
        self.assertTrue(net.is_supported("HTTPS://x"))
        for url in ("file:///etc/passwd", "ftp://x", "data:text/html,x", "javascript:x"):
            self.assertFalse(net.is_supported(url))
            with self.assertRaises(net.FetchError):
                net.fetch(url)

    def test_same_server(self):
        self.assertTrue(net.same_server("https://a.de/x", "http://A.de:8080/b.png"))
        self.assertTrue(net.same_server("https://www.a.de/x", "https://cdn.a.de/b.png"))
        self.assertTrue(net.same_server("https://a.co.uk/", "https://img.a.co.uk/b.png"))
        self.assertFalse(net.same_server("https://a.co.uk/", "https://b.co.uk/b.png"))
        self.assertFalse(net.same_server("https://a.de/x", "https://a.com/b.png"))
        self.assertFalse(net.same_server("http://10.0.0.1/", "http://10.0.0.2/b.png"))
        self.assertFalse(net.same_server("https://a.de/x", "data:image/png;base64,AAAA"))

    def test_normalize(self):
        self.assertEqual(net.normalize_url("http://bücher.de/a b?q=ä"),
                         "http://xn--bcher-kva.de/a%20b?q=%C3%A4")

    def test_decode_body(self):
        self.assertEqual(net.decode_body("ä".encode("utf-8"), None), "ä")
        self.assertEqual(net.decode_body("ä".encode("cp1252"), None), "ä")
        self.assertEqual(net.decode_body(b'<meta charset="iso-8859-1">\x80', None)[-1], "€")


class ImageTest(unittest.TestCase):
    def _png(self, size=(40, 20)) -> bytes:
        out = io.BytesIO()
        Image.new("RGB", size, "red").save(out, "PNG")
        return out.getvalue()

    def test_decode_and_scale(self):
        png, size = images.decode_image(self._png(), max_width=20)
        self.assertEqual(size, (20, 10))
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_attributes(self):
        self.assertEqual(images.target_size((40, 20), 80, None, 0), (80, 40))

    def test_reject_svg(self):
        with self.assertRaises(images.ImageError):
            images.decode_image(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')

    def test_reject_other_formats(self):
        out = io.BytesIO()
        Image.new("RGB", (4, 4)).save(out, "TIFF")
        with self.assertRaises(images.ImageError):
            images.decode_image(out.getvalue())


if __name__ == "__main__":
    unittest.main()
