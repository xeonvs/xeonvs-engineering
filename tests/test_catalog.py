from __future__ import annotations

import subprocess
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CatalogTest(unittest.TestCase):
    def test_catalog_is_self_consistent_and_public(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_catalog.py")],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_marketplace_branding_is_public_and_opaque(self) -> None:
        svg = ROOT / "assets/logo.svg"
        png = ROOT / "assets/logo.png"
        self.assertTrue(svg.is_file())
        self.assertTrue(png.is_file())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('src="assets/logo.svg"', readme)
        self.assertIn('alt="Xeonvs Engineering"', readme)
        self.assertIn('width="160"', readme)
        self.assertTrue((ROOT / "assets/logo.svg").resolve().is_file())
        data = png.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
        self.assertEqual((width, height, bit_depth, color_type), (1024, 1024, 8, 2))
        for catalog in (".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json"):
            self.assertNotIn('"logo"', (ROOT / catalog).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
