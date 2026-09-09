#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from common import iter_public_text_files, scan_privacy_text


def scan_text(text: str, deny_terms: list[str] | None = None) -> list[dict[str, int | str]]:
    """Return privacy categories without echoing candidate secret values."""
    issues = list(scan_privacy_text(text))
    for term in deny_terms or []:
        if not term:
            continue
        for line_number, line in enumerate(text.splitlines() or [""], start=1):
            if re.search(re.escape(term), line, re.IGNORECASE):
                issues.append({"type": "deny_term", "line": line_number})
                break
    return issues


def scan_public_tree(root: Path, deny_terms: list[str] | None = None) -> list[dict[str, int | str]]:
    """Scan public files with the same path, credential, email, and deny-term rules as direct input."""
    issues: list[dict[str, int | str]] = []
    for path in iter_public_text_files(root):
        if path.is_symlink():
            try:
                text = os.readlink(path)
            except OSError:
                continue
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        relative_path = path.relative_to(root).as_posix()
        for issue in scan_text(text, deny_terms):
            issues.append({"path": relative_path, **issue})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan public text without printing candidate secret values.")
    parser.add_argument("--path", action="append", default=[], help="File path to scan")
    parser.add_argument("--deny-term", action="append", default=[], help="Forbidden term to scan for")
    parser.add_argument("--public-tree", action="store_true", help="Scan every tracked public text file")
    parser.add_argument("--repo-root", default=".", help="Repository root for --public-tree")
    args = parser.parse_args()

    issues: list[dict[str, int | str]] = []
    if args.public_tree:
        issues.extend(scan_public_tree(Path(args.repo_root).resolve(), args.deny_term))

    texts: list[tuple[str, str]] = []
    if args.path:
        for raw_path in args.path:
            path = Path(raw_path)
            texts.append((str(path), path.read_text(encoding="utf-8")))
    elif not args.public_tree:
        texts.append(("stdin", sys.stdin.read()))

    for source, text in texts:
        for issue in scan_text(text, args.deny_term):
            issues.append({"path": source, **issue})

    print(json.dumps({"success": not issues, "issue_count": len(issues), "issues": issues}, indent=2, sort_keys=True))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
