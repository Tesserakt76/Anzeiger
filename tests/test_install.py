import configparser
import struct
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "anzeiger" / "icons"
SIZES = (16, 24, 32, 48, 64, 128, 256)


class InstallFilesTest(unittest.TestCase):
    def test_icons_exist_with_right_size(self):
        for size in SIZES:
            data = (ICONS / f"anzeiger-{size}.png").read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(struct.unpack(">II", data[16:24]), (size, size))
        self.assertIn("<svg", (ICONS / "anzeiger.svg").read_text(encoding="utf-8"))

    def test_icons_are_package_data(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        patterns = data["tool"]["setuptools"]["package-data"]["anzeiger"]
        self.assertIn("icons/*.png", patterns)
        self.assertIn("icons/*.svg", patterns)
        self.assertIn("lang/*.toml", patterns)

    def test_desktop_entry(self):
        entry = configparser.ConfigParser(interpolation=None)
        entry.optionxform = str
        entry.read(ROOT / "data" / "anzeiger.desktop", encoding="utf-8")
        section = entry["Desktop Entry"]
        self.assertEqual(section["Exec"], "anzeiger %u")
        self.assertEqual(section["Icon"], "anzeiger")
        self.assertEqual(section["StartupWMClass"], "Anzeiger")   # = tk.Tk(className=…)

    def test_install_scripts_cover_all_icon_sizes(self):
        for script in ("install.sh", "uninstall.sh"):
            text = (ROOT / script).read_text(encoding="utf-8")
            self.assertIn("for size in " + " ".join(map(str, SIZES)), text)


if __name__ == "__main__":
    unittest.main()
