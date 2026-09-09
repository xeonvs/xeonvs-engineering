#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Iterable

sys.dont_write_bytecode = True

from common import (  # noqa: E402
    IGNORED_DIRS,
    find_stale_completed_state,
    iter_public_text_files,
    scan_privacy_text,
    validate_plan_schema,
)
from instruction_contract import check_instruction_contract  # noqa: E402
from plan_lifecycle import check_archive_indexes, closure_issues  # noqa: E402

REQUIRED_PATHS = (
    "AGENTS.md",
    "README.md",
    "LICENSE",
    ".github/workflows/ci.yml",
    "scripts/build_marketplace_package.py",
    ".agents/plugins/marketplace.json",
    ".claude-plugin/marketplace.json",
    "plugins/engineering-workflow/.codex-plugin/plugin.json",
    "plugins/engineering-workflow/.claude-plugin/plugin.json",
    "plugins/engineering-workflow/skills/engineering-workflow/SKILL.md",
    "skill/engineering-workflow/SKILL.md",
    "skill/engineering-workflow/agents/openai.yaml",
    "skill/engineering-workflow/scripts/common.py",
    "skill/engineering-workflow/scripts/repo_audit.py",
    "skill/engineering-workflow/scripts/assess_programmatic_stage.py",
    "skill/engineering-workflow/scripts/plan_bootstrap.py",
    "skill/engineering-workflow/scripts/validate_target_repo.py",
    "skill/engineering-workflow/scripts/validate_skill_repo.py",
    "skill/engineering-workflow/scripts/sanitize_output.py",
    "skill/engineering-workflow/scripts/update_installed_skill.py",
    "skill/engineering-workflow/scripts/upgrade_target_workflow.py",
    "skill/engineering-workflow/scripts/instruction_contract.py",
    "skill/engineering-workflow/scripts/plan_lifecycle.py",
    "skill/engineering-workflow/references/instruction_lifecycle.md",
    "skill/engineering-workflow/references/platform_compatibility.md",
    "skill/engineering-workflow/references/planning_and_backlog.md",
    "skill/engineering-workflow/references/agent_orchestration.md",
    "skill/engineering-workflow/references/model_profiles.md",
    "skill/engineering-workflow/references/skill_update.md",
    "skill/engineering-workflow/references/target_workflow_upgrade.md",
    "skill/engineering-workflow/references/validation_safety.md",
    "skill/engineering-workflow/references/privacy_and_sanitization.md",
    "skill/engineering-workflow/references/canonical_target.md",
    "skill/engineering-workflow/assets/templates/AGENTS.md.tmpl",
    "skill/engineering-workflow/assets/templates/PLANS.md.tmpl",
    "skill/engineering-workflow/assets/templates/TASKS_BACKLOG.md.tmpl",
    "skill/engineering-workflow/assets/templates/ENGINEERING_WORKFLOW_STATE.yaml.tmpl",
    "skill/engineering-workflow/assets/templates/PROGRAMMATIC_TOOL_STAGE.md.tmpl",
    "skill/engineering-workflow/assets/templates/indexes/docs_README.md.tmpl",
    "skill/engineering-workflow/assets/templates/indexes/codex_README.md.tmpl",
    "skill/engineering-workflow/assets/templates/indexes/engineering_README.md.tmpl",
    "skill/engineering-workflow/assets/templates/indexes/archive_README.md.tmpl",
    "skill/engineering-workflow/assets/templates/indexes/archive_plans_README.md.tmpl",
    "skill/engineering-workflow/assets/templates/indexes/archive_backlog_README.md.tmpl",
    "skill/engineering-workflow/assets/agents/utility.toml.tmpl",
    "skill/engineering-workflow/assets/agents/explorer.toml.tmpl",
    "skill/engineering-workflow/assets/agents/reviewer.toml.tmpl",
)
FORBIDDEN_PATH_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
MODEL_SLUG_RE = re.compile(r"\bgpt-\d+(?:\.\d+)*(?:-[a-z0-9]+)*\b")
FORBIDDEN_PRO_SLUG = "gpt-" + "5.6-" + "pro"

SKILL_REQUIRED_HEADINGS = (
    "## Runtime Invariants",
    "## Route By Request",
    "## Core Workflow",
    "## Canonical References",
    "## Scripts",
)
SKILL_REQUIRED_MARKERS = (
    "audit_before_edit: required",
    "plan_schema_version: 2",
    "instruction_contract_version: 3",
    "orchestration_contract_version: 3",
    "platform_compatibility_version: 1",
    "privacy_review_contract_version: 1",
    "repo_change_plan: full_required",
    "plan_mode_exit_materialization: required",
    "direct_execution_materialization: required",
    "shared_state_owner: root",
)
SKILL_REQUIRED_REFERENCES = (
    "references/planning_and_backlog.md",
    "references/instruction_lifecycle.md",
    "references/platform_compatibility.md",
    "references/agent_orchestration.md",
    "references/model_profiles.md",
    "references/skill_update.md",
    "references/target_workflow_upgrade.md",
    "references/validation_safety.md",
    "references/privacy_and_sanitization.md",
    "references/question_matrix.md",
)
README_REQUIRED_HEADINGS = (
    "## Install with Codex or Claude Code",
    "## Quick start",
    "## Using the skill in Codex",
    "## Claude Code compatibility",
    "## Alternative installations",
    "## Refresh a loaded skill",
    "## Update an installed skill",
    "## Upgrade a target workflow",
    "## Operating modes",
    "## Planning and backlog lifecycle",
    "## Agent orchestration",
    "## Validation and privacy",
    "## Example workflows",
    "## Repository layout",
    "## Validating",
    "## Versioning and updates",
)
CANONICAL_OWNER_MARKERS = {
    "## Full Active Plan Schema": "skill/engineering-workflow/references/planning_and_backlog.md",
    "## Deterministic Route": "skill/engineering-workflow/references/agent_orchestration.md",
    "## Programmatic Tool Route": "skill/engineering-workflow/references/agent_orchestration.md",
    "## Capability Mapping": "skill/engineering-workflow/references/model_profiles.md",
    "## Refresh Loaded Skill Decision": "skill/engineering-workflow/references/skill_update.md",
    "## Installation Types": "skill/engineering-workflow/references/skill_update.md",
    "## Prompt Invocation": "skill/engineering-workflow/references/target_workflow_upgrade.md",
    "## Migration Report": "skill/engineering-workflow/references/target_workflow_upgrade.md",
    "## Token-Aware Classification": "skill/engineering-workflow/references/validation_safety.md",
    "## Public Scan Scope": "skill/engineering-workflow/references/privacy_and_sanitization.md",
    "## Exact Synthetic-Fixture Review": "skill/engineering-workflow/references/privacy_and_sanitization.md",
    "## Cause Codes": "skill/engineering-workflow/references/instruction_lifecycle.md",
    "## Incident Catalog Schema": "skill/engineering-workflow/references/instruction_lifecycle.md",
    "## Shared Workflow Contract": "skill/engineering-workflow/references/platform_compatibility.md",
    "## Scope And Authorization": "skill/engineering-workflow/references/question_matrix.md",
    "## Task Continuity And Handoff": "skill/engineering-workflow/references/agent_orchestration.md",
}


def _extract_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(?P<body>.*?)\n---(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}
    values: dict[str, str] = {}
    section = ""
    for raw in match.group("body").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0 and raw.rstrip().endswith(":"):
            section = raw.rstrip()[:-1].strip()
            continue
        if ":" not in raw:
            continue
        key, value = raw.strip().split(":", 1)
        full_key = f"{section}.{key}" if indent and section else key
        values[full_key] = value.strip().strip("\"'")
    return values


def _candidate_paths(repo_root: Path) -> list[Path]:
    return sorted(
        iter_public_text_files(repo_root),
        key=lambda path: os.fsencode(path.relative_to(repo_root)),
    )


def _read_public_text(path: Path) -> str | None:
    if path.is_symlink():
        try:
            return os.readlink(path)
        except OSError:
            return None
    if any(parent.is_symlink() for parent in path.parents):
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _text_files(repo_root: Path) -> Iterable[tuple[Path, str]]:
    for path in _candidate_paths(repo_root):
        text = _read_public_text(path)
        if text is not None:
            yield path, text


def _check_forbidden_paths(repo_root: Path) -> list[str]:
    issues = []
    excluded_non_public = IGNORED_DIRS - FORBIDDEN_PATH_PARTS
    for path in repo_root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(repo_root)
        if any(part in excluded_non_public for part in rel.parts):
            continue
        if any(part in FORBIDDEN_PATH_PARTS for part in rel.parts):
            issues.append(f"Forbidden cache path present: {rel.as_posix()}")
        elif path.suffix.lower() in FORBIDDEN_SUFFIXES:
            issues.append(f"Forbidden compiled artifact present: {rel.as_posix()}")
    return issues


def _scan_public_privacy(repo_root: Path) -> list[str]:
    issues = []
    for path, text in _text_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        for finding in scan_privacy_text(text):
            issues.append(f"Privacy finding {finding['type']} in {rel}:{finding['line']}")
        if FORBIDDEN_PRO_SLUG in text:
            issues.append(f"Forbidden invented pro model slug in {rel}")
    return issues


def _validate_yaml_shape(text: str) -> None:
    """Parse the repository's intentionally small YAML subset without third-party dependencies."""

    def validate_scalar(value: str, number: int) -> None:
        stack: list[str] = []
        quote: str | None = None
        index = 0
        pairs = {")": "(", "]": "[", "}": "{"}
        while index < len(value):
            char = value[index]
            if quote is not None:
                if quote == '"' and char == "\\":
                    index += 2
                    continue
                if quote == "'" and char == "'" and index + 1 < len(value) and value[index + 1] == "'":
                    index += 2
                    continue
                if char == quote:
                    quote = None
                index += 1
                continue
            if char == "#":
                break
            if char in {"'", '"'}:
                quote = char
            elif char in "([{":
                stack.append(char)
            elif char in ")]}":
                if not stack or stack.pop() != pairs[char]:
                    raise ValueError(f"unbalanced collection at line {number}")
            index += 1
        if quote is not None:
            raise ValueError(f"unterminated quoted scalar at line {number}")
        if stack:
            raise ValueError(f"unterminated collection at line {number}")

    previous_indent = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#") or raw.strip() in {"---", "..."}:
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError(f"tab indentation at line {number}")
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        body = stripped[2:].strip() if stripped.startswith("- ") else stripped
        if stripped == "-":
            body = ""
        if body and not re.match(r"^(?:[^:#][^:]*|['\"][^'\"]+['\"]):(?:\s.*)?$", body):
            if not stripped.startswith("-"):
                raise ValueError(f"expected mapping or sequence at line {number}")
        scalar = body.split(":", 1)[1].strip() if ":" in body else body
        if scalar not in {"|", ">", "|-", ">-", "|+", ">+"}:
            validate_scalar(scalar, number)
        if indent > previous_indent + 8:
            raise ValueError(f"unexpected indentation jump at line {number}")
        previous_indent = indent


def _validate_parseable_files(repo_root: Path) -> list[str]:
    issues = []
    for path, text in _text_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        try:
            if path.suffix.lower() in {".yaml", ".yml"} or path.name.endswith((".yaml.tmpl", ".yml.tmpl")):
                _validate_yaml_shape(text)
            elif path.suffix.lower() == ".toml" or path.name.endswith(".toml.tmpl"):
                tomllib.loads(text)
            elif path.suffix.lower() == ".json" or path.name.endswith(".json.tmpl"):
                json.loads(text)
            elif path.suffix.lower() == ".py":
                ast.parse(text, filename=rel)
        except (ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError, SyntaxError) as exc:
            issues.append(f"Parse failure in {rel}: {exc}")
    return issues


def _validate_skill_router(repo_root: Path) -> tuple[list[str], str | None]:
    issues: list[str] = []
    path = repo_root / "skill/engineering-workflow/SKILL.md"
    if not path.exists():
        return issues, None
    text = path.read_text(encoding="utf-8")
    metadata = _extract_frontmatter(text)
    frontmatter = re.match(r"^---\n(?P<body>.*?)\n---(?:\n|$)", text, re.DOTALL)
    if frontmatter:
        override_fields = {"model", "effort", "context", "agent", "allowed-tools", "disallowed-tools", "hooks"}
        root_fields = set()
        for raw_key in re.findall(r"(?m)^([^\s:#][^:]*):", frontmatter.group("body")):
            key = raw_key.strip()
            if key.startswith('"'):
                try:
                    key = json.loads(key)
                except json.JSONDecodeError:
                    issues.append("Shared skill frontmatter has an unsupported quoted key")
                    continue
            elif key.startswith("'") and key.endswith("'"):
                key = key[1:-1].replace("''", "'")
            root_fields.add(key)
        for field in sorted(root_fields & override_fields):
            issues.append(f"Shared skill frontmatter must preserve native platform settings: {field}")
    if metadata.get("name") != "engineering-workflow" or not metadata.get("description"):
        issues.append("SKILL.md frontmatter is missing name or description")
    version = metadata.get("metadata.version")
    if not version or not SEMVER_RE.fullmatch(version):
        issues.append("SKILL.md metadata.version is missing or not SemVer")
        version = None
    for heading in SKILL_REQUIRED_HEADINGS:
        if heading not in text:
            issues.append(f"SKILL.md is missing required heading: {heading}")
    for marker in SKILL_REQUIRED_MARKERS:
        if marker not in text:
            issues.append(f"SKILL.md is missing structured invariant: {marker}")
    for reference in SKILL_REQUIRED_REFERENCES:
        if reference not in text:
            issues.append(f"SKILL.md is missing canonical reference link: {reference}")
    if len(text.splitlines()) > 140:
        issues.append("SKILL.md is no longer a lean runtime router")
    return issues, version


def _validate_readme(repo_root: Path, version: str | None) -> list[str]:
    path = repo_root / "README.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    issues = []
    for heading in README_REQUIRED_HEADINGS:
        if heading not in text:
            issues.append(f"README.md is missing required section: {heading}")
    if 'CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"' not in text:
        issues.append("README.md does not explain the official installer CODEX_HOME default")
    if version and f"Current skill version: `{version}`." not in text:
        issues.append("README.md current skill version does not match SKILL.md metadata.version")
    for mode in ("refresh_loaded_skill", "update_installed_skill", "upgrade_target_workflow"):
        if mode not in text:
            issues.append(f"README.md is missing lifecycle or migration mode: {mode}")
    for field in ("recommended_action", "automatic_update_allowed", "confirmation_required"):
        if field not in text:
            issues.append(f"README.md is missing refresh orchestration field: {field}")
    if "--prompt" not in text:
        issues.append("README.md is missing prompt-owned target-upgrade orchestration")
    if version and f"--target-version {version}" not in text:
        issues.append("README.md target-upgrade prompt does not use the current version")
    return issues


def _validate_plan_contract(repo_root: Path) -> list[str]:
    issues = []
    template_path = repo_root / "skill/engineering-workflow/assets/templates/PLANS.md.tmpl"
    if template_path.exists():
        for item in validate_plan_schema(template_path.read_text(encoding="utf-8")):
            issues.append(f"PLANS.md template: {item}")
    reference_path = repo_root / "skill/engineering-workflow/references/planning_and_backlog.md"
    if reference_path.exists():
        text = reference_path.read_text(encoding="utf-8")
        markers = (
            "repo_change_plan: full_required",
            "plan_mode_exit_materialization: required",
            "direct_execution_materialization: required",
            "compressed_active_plan: forbidden",
            "closure_transition: checked",
            "archive_indexing: atomic",
            "## Resume And Milestone Reconciliation",
            "## Closure State Machine",
        )
        for marker in markers:
            if marker not in text:
                issues.append(f"Planning reference is missing structural contract marker: {marker}")
    root_plans = repo_root / "PLANS.md"
    if root_plans.exists():
        text = root_plans.read_text(encoding="utf-8")
        if "## Active Plan:" in text:
            for item in validate_plan_schema(text, declared_external_sources=True, require_fidelity_passed=True):
                issues.append(f"Root PLANS.md: {item}")
            for item in closure_issues(text):
                issues.append(f"Root PLANS.md lifecycle: {item}")
        for item in find_stale_completed_state(text):
            issues.append(f"Root PLANS.md stale completed state: {item}")
    return issues


def _validate_instruction_assets(repo_root: Path) -> list[str]:
    issues: list[str] = []
    template_root = repo_root / "skill/engineering-workflow/assets/templates"
    with tempfile.TemporaryDirectory(prefix="engineering-workflow-contract-") as temp_name:
        target = Path(temp_name)
        (target / "docs/codex").mkdir(parents=True)
        (target / "docs/engineering").mkdir(parents=True)
        agents = (template_root / "AGENTS.md.tmpl").read_text(encoding="utf-8")
        agents = agents.replace("{{ entrypoint_hint }}", "README.md").replace("{{ subsystem_hint }}", "src/")
        (target / "AGENTS.md").write_text(agents, encoding="utf-8")
        (target / "docs/engineering/project_principles.md").write_text(
            (template_root / "project_principles.md.tmpl").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (target / "docs/codex/AGENT_EXECUTION_PITFALLS.md").write_text(
            (template_root / "AGENT_EXECUTION_PITFALLS.md.tmpl").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        result = check_instruction_contract(target)
    for item in result["errors"]:
        issues.append(f"Instruction template contract: {item['code']} in {item['path']} ({item['detail']})")
    return issues


def _validate_root_agents_boundary(repo_root: Path) -> list[str]:
    path = repo_root / "AGENTS.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    for marker in ("local guidance", "not part of the installed", "must never be read by runtime skill scripts"):
        if marker not in text:
            issues.append(f"Root AGENTS.md is missing local-only boundary: {marker}")
    packaged_root_agents = repo_root / "skill/engineering-workflow/AGENTS.md"
    if packaged_root_agents.exists():
        issues.append("Runtime skill contains a repository-local root AGENTS.md")
    return issues


def _validate_source_indexes(repo_root: Path) -> list[str]:
    result = check_archive_indexes(repo_root)
    return [
        f"Source documentation index: {item['code']} in {item['path']} ({item['detail']})" for item in result["errors"]
    ]


def _validate_canonical_owners(repo_root: Path) -> list[str]:
    issues = []
    skill_root = repo_root / "skill/engineering-workflow"
    text_by_path: dict[str, str] = {}
    for path in skill_root.rglob("*"):
        if path.is_file() and (path.suffix.lower() == ".md" or path.name.endswith(".md.tmpl")):
            text = _read_public_text(path)
            if text is not None:
                text_by_path[path.relative_to(repo_root).as_posix()] = text
    for marker, owner in CANONICAL_OWNER_MARKERS.items():
        found = sorted(path for path, text in text_by_path.items() if marker in text)
        if found != [owner]:
            issues.append(f"Canonical owner mismatch for {marker}: expected only {owner}, found {found}")

    allowed_model_owners = {
        "skill/engineering-workflow/references/model_profiles.md",
        "skill/engineering-workflow/assets/agents/utility.toml.tmpl",
        "skill/engineering-workflow/assets/agents/explorer.toml.tmpl",
        "skill/engineering-workflow/assets/agents/reviewer.toml.tmpl",
    }
    for path, text in text_by_path.items():
        if MODEL_SLUG_RE.search(text) and path not in allowed_model_owners:
            issues.append(f"Concrete model mapping appears outside its canonical owner: {path}")
    return issues


def _validate_agent_profiles(repo_root: Path) -> list[str]:
    issues = []
    root = repo_root / "skill/engineering-workflow/assets/agents"
    parsed: dict[str, dict] = {}
    for name in ("utility", "explorer", "reviewer"):
        path = root / f"{name}.toml.tmpl"
        if not path.exists():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            issues.append(f"{path.name} is not parseable TOML: {exc}")
            continue
        parsed[name] = data
        for field in (
            "name",
            "description",
            "developer_instructions",
            "model",
            "model_reasoning_effort",
            "sandbox_mode",
        ):
            if field not in data:
                issues.append(f"{path.name} is missing required field: {field}")
    utility = parsed.get("utility", {})
    expected_utility_model = "gpt-" + "5.6-" + "terra"
    if utility.get("model") != expected_utility_model or utility.get("model_reasoning_effort") != "low":
        issues.append("Utility agent must use the current low-cost low-reasoning profile")
    if utility.get("sandbox_mode") != "read-only":
        issues.append("Utility agent must remain read-only")
    explorer = parsed.get("explorer", {})
    if explorer.get("model") != expected_utility_model or explorer.get("model_reasoning_effort") != "medium":
        issues.append("Explorer agent must use the current balanced read-heavy profile")
    if explorer.get("sandbox_mode") != "read-only":
        issues.append("Explorer agent must remain read-only")
    reviewer = parsed.get("reviewer", {})
    if reviewer.get("model") != "gpt-" + "6-astra":
        issues.append("Reviewer agent must use the current Codex review model profile")
    if reviewer.get("model_reasoning_effort") != "high" or reviewer.get("sandbox_mode") != "read-only":
        issues.append("Reviewer agent must use high reasoning in read-only mode")
    reference = repo_root / "skill/engineering-workflow/references/agent_orchestration.md"
    if reference.exists():
        text = reference.read_text(encoding="utf-8")
        for marker in ("agents.max_depth = 1", "two or three", "single-writer", "PLANS.md", "periodic"):
            if marker not in text:
                issues.append(f"Agent orchestration reference is missing invariant: {marker}")
    return issues


def _validate_programmatic_tool_assets(repo_root: Path) -> list[str]:
    issues: list[str] = []
    template_path = repo_root / "skill/engineering-workflow/assets/templates/PROGRAMMATIC_TOOL_STAGE.md.tmpl"
    if template_path.exists():
        text = template_path.read_text(encoding="utf-8")
        expected = {
            "stage_id",
            "eligible_tools",
            "max_calls",
            "max_concurrency",
            "result_schema",
            "evidence_fields",
            "stop_condition",
            "retry_limit",
            "direct_handoff",
        }
        found = re.findall(r"\{\{\s*([a-z_]+)\s*\}\}", text)
        if set(found) != expected or len(found) != len(expected):
            issues.append(
                f"Programmatic tool template placeholders mismatch: expected {sorted(expected)}, found {sorted(found)}"
            )
        if text.count("<tool_orchestration>") != 1 or text.count("</tool_orchestration>") != 1:
            issues.append("Programmatic tool template must contain one orchestration wrapper")
        for api_only in ('"type": "programmatic_tool_calling"', "allowed_callers", "previous_response_id"):
            if api_only in text:
                issues.append(f"Programmatic tool template contains API integration field: {api_only}")
    for relative in (
        "skill/engineering-workflow/assets/templates/AGENTS.md.tmpl",
        "skill/engineering-workflow/assets/templates/PLANS.md.tmpl",
        "skill/engineering-workflow/assets/templates/project_principles.md.tmpl",
    ):
        path = repo_root / relative
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "Programmatic Tool Calling" in text or "assess_programmatic_stage.py" in text:
                issues.append(f"Target repository template duplicates runtime PTC policy: {relative}")
    return issues


def _validate_marketplace_package(repo_root: Path, version: str | None) -> list[str]:
    issues: list[str] = []
    if version is None:
        return issues
    paths = {
        "codex_catalog": repo_root / ".agents/plugins/marketplace.json",
        "claude_catalog": repo_root / ".claude-plugin/marketplace.json",
        "codex_manifest": repo_root / "plugins/engineering-workflow/.codex-plugin/plugin.json",
        "claude_manifest": repo_root / "plugins/engineering-workflow/.claude-plugin/plugin.json",
    }
    parsed: dict[str, dict] = {}
    for name, path in paths.items():
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            issues.append(f"Marketplace file is not valid UTF-8 JSON: {path.relative_to(repo_root)}")
            continue
        if not isinstance(value, dict):
            issues.append(f"Marketplace file root must be an object: {path.relative_to(repo_root)}")
            continue
        parsed[name] = value

    for name in ("codex_manifest", "claude_manifest"):
        manifest = parsed.get(name, {})
        if manifest.get("name") != "engineering-workflow":
            issues.append(f"{name} plugin name is not engineering-workflow")
        if manifest.get("version") != version:
            issues.append(f"{name} version does not match SKILL.md")
        if manifest.get("repository") != "https://github.com/xeonvs/codex-engineering-workflow":
            issues.append(f"{name} repository URL is not canonical")
        for unsupported in ("mcpServers", "apps", "hooks"):
            if unsupported in manifest:
                issues.append(f"{name} declares unsupported capability: {unsupported}")

    codex_manifest = parsed.get("codex_manifest", {})
    interface = codex_manifest.get("interface", {})
    if not isinstance(interface, dict) or interface.get("category") != "Developer Tools":
        issues.append("Codex plugin category must be Developer Tools")
    if codex_manifest.get("skills") != "./skills/":
        issues.append("Codex plugin must discover skills only inside its package")
    codex_catalog = parsed.get("codex_catalog", {})
    codex_entries = codex_catalog.get("plugins", [])
    if codex_catalog.get("name") != "xeonvs-engineering" or len(codex_entries) != 1:
        issues.append("Codex marketplace must contain the single xeonvs-engineering plugin entry")
    elif codex_entries[0] != {
        "name": "engineering-workflow",
        "source": {"source": "local", "path": "./plugins/engineering-workflow"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }:
        issues.append("Codex marketplace entry does not match the public package contract")

    claude_catalog = parsed.get("claude_catalog", {})
    claude_entries = claude_catalog.get("plugins", [])
    if claude_catalog.get("name") != "xeonvs-engineering" or len(claude_entries) != 1:
        issues.append("Claude marketplace must contain the single xeonvs-engineering plugin entry")
    elif claude_entries[0].get("source") != "./plugins/engineering-workflow":
        issues.append("Claude marketplace source must stay inside the repository package")

    source = repo_root / "skill/engineering-workflow"
    plugin_root = repo_root / "plugins/engineering-workflow"
    packaged = plugin_root / "skills/engineering-workflow"
    if plugin_root.is_dir():
        for path in plugin_root.rglob("*"):
            if path.is_symlink():
                issues.append(
                    f"Marketplace package must not contain symlinks: {path.relative_to(plugin_root).as_posix()}"
                )
    source_files = {
        path.relative_to(source).as_posix(): path
        for path in source.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and path.name != ".DS_Store"
    }
    packaged_files = (
        {
            path.relative_to(packaged).as_posix(): path
            for path in packaged.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        if packaged.is_dir()
        else {}
    )
    if source_files.keys() != packaged_files.keys():
        issues.append("Packaged skill file set drifts from the canonical source")
    else:
        for relative in sorted(source_files):
            if source_files[relative].read_bytes() != packaged_files[relative].read_bytes():
                issues.append(f"Packaged skill byte drift: {relative}")
    expected_plugin_files = {
        ".codex-plugin/plugin.json",
        ".claude-plugin/plugin.json",
        *(f"skills/engineering-workflow/{relative}" for relative in source_files),
    }
    actual_plugin_files = (
        {
            path.relative_to(plugin_root).as_posix()
            for path in plugin_root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        if plugin_root.is_dir()
        else set()
    )
    if actual_plugin_files != expected_plugin_files:
        issues.append("Marketplace package contains missing or unmanaged files")
    return issues


def _validate_active_versions(repo_root: Path, version: str | None) -> list[str]:
    if not version:
        return []
    issues = []
    target_script = repo_root / "skill/engineering-workflow/scripts/upgrade_target_workflow.py"
    if target_script.exists() and f'default="{version}"' not in target_script.read_text(encoding="utf-8"):
        issues.append("Target-upgrade CLI default version does not match SKILL.md")
    manifest = repo_root / "docs/codex/ENGINEERING_WORKFLOW_STATE.yaml"
    if manifest.exists():
        match = re.search(r"(?m)^skill_version:\s*[\"']?([^\s\"']+)", manifest.read_text(encoding="utf-8"))
        if match and match.group(1) != version:
            issues.append("Active workflow state manifest version does not match SKILL.md")
    return issues


def _validate_openai_yaml(repo_root: Path) -> list[str]:
    path = repo_root / "skill/engineering-workflow/agents/openai.yaml"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    issues = []
    if "$engineering-workflow" not in text:
        issues.append("agents/openai.yaml default prompt does not mention $engineering-workflow")
    if "Upgrade A Target Workflow" not in text:
        issues.append("agents/openai.yaml default prompt does not route target workflow upgrades")
    implicit = re.search(r"(?m)^\s*allow_implicit_invocation:\s*(true|false)\s*$", text)
    if not implicit or implicit.group(1) != "true":
        issues.append("agents/openai.yaml must allow prompt-driven implicit invocation")
    match = re.search(r'(?m)^\s*short_description:\s*["\'](?P<value>.*?)["\']\s*$', text)
    if not match or not 25 <= len(match.group("value")) <= 64:
        issues.append("agents/openai.yaml short_description must be 25-64 characters")
    return issues


def validate_skill_repo(repo_root: Path) -> dict:
    root = repo_root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    unsafe_required = False
    for relative in REQUIRED_PATHS:
        path = root / relative
        current = root
        symbolic_parent = False
        for part in Path(relative).parts[:-1]:
            current = current / part
            if current.is_symlink():
                symbolic_parent = True
                break
        if not path.exists():
            errors.append(f"Missing required path: {relative}")
        elif path.is_symlink() or symbolic_parent:
            errors.append(f"Required public path must not be a symlink: {relative}")
            unsafe_required = True
    if unsafe_required:
        errors.extend(_check_forbidden_paths(root))
        errors.extend(_scan_public_privacy(root))
        return {
            "success": False,
            "skill_version": None,
            "errors": errors,
            "warnings": warnings,
            "checks": {
                "structural_contracts": False,
                "public_privacy_scope": "tracked_and_untracked_public_text",
                "parseable_formats": [],
                "historical_versions_allowed": True,
            },
        }
    router_errors, version = _validate_skill_router(root)
    errors.extend(router_errors)
    errors.extend(_validate_readme(root, version))
    errors.extend(_validate_plan_contract(root))
    errors.extend(_validate_instruction_assets(root))
    errors.extend(_validate_root_agents_boundary(root))
    errors.extend(_validate_source_indexes(root))
    errors.extend(_validate_canonical_owners(root))
    errors.extend(_validate_agent_profiles(root))
    errors.extend(_validate_programmatic_tool_assets(root))
    errors.extend(_validate_marketplace_package(root, version))
    errors.extend(_validate_active_versions(root, version))
    errors.extend(_validate_openai_yaml(root))
    errors.extend(_check_forbidden_paths(root))
    errors.extend(_scan_public_privacy(root))
    errors.extend(_validate_parseable_files(root))
    return {
        "success": not errors,
        "skill_version": version,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "structural_contracts": True,
            "public_privacy_scope": "tracked_and_untracked_public_text",
            "parseable_formats": ["python", "yaml", "toml", "json"],
            "historical_versions_allowed": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate this public skill repository.")
    parser.add_argument("--repo-root", default=".", help="Path to the skill repository root")
    args = parser.parse_args()
    result = validate_skill_repo(Path(args.repo_root))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
