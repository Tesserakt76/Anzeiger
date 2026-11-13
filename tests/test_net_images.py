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
        data, size = images.decode_image(self._png(), max_width=20)
        self.assertEqual(size, (20, 10))
        self.assertTrue(data.startswith(b"P6"))
        self.assertEqual(Image.open(io.BytesIO(data)).size, (20, 10))

    def test_transparency_on_white(self):
        out = io.BytesIO()
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(out, "PNG")
        data, _size = images.decode_image(out.getvalue())
        self.assertEqual(Image.open(io.BytesIO(data)).getpixel((1, 1)), (255, 255, 255))

    def test_attributes(self):
        self.assertEqual(images.target_size((40, 20), 20, None, 0), (20, 10))
        self.assertEqual(images.target_size((40, 20), None, 5, 0), (10, 5))
        # Attribute vergrößern nicht: Originalfoto 4000×2667 angegeben, ausgeliefert 422×316
        self.assertEqual(images.target_size((422, 316), 4000, 2667, 1000), (422, 316))
        self.assertEqual(images.target_size((40, 20), 80, None, 0), (40, 20))

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


class ImagePageTest(unittest.TestCase):
    """Direkt aufgerufene Bildadressen werden als eigene Seite angezeigt."""

    def response(self, body: bytes, ctype: str = "image/jpeg", status: int = 200) -> net.Response:
        return net.Response("https://a.de/fotos/Gr%C3%BCn.jpg", status, "OK", ctype, None, body)

    def jpeg(self, size=(1200, 600)) -> bytes:
        out = io.BytesIO()
        Image.new("RGB", size, "green").save(out, "JPEG")
        return out.getvalue()

    def test_jpeg_page(self):
        from anzeiger.app import Tab
        from anzeiger.layout import ImageOp
        page = Tab._build_page(self.response(self.jpeg()), 100, 600)
        self.assertEqual(page.title, "Grün.jpg (1200×600)")
        image_ops = [op for op in page.ops if isinstance(op, ImageOp)]
        self.assertEqual([op.src for op in image_ops], ["https://a.de/fotos/Gr%C3%BCn.jpg"])
        data = page.preloaded[image_ops[0].src]
        self.assertEqual(Image.open(io.BytesIO(data)).size, (600, 300))
        text = "".join(getattr(op, "text", "") for op in page.ops)
        self.assertIn("JPEG, 1200×600 Pixel – verkleinert auf 600×300", text)
        self.assertTrue(net.same_server(page.url, image_ops[0].src))

    def test_broken_or_unsupported(self):
        from anzeiger.app import Tab
        page = Tab._build_page(self.response(b"kein Bild"), 100, 600)
        self.assertEqual(page.title, "Fehler")
        self.assertEqual(page.preloaded, {})
        page = Tab._build_page(self.response(b"<svg/>", "image/svg+xml"), 100, 600)
        self.assertEqual(page.title, "Fehler")
        self.assertEqual(images.probe(self.jpeg((3, 2))), ("JPEG", (3, 2)))
