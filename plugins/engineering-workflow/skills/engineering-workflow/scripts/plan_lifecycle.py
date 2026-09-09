#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable

from common import INDEX_MARKER_END, INDEX_MARKER_START, PLAN_SCHEMA_VERSION, _section_text, validate_plan_schema


INDEX_START = INDEX_MARKER_START
INDEX_END = INDEX_MARKER_END
INDEX_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "assets" / "templates" / "indexes"
INDEX_SPECS = {
    "docs": "docs_README.md.tmpl",
    "docs/codex": "codex_README.md.tmpl",
    "docs/engineering": "engineering_README.md.tmpl",
    "docs/archive": "archive_README.md.tmpl",
    "docs/archive/plans": "archive_plans_README.md.tmpl",
    "docs/archive/backlog": "archive_backlog_README.md.tmpl",
}
PLAN_STATUSES = {"active", "blocked", "ready_for_closure", "done"}
ITEM_STATUSES = {"pending", "in_progress", "blocked", "done", "out_of_scope"}
TERMINAL_ITEM_STATUSES = {"done", "out_of_scope"}


class LifecycleError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _read(path: Path) -> str:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _plan_version(text: str) -> int | None:
    match = re.search(r"(?mi)^plan_schema_version:\s*`?(\d+)`?\s*$", text)
    return int(match.group(1)) if match else None


def _plan_status(text: str) -> str:
    match = re.search(r"(?m)^Status:\s*([a-z_]+)\s*$", text)
    return match.group(1) if match else ""


def _table_statuses(text: str) -> list[str]:
    statuses: list[str] = []
    for line in _section_text(text, "Requirement Traceability").splitlines():
        if not line.lstrip().startswith("|") or "REQ-" not in line:
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if cells:
            statuses.append(cells[-1])
    return statuses


def _queue_statuses(text: str) -> list[str]:
    statuses: list[str] = []
    for line in _section_text(text, "Current Work Queue").splitlines():
        if "WQ-" not in line:
            continue
        explicit = re.findall(r"`(pending|in_progress|blocked|done|out_of_scope|[a-z_]+)`", line)
        if explicit:
            statuses.append(explicit[-1])
        elif re.search(r"-\s*\[x\]", line, re.IGNORECASE):
            statuses.append("done")
        elif re.search(r"-\s*\[ \]", line):
            statuses.append("pending")
    return statuses


def closure_issues(text: str, *, require_ready: bool = False, archived: bool = False) -> list[str]:
    issues: list[str] = []
    if _plan_version(text) != PLAN_SCHEMA_VERSION:
        return issues if archived and _plan_version(text) == 1 else ["closure requires plan_schema_version 2"]
    status = _plan_status(text)
    expected = "done" if archived else "ready_for_closure"
    if require_ready and status != expected:
        issues.append(f"closure status must be {expected}, found {status or 'missing'}")
    elif status and status not in PLAN_STATUSES:
        issues.append(f"invalid plan status: {status}")

    statuses = _table_statuses(text) + _queue_statuses(text)
    for value in statuses:
        if value not in ITEM_STATUSES:
            issues.append(f"invalid requirement or queue status: {value}")
        elif (require_ready or status in {"ready_for_closure", "done"}) and value not in TERMINAL_ITEM_STATUSES:
            issues.append(f"non-terminal requirement or queue status: {value}")
    if "resolved_for_release_handoff" in text:
        issues.append("pseudo-terminal status resolved_for_release_handoff is forbidden")
    validation = _section_text(text, "Latest Validation Results")
    if (require_ready or status in {"ready_for_closure", "done"}) and (
        not validation or re.search(r"\bnot run yet\b", validation, re.IGNORECASE)
    ):
        issues.append("current final validation evidence is missing")
    if require_ready or status in {"ready_for_closure", "done"}:
        updated_match = re.search(r"(?m)^Last Updated:\s*(\d{4}-\d{2}-\d{2})\s*$", text)
        validation_dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", validation)
        if not updated_match:
            issues.append("Last Updated must be an ISO date before closure")
        elif not validation_dates or max(validation_dates) < updated_match.group(1):
            issues.append("final validation predates the last content update")
    for section in ("Plan Fidelity Check", "Reconciliation Check", "Closure Gate"):
        body = _section_text(text, section)
        if (require_ready or status in {"ready_for_closure", "done"}) and re.search(r"(?m)^\s*-\s*\[ \]", body):
            issues.append(f"{section} has unchecked conditions")
    resume = _section_text(text, "Resume Point")
    if require_ready or status in {"ready_for_closure", "done"}:
        if re.search(r"\bWQ-\d+\b|\b(?:start|continue|resume)\b", resume, re.IGNORECASE):
            issues.append("Resume Point contains future in-scope work")
        if not re.search(r"\b(?:no|none|nothing)\b", resume, re.IGNORECASE):
            issues.append("Resume Point does not explicitly state that no work remains")
        delivery = _section_text(text, "Post-Close Delivery")
        if not delivery:
            issues.append("Post-Close Delivery is empty")
        elif not re.search(
            r"\b(?:completed|outside|out of scope|not applicable|none|no .* required)\b",
            delivery,
            re.IGNORECASE,
        ):
            issues.append("Post-Close Delivery does not classify remaining delivery work")
        handoff = _section_text(text, "Handoff Notes")
        if re.search(r"\b(?:start|continue|resume|implement|finish|run|report|push|release)\b", handoff, re.IGNORECASE):
            issues.append("Handoff Notes contains future in-scope work")
        if not re.search(r"\b(?:no|none|nothing|completed|outside|out of scope|not applicable)\b", handoff, re.IGNORECASE):
            issues.append("Handoff Notes does not explicitly state that no in-scope work remains")
    return issues


def _links(text: str) -> list[str]:
    return [match.group(1).split("#", 1)[0] for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text)]


def _index_targets(root: Path, relative_dir: str, extra_files: set[str] | None = None) -> list[str]:
    extra_files = extra_files or set()
    directory = root / relative_dir
    entries: set[str] = set()
    if directory.is_dir() and not directory.is_symlink():
        for path in directory.iterdir():
            if path.is_file() and not path.is_symlink() and path.name != "README.md" and path.suffix.lower() in {".md", ".rst", ".txt"}:
                entries.add(path.name)
    prefix = relative_dir.rstrip("/") + "/"
    for item in extra_files:
        if item.startswith(prefix):
            remainder = item[len(prefix):]
            if "/" not in remainder and remainder != "README.md":
                entries.add(remainder)
    if relative_dir == "docs":
        for child in ("codex", "engineering", "archive"):
            readme = f"docs/{child}/README.md"
            if (root / readme).is_file() or readme in extra_files:
                entries.add(f"{child}/README.md")
    elif relative_dir == "docs/archive":
        for child in ("plans", "backlog"):
            readme = f"docs/archive/{child}/README.md"
            if (root / readme).is_file() or readme in extra_files:
                entries.add(f"{child}/README.md")
    return sorted(entries)


def _render_entries(entries: list[str]) -> str:
    if not entries:
        return "No indexed documents yet."
    return "\n".join(f"- [{entry}]({entry})" for entry in entries)


def _render_index(relative_dir: str, entries: list[str], existing: str) -> str:
    managed = _render_entries(entries)
    if existing:
        if INDEX_START not in existing or INDEX_END not in existing:
            raise LifecycleError("unmanaged_index_conflict", f"Existing {relative_dir}/README.md has no managed index markers")
        return re.sub(
            re.escape(INDEX_START) + r".*?" + re.escape(INDEX_END),
            f"{INDEX_START}\n{managed}\n{INDEX_END}",
            existing,
            count=1,
            flags=re.DOTALL,
        ).rstrip() + "\n"
    template = _read(INDEX_TEMPLATE_ROOT / INDEX_SPECS[relative_dir])
    if not template:
        raise LifecycleError("index_template_missing", f"Missing index template for {relative_dir}")
    return template.replace("{{ entries }}", managed).rstrip() + "\n"


def planned_index_writes(
    root: Path,
    *,
    extra_files: set[str] | None = None,
    relative_dirs: set[str] | None = None,
) -> dict[str, bytes]:
    extra_files = extra_files or set()
    writes: dict[str, bytes] = {}
    planned_dirs = [
        relative_dir
        for relative_dir in INDEX_SPECS
        if (relative_dirs is None or relative_dir in relative_dirs)
        and (
            (root / relative_dir).is_dir()
            or any(item == relative_dir or item.startswith(relative_dir.rstrip("/") + "/") for item in extra_files)
        )
    ]
    planned_readmes = {f"{relative_dir}/README.md" for relative_dir in planned_dirs}
    indexed_files = extra_files | planned_readmes
    for relative_dir in planned_dirs:
        exists = (root / relative_dir).is_dir() or any(
            item == relative_dir or item.startswith(relative_dir.rstrip("/") + "/") for item in extra_files
        )
        if not exists:
            continue
        readme_rel = f"{relative_dir}/README.md"
        existing = _read(root / readme_rel) if (root / readme_rel).exists() else ""
        content = _render_index(relative_dir, _index_targets(root, relative_dir, indexed_files), existing)
        writes[readme_rel] = content.encode("utf-8")
    return writes


def check_archive_indexes(root: Path, *, relative_dirs: set[str] | None = None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    required: list[str] = []
    indexed: list[str] = []
    for relative_dir in INDEX_SPECS:
        if relative_dirs is not None and relative_dir not in relative_dirs:
            continue
        directory = root / relative_dir
        if not directory.is_dir():
            continue
        readme = directory / "README.md"
        readme_rel = readme.relative_to(root).as_posix()
        expected = _index_targets(root, relative_dir)
        if (
            relative_dir in {"docs/archive", "docs/archive/plans", "docs/archive/backlog"}
            and not expected
            and not readme.exists()
            and not readme.is_symlink()
        ):
            continue
        required.append(readme_rel)
        if not readme.is_file():
            errors.append({"code": "index_missing", "path": readme_rel, "detail": relative_dir})
            continue
        if readme.is_symlink():
            errors.append({"code": "index_unsafe", "path": readme_rel, "detail": "symbolic file"})
            continue
        text = _read(readme)
        if INDEX_START not in text or INDEX_END not in text:
            errors.append({"code": "index_unmanaged", "path": readme_rel, "detail": "managed marker block missing"})
        managed_match = re.search(
            re.escape(INDEX_START) + r"(?P<body>.*?)" + re.escape(INDEX_END),
            text,
            re.DOTALL,
        )
        links = _links(managed_match.group("body")) if managed_match else []
        for link in links:
            if "://" in link or link.startswith("#"):
                continue
            target = (directory / link).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                errors.append({"code": "index_link_escape", "path": readme_rel, "detail": link})
                continue
            if not target.exists():
                errors.append({"code": "index_link_missing", "path": readme_rel, "detail": link})
        for link in links:
            if "://" not in link and not link.startswith("#") and link not in expected:
                errors.append({"code": "index_orphan_entry", "path": readme_rel, "detail": link})
        for entry in expected:
            count = links.count(entry)
            if count != 1:
                code = "archive_orphan" if relative_dir.startswith("docs/archive/") else "index_entry_mismatch"
                errors.append({"code": code, "path": readme_rel, "detail": f"{entry}:{count}"})
            else:
                indexed.append(f"{relative_dir}/{entry}")
    return {"success": not errors, "required": required, "indexed": sorted(indexed), "errors": errors}


def check_plan_lifecycle(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[dict[str, str]] = []
    plans = root / "PLANS.md"
    if plans.exists():
        text = _read(plans)
        if "## Active Plan:" in text:
            for issue in validate_plan_schema(text, declared_external_sources=bool(re.search(r"https?://", text))):
                errors.append({"code": "plan_schema", "path": "PLANS.md", "detail": issue})
            for issue in closure_issues(text):
                errors.append({"code": "plan_state", "path": "PLANS.md", "detail": issue})
    archive_dir = root / "docs" / "archive" / "plans"
    if archive_dir.is_dir():
        for path in sorted(archive_dir.glob("*.md")):
            if path.name == "README.md":
                continue
            text = _read(path)
            if _plan_version(text) == PLAN_SCHEMA_VERSION:
                for issue in validate_plan_schema(text, declared_external_sources=bool(re.search(r"https?://", text))):
                    errors.append({"code": "archive_plan_schema", "path": path.relative_to(root).as_posix(), "detail": issue})
                for issue in closure_issues(text, require_ready=True, archived=True):
                    errors.append({"code": "archive_plan_state", "path": path.relative_to(root).as_posix(), "detail": issue})
    state_text = _read(root / "docs/codex/ENGINEERING_WORKFLOW_STATE.yaml")
    index_dirs = None
    if not re.search(r"(?m)^instruction_contract_version:\s*[12]\s*$", state_text):
        index_dirs = {"docs", "docs/archive", "docs/archive/plans", "docs/archive/backlog"}
    indexes = check_archive_indexes(root, relative_dirs=index_dirs)
    errors.extend(indexes["errors"])
    return {"success": not errors, "errors": errors, "archive_indexes": indexes}


def _safe_target(root: Path, relative: str) -> Path:
    normalized = Path(relative)
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise LifecycleError("unsafe_target_path", relative)
    target = root / normalized
    current = root
    for part in normalized.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise LifecycleError("unsafe_target_path", f"symbolic parent: {current}")
    if target.is_symlink():
        raise LifecycleError("unsafe_target_path", f"symbolic target: {target}")
    return target


def _replace_file(source: Path, target: Path) -> None:
    os.replace(source, target)


def apply_writes_atomically(
    root: Path,
    writes: dict[str, bytes],
    validate: Callable[[], None] | None = None,
) -> None:
    snapshots: dict[str, tuple[bytes | None, int | None]] = {}
    created_dirs: list[Path] = []
    applied: list[str] = []
    temp_paths: list[Path] = []
    try:
        for relative in sorted(writes):
            target = _safe_target(root, relative)
            parent = target.parent
            missing: list[Path] = []
            cursor = parent
            while cursor != root and not cursor.exists():
                missing.append(cursor)
                cursor = cursor.parent
            if cursor.is_symlink():
                raise LifecycleError("unsafe_target_path", f"symbolic parent: {cursor}")
            for directory in reversed(missing):
                directory.mkdir()
                created_dirs.append(directory)
            previous = target.read_bytes() if target.exists() else None
            mode = target.stat().st_mode & 0o777 if target.exists() else None
            snapshots[relative] = (previous, mode)
            with tempfile.NamedTemporaryFile(dir=parent, prefix=f".{target.name}.", delete=False) as handle:
                handle.write(writes[relative])
                handle.flush()
                os.fsync(handle.fileno())
                temp = Path(handle.name)
            temp_paths.append(temp)
            if mode is not None:
                temp.chmod(mode)
            _replace_file(temp, target)
            applied.append(relative)
        temp_paths.clear()
        if validate is not None:
            validate()
    except Exception:
        for temp in temp_paths:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        for relative in reversed(applied):
            target = _safe_target(root, relative)
            previous, mode = snapshots[relative]
            if previous is None:
                target.unlink(missing_ok=True)
                continue
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.restore.", delete=False) as handle:
                handle.write(previous)
                restore = Path(handle.name)
            if mode is not None:
                restore.chmod(mode)
            os.replace(restore, target)
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise


def _title(text: str) -> str:
    match = re.search(r"(?m)^## Active Plan:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else "completed-plan"


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:80] or "completed-plan"


def _compact_root(existing: str, title: str, archive_path: str | None) -> str:
    completed_match = re.search(r"(?ms)^## Recently Completed\s*$\n(?P<body>.*)\Z", existing)
    old_entries = []
    if completed_match:
        old_entries = [line for line in completed_match.group("body").splitlines() if re.match(r"^- \[x\]", line, re.IGNORECASE)]
    suffix = f"; [full archived plan]({archive_path})" if archive_path else ""
    new_entry = f"- [x] {date.today().isoformat()}: Completed {title}{suffix}."
    entries = [new_entry, *[item for item in old_entries if item != new_entry]][:10]
    return (
        "# Execution Plans\n\n"
        f"plan_schema_version: {PLAN_SCHEMA_VERSION}\n\n"
        "Use this file for active, blocked, ready-for-closure, or recently completed execution work. "
        "The canonical lifecycle is the installed `engineering-workflow` planning reference.\n\n"
        "## Recently Completed\n\n"
        + "\n".join(entries)
        + "\n"
    )


def close_plan(root: Path, disposition: str) -> dict[str, Any]:
    root = root.resolve()
    plans_path = root / "PLANS.md"
    text = _read(plans_path)
    if not text or "## Active Plan:" not in text:
        raise LifecycleError("active_plan_missing", "PLANS.md has no active plan")
    structural = validate_plan_schema(text, declared_external_sources=bool(re.search(r"https?://", text)), require_fidelity_passed=True)
    closing = closure_issues(text, require_ready=True)
    if structural or closing:
        raise LifecycleError("closure_gate_failed", "; ".join([*structural, *closing]))
    title = _title(text)
    archive_relative: str | None = None
    writes: dict[str, bytes] = {}
    extra_files: set[str] = set()
    if disposition == "archive":
        archive_relative = f"docs/archive/plans/{date.today().isoformat()}-{_slugify(title)}.md"
        if (root / archive_relative).exists():
            raise LifecycleError("archive_exists", archive_relative)
        archived = re.sub(r"(?m)^Status:\s*ready_for_closure\s*$", "Status: done", text, count=1)
        writes[archive_relative] = archived.encode("utf-8")
        extra_files.add(archive_relative)
    writes["PLANS.md"] = _compact_root(text, title, archive_relative).encode("utf-8")
    if disposition == "archive":
        writes.update(
            planned_index_writes(
                root,
                extra_files=extra_files,
                relative_dirs={"docs", "docs/archive", "docs/archive/plans"},
            )
        )
    result: dict[str, Any] = {}

    def validate_closed_state() -> None:
        nonlocal result
        result = check_plan_lifecycle(root)
        if not result["success"]:
            raise LifecycleError("post_close_validation_failed", json.dumps(result["errors"], sort_keys=True))

    apply_writes_atomically(root, writes, validate=validate_closed_state)
    return {
        "success": True,
        "status": "done",
        "disposition": disposition,
        "archive_path": archive_relative,
        "changed_paths": sorted(writes),
        "archive_indexes": result["archive_indexes"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or close an engineering-workflow execution plan.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--repo-root", default=".")
    check.add_argument("--format", choices=("human", "json"), default="human")
    close = subparsers.add_parser("close")
    close.add_argument("--repo-root", default=".")
    close.add_argument("--disposition", choices=("compact", "archive"), required=True)
    close.add_argument("--format", choices=("human", "json"), default="human")
    args = parser.parse_args()
    try:
        if args.command == "check":
            result = check_plan_lifecycle(Path(args.repo_root))
        else:
            result = close_plan(Path(args.repo_root), args.disposition)
    except LifecycleError as exc:
        result = {"success": False, "errors": [{"code": exc.code, "message": str(exc)}]}
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"plan-lifecycle: {'ok' if result.get('success') else 'failed'}")
        for issue in result.get("errors", []):
            print(f"error: {issue.get('code')}: {issue.get('detail', issue.get('message', ''))}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
