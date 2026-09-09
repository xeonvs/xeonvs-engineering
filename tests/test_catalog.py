from __future__ import annotations

import subprocess
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


if __name__ == "__main__":
    unittest.main()
