from __future__ import annotations

import importlib.util
import json
import subprocess
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_catalog", ROOT / "scripts/validate_catalog.py")
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


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

    def test_declared_plugin_icons_are_narrowly_allowlisted(self) -> None:
        def png(width: int, height: int) -> bytes:
            def chunk(kind: bytes, data: bytes) -> bytes:
                crc = zlib.crc32(data, zlib.crc32(kind))
                return len(data).to_bytes(4, "big") + kind + data + crc.to_bytes(4, "big")

            header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
            pixels = (b"\x00" + b"\x00" * (width * 3)) * height
            return (
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", header)
                + chunk(b"IDAT", zlib.compress(pixels))
                + chunk(b"IEND", b"")
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = {Path("assets/logo.png"): (1024, 1024)}
            for name in validator.EXPECTED_NAMES:
                bundle = root / "plugins" / name
                (bundle / ".codex-plugin").mkdir(parents=True)
                (bundle / ".claude-plugin").mkdir()
                interface = {"brandColor": "#3972F6"}
                for field, dimensions in validator.ICON_FIELDS.items():
                    filename = f"assets/{field}.png"
                    interface[field] = "./" + filename
                    path = bundle / filename
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(png(*dimensions))
                    expected[Path("plugins") / name / filename] = dimensions
                (bundle / ".codex-plugin/plugin.json").write_text(
                    json.dumps({"interface": interface}), encoding="utf-8"
                )
                (bundle / ".claude-plugin/plugin.json").write_text("{}", encoding="utf-8")

            with mock.patch.object(validator, "ROOT", root):
                self.assertEqual(validator.declared_binary_assets(), expected)
                manifest = root / "plugins/engineering-workflow/.codex-plugin/plugin.json"
                value = json.loads(manifest.read_text(encoding="utf-8"))
                value["interface"]["logo"] = "./../outside.png"
                manifest.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "unsafe Codex icon path"):
                    validator.declared_binary_assets()


if __name__ == "__main__":
    unittest.main()
