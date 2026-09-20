#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from common import audit_repo, print_json


def _write_full_report(report: dict, target: Path) -> dict[str, int | str]:
    parent = target.parent
    if not parent.is_dir():
        raise ValueError(f"Full-report parent directory does not exist: {parent}")
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{target.name}.", dir=parent, delete=False) as handle:
            temporary_name = handle.name
            os.chmod(temporary_name, 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except OSError:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise
    return {
        "path": str(target),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def summarize_audit(report: dict, full_report: dict[str, int | str]) -> dict:
    failure_categories: list[str] = []
    discovery = report["discovery"]
    if discovery["truncated"]:
        failure_categories.append("discovery_truncated")
    if "git_inventory_failed" in discovery["omission_reasons"]:
        failure_categories.append("git_inventory_failed")
    if {"unreadable_directory", "unreadable_entry"} & set(discovery["omission_reasons"]):
        failure_categories.append("discovery_unreadable")
    if report["prompt_injection_risks"]:
        failure_categories.append("prompt_injection_risks")
    if not report["instruction_contract"]["success"]:
        failure_categories.append(f"instruction_contract:{report['instruction_contract']['status']}")
    if not report["archive_indexes"]["success"]:
        failure_categories.append("archive_indexes")

    represented = {
        "repo_maturity",
        "file_count",
        "doc_count",
        "context_docs",
        "workflow_artifacts",
        "prompt_injection_risks",
        "instruction_contract",
        "archive_indexes",
        "discovery",
    }
    return {
        "status": "attention_required" if failure_categories else "ok",
        "repo_maturity": report["repo_maturity"],
        "failure_categories": failure_categories,
        "counts": {
            "files": report["file_count"],
            "documents": report["doc_count"],
            "workflow_artifacts": len(report["workflow_artifacts"]),
            "context_documents": len(report["context_docs"]),
            "prompt_injection_risks": len(report["prompt_injection_risks"]),
            "instruction_contract_errors": len(report["instruction_contract"]["errors"]),
            "archive_index_errors": len(report["archive_indexes"]["errors"]),
        },
        "discovery": discovery,
        "omissions": {
            "details_omitted": True,
            "full_report_fields": sorted(set(report) - represented),
            "inventory_truncated": discovery["truncated"],
            "inventory_omission_reasons": discovery["omission_reasons"],
        },
        "full_report": full_report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a repository for workflow scaffolding.")
    parser.add_argument("repo", help="Path to the target repository")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact machine-readable summary; requires --full-report.",
    )
    parser.add_argument(
        "--full-report",
        metavar="PATH",
        help="Write the complete JSON report atomically to PATH when --summary is used.",
    )
    args = parser.parse_args(argv)

    if args.summary != bool(args.full_report):
        parser.error("--summary and --full-report must be used together")

    repo = Path(args.repo).resolve()
    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Repository path does not exist or is not a directory: {repo}")

    report = audit_repo(repo)
    if args.summary:
        try:
            full_report = _write_full_report(report, Path(args.full_report))
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print_json(summarize_audit(report, full_report))
    else:
        print_json(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
