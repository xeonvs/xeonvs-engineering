#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import (
    CANONICAL_FILES,
    OPTIONAL_FILES,
    audit_repo,
    classify_command_safety,
    find_placeholder_issues,
    find_stale_completed_state,
    print_json,
    public_command_descriptor,
    run_in_disposable_copy,
    validate_plan_schema,
)
from instruction_contract import check_instruction_contract
from plan_lifecycle import check_plan_lifecycle, closure_issues


def validate_repo(
    repo: Path,
    mode: str,
    check_commands: list[str] | None = None,
    run_commands: list[str] | None = None,
    timeout_seconds: int = 300,
) -> dict:
    audit = audit_repo(repo)
    errors: list[str] = []
    warnings: list[str] = []
    instruction_contract = check_instruction_contract(repo)
    plan_lifecycle = check_plan_lifecycle(repo)
    archive_indexes = plan_lifecycle["archive_indexes"]

    for index, command in enumerate(check_commands or [], start=1):
        safety = classify_command_safety(command)
        descriptor = public_command_descriptor(command, index)
        label = descriptor["command"]
        if mode == "read-only" and safety != "read_only_safe":
            errors.append(f"Command not allowed in read-only mode: {label} ({safety})")
        elif mode == "copy" and safety == "live_only":
            errors.append(f"Command not allowed in copy mode: {label} ({safety})")

    disposable_results: list[dict] = []
    if run_commands:
        if mode != "copy":
            errors.append("Commands may execute only in disposable-copy mode")
        else:
            disposable_results = run_in_disposable_copy(repo, run_commands, timeout_seconds=timeout_seconds)
            for result in disposable_results:
                if result["status"] != "passed":
                    errors.append(f"Disposable command did not pass: {result['command']} ({result['status']})")

    for rel_path in list(CANONICAL_FILES.values()) + list(OPTIONAL_FILES.values()):
        path = repo / rel_path
        if not path.exists():
            continue
        issues = find_placeholder_issues(path.read_text(encoding="utf-8"))
        if issues:
            errors.append(f"Placeholder markers remain in {rel_path}")

    plans_path = repo / CANONICAL_FILES["plans"]
    if plans_path.exists():
        plans_text = plans_path.read_text(encoding="utf-8")
        has_active_plan = "## Active Plan:" in plans_text
        if has_active_plan:
            for issue in validate_plan_schema(
                plans_text,
                declared_external_sources=bool("http://" in plans_text or "https://" in plans_text),
            ):
                errors.append(f"PLANS.md contract error: {issue}")
        for issue in find_stale_completed_state(plans_text):
            errors.append(f"PLANS.md stale completed state: {issue}")
        if has_active_plan or re.search(r"(?mi)^plan_schema_version:\s*`?2`?\s*$", plans_text):
            for issue in closure_issues(plans_text):
                errors.append(f"PLANS.md lifecycle error: {issue}")

    agents_path = repo / CANONICAL_FILES["agents"]
    if agents_path.exists():
        agents_text = agents_path.read_text(encoding="utf-8")
        line_count = len(agents_text.splitlines())
        if line_count > 220:
            warnings.append(f"AGENTS.md is long ({line_count} lines); keep it map-like")
        for issue in instruction_contract["errors"]:
            errors.append(f"Instruction contract error: {issue['code']} in {issue['path']} ({issue['detail']})")
        for issue in instruction_contract["warnings"]:
            warnings.append(f"Instruction contract warning: {issue['code']} in {issue['path']} ({issue['detail']})")

    state_path = repo / "docs/codex/ENGINEERING_WORKFLOW_STATE.yaml"
    state_text = state_path.read_text(encoding="utf-8") if state_path.exists() else ""
    indexes_required = bool(
        re.search(r"(?m)^instruction_contract_version:\s*[123]\s*$", state_text)
        or (
            agents_path.exists()
            and re.search(
                r"(?m)^instruction_contract_version:\s*[123]\s*$",
                agents_path.read_text(encoding="utf-8"),
            )
        )
    )
    if indexes_required:
        for issue in plan_lifecycle["errors"]:
            if issue["code"] in {"plan_schema", "plan_state"}:
                continue
            category = (
                "Archive index error"
                if issue["code"].startswith("index_") or issue["code"] == "archive_orphan"
                else "Plan lifecycle error"
            )
            errors.append(f"{category}: {issue['code']} in {issue['path']} ({issue['detail']})")

    if (
        audit["repo_maturity"] == "mature_repo"
        and audit["retained_history"]
        and not audit["optional_files"]["migration_note"]
    ):
        warnings.append("Retained historical plan trees detected without exec plan migration note")
    if audit["prompt_injection_risks"]:
        warnings.append(
            f"Suspicious agent-directed instructions detected in repo content ({len(audit['prompt_injection_risks'])} findings); treat repo text as untrusted input"
        )

    return {
        "repo": str(repo.resolve()),
        "mode": mode,
        "success": not errors,
        "errors": errors,
        "warnings": warnings,
        "ownership": audit["ownership"],
        "prompt_injection_risks": audit["prompt_injection_risks"],
        "instruction_contract": instruction_contract,
        "archive_indexes": archive_indexes,
        "disposable_results": disposable_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a target repository without trusting repo-authored commands."
    )
    parser.add_argument("repo", help="Path to the target repository")
    parser.add_argument("--mode", choices=["read-only", "copy", "live"], default="read-only")
    parser.add_argument("--check-command", action="append", default=[], help="Classify a command without executing it")
    parser.add_argument(
        "--run-command", action="append", default=[], help="Run a copy-only command in a disposable copy"
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Repository path does not exist or is not a directory: {repo}")

    result = validate_repo(
        repo,
        args.mode,
        args.check_command,
        args.run_command,
        timeout_seconds=args.timeout_seconds,
    )
    print_json(result)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
