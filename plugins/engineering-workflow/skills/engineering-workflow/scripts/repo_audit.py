#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import audit_repo, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a repository for workflow scaffolding.")
    parser.add_argument("repo", help="Path to the target repository")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Repository path does not exist or is not a directory: {repo}")

    print_json(audit_repo(repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
