#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import CANONICAL_FILES, OPTIONAL_FILES, PLAN_ORIGINS, PLAN_SCHEMA_VERSION, audit_repo, print_json


def build_plan(repo: Path, repo_changing: bool = True, plan_origin: str = "direct_execution") -> dict:
    if plan_origin not in PLAN_ORIGINS:
        raise ValueError(f"Unsupported plan origin: {plan_origin}")
    audit = audit_repo(repo)
    if not repo_changing:
        mode = "read_only_verify"
    else:
        mode = "greenfield_scaffold" if audit["repo_maturity"] == "empty_directory" else "conservative_merge"
    actions = []

    if repo_changing:
        ordered_keys = ["plans", *[key for key in CANONICAL_FILES if key != "plans"]]
        for key in ordered_keys:
            rel_path = CANONICAL_FILES[key]
            if not audit["canonical_files"][key]:
                action = "create"
            elif key == "plans":
                action = "update_in_place"
            else:
                action = "review_merge"
            actions.append({"path": rel_path, "action": action})
        index_dirs = ["docs", "docs/codex", "docs/engineering"]
        for archive_dir in ("docs/archive", "docs/archive/plans", "docs/archive/backlog"):
            if (repo / archive_dir).is_dir():
                index_dirs.append(archive_dir)
        for relative_dir in index_dirs:
            readme = f"{relative_dir}/README.md"
            actions.append({"path": readme, "action": "update_index" if (repo / readme).exists() else "create"})

    optional_actions = []
    if repo_changing and audit["repo_maturity"] == "mature_repo" and audit["retained_history"]:
        optional_actions.append(
            {
                "path": OPTIONAL_FILES["migration_note"],
                "action": "create",
                "reason": "retained historical plan topology",
            }
        )

    if (
        repo_changing
        and audit["repo_maturity"] == "mature_repo"
        and (audit["retained_history"] or audit["compatibility_docs"])
    ):
        optional_actions.append(
            {
                "path": OPTIONAL_FILES["adoption_note"],
                "action": "create",
                "reason": "record adopted and adapted workflow practices",
            }
        )

    questions = []
    if audit["dominant_language"] == "mixed":
        questions.append("language_choice")
    if audit["retained_history"]:
        questions.append("retained_history_policy")
    if audit["compatibility_docs"]:
        questions.append("compatibility_shim_policy")
    if audit["recommended_validation"]["copy_only_safe"]:
        questions.append("validation_mode")

    notes = []
    if audit["context_docs"]:
        notes.append(
            "Keep existing repo-specific docs as their own sources of truth; reference them from AGENTS.md instead of rewriting them."
        )

    return {
        "repo": str(repo.resolve()),
        "recommended_mode": mode,
        "repo_maturity": audit["repo_maturity"],
        "requires_full_plan": repo_changing,
        "plan_schema_version": PLAN_SCHEMA_VERSION if repo_changing else None,
        "plan_origin": plan_origin if repo_changing else None,
        "first_repository_write": CANONICAL_FILES["plans"] if repo_changing else None,
        "artifact_actions": actions,
        "optional_artifact_actions": optional_actions,
        "protected_doc_actions": audit["context_docs"],
        "ownership": audit["ownership"],
        "instruction_contract": audit["instruction_contract"],
        "archive_indexes": audit["archive_indexes"],
        "questions": questions,
        "notes": notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce a workflow bootstrap plan for a repository.")
    parser.add_argument("repo", help="Path to the target repository")
    parser.add_argument(
        "--read-only", action="store_true", help="Produce a read-only verification plan with no repo writes"
    )
    parser.add_argument("--plan-origin", choices=sorted(PLAN_ORIGINS), default="direct_execution")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Repository path does not exist or is not a directory: {repo}")

    print_json(build_plan(repo, repo_changing=not args.read_only, plan_origin=args.plan_origin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
