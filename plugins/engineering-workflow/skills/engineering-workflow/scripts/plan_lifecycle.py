#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable, NamedTuple

from common import (
    INDEX_MARKER_END,
    INDEX_MARKER_START,
    PLAN_SCHEMA_VERSION,
    _section_text,
    parse_manifest_path_list,
    parse_manifest_path_scalar,
    validate_plan_schema,
)

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
STATE_MANIFEST_PATH = "docs/codex/ENGINEERING_WORKFLOW_STATE.yaml"
DEFAULT_ARCHIVE_PATH = "docs/archive/plans"
DEFAULT_ARCHIVE_INDEXES = (
    "docs/archive/plans/README.md",
    "docs/archive/README.md",
    "docs/README.md",
)


class LifecycleError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ArchiveLayout(NamedTuple):
    archive_path: str
    indexes: tuple[str, ...]
    explicit: bool
    state_path: str | None
    active_plan: str | None
    managed_paths: frozenset[str]


def _read(path: Path) -> str:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def resolve_archive_layout(root: Path) -> ArchiveLayout:
    root = root.resolve()
    state = root / STATE_MANIFEST_PATH
    if not state.exists() and not state.is_symlink():
        return ArchiveLayout(
            archive_path=DEFAULT_ARCHIVE_PATH,
            indexes=DEFAULT_ARCHIVE_INDEXES,
            explicit=False,
            state_path=None,
            active_plan=None,
            managed_paths=frozenset(),
        )
    try:
        _safe_target(root, STATE_MANIFEST_PATH)
    except LifecycleError as exc:
        raise LifecycleError("archive_state_unsafe", str(exc)) from exc
    if not state.is_file():
        raise LifecycleError("archive_state_invalid", f"{STATE_MANIFEST_PATH} is not a regular file")
    text = _read(state)
    if not text:
        raise LifecycleError("archive_state_invalid", f"Cannot read {STATE_MANIFEST_PATH}")
    try:
        archive_present, archive_path = parse_manifest_path_scalar(text, "plan_archive_path")
        indexes_present, indexes = parse_manifest_path_list(text, "plan_archive_indexes")
        active_present, active_plan = parse_manifest_path_scalar(text, "active_plan", allow_null=True)
        managed_present, managed_paths = parse_manifest_path_list(text, "managed_paths")
    except ValueError as exc:
        raise LifecycleError("archive_state_invalid", str(exc)) from exc
    explicit_fields = (archive_present, indexes_present, active_present)
    if not any(explicit_fields):
        return ArchiveLayout(
            archive_path=DEFAULT_ARCHIVE_PATH,
            indexes=DEFAULT_ARCHIVE_INDEXES,
            explicit=False,
            state_path=None,
            active_plan=None,
            managed_paths=frozenset(managed_paths if managed_present else ()),
        )
    if not all(explicit_fields):
        raise LifecycleError(
            "archive_ownership_ambiguous",
            "plan_archive_path, plan_archive_indexes, and active_plan must be declared together",
        )
    if archive_path is None or not indexes:
        raise LifecycleError("archive_ownership_ambiguous", "Explicit archive path and index graph must be non-empty")
    if len(set(indexes)) != len(indexes):
        raise LifecycleError("archive_ownership_ambiguous", "plan_archive_indexes contains duplicate paths")
    if archive_path in indexes or STATE_MANIFEST_PATH in indexes or "PLANS.md" in indexes:
        raise LifecycleError("archive_ownership_ambiguous", "Archive and workflow-state paths must be distinct")
    for relative in (archive_path, *indexes):
        try:
            _safe_target(root, relative)
        except LifecycleError as exc:
            raise LifecycleError("archive_ownership_unsafe", str(exc)) from exc
    managed = frozenset(managed_paths if managed_present else ())
    for relative in indexes:
        target = root / relative
        if not target.exists() and relative not in managed:
            raise LifecycleError(
                "archive_index_ownership_missing",
                f"Missing explicit index is not listed in managed_paths: {relative}",
            )
    if active_plan not in {None, "PLANS.md"}:
        raise LifecycleError("archive_active_plan_mismatch", f"Unsupported active_plan: {active_plan}")
    return ArchiveLayout(
        archive_path=archive_path,
        indexes=tuple(indexes),
        explicit=True,
        state_path=STATE_MANIFEST_PATH,
        active_plan=active_plan,
        managed_paths=managed,
    )


def _active_plan_state_errors(layout: ArchiveLayout, *, has_active_plan: bool) -> list[dict[str, str]]:
    if not layout.explicit:
        return []
    expected = "PLANS.md" if has_active_plan else None
    if layout.active_plan == expected:
        return []
    detail = "PLANS.md" if expected else "null"
    return [
        {
            "code": "active_plan_state_mismatch",
            "path": layout.state_path or STATE_MANIFEST_PATH,
            "detail": f"expected {detail}",
        }
    ]


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
        if not re.search(
            r"\b(?:no|none|nothing|completed|outside|out of scope|not applicable)\b", handoff, re.IGNORECASE
        ):
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
            if (
                path.is_file()
                and not path.is_symlink()
                and path.name != "README.md"
                and path.suffix.lower() in {".md", ".rst", ".txt"}
            ):
                entries.add(path.name)
    prefix = relative_dir.rstrip("/") + "/"
    for item in extra_files:
        if item.startswith(prefix):
            remainder = item[len(prefix) :]
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
            raise LifecycleError(
                "unmanaged_index_conflict", f"Existing {relative_dir}/README.md has no managed index markers"
            )
        return (
            re.sub(
                re.escape(INDEX_START) + r".*?" + re.escape(INDEX_END),
                f"{INDEX_START}\n{managed}\n{INDEX_END}",
                existing,
                count=1,
                flags=re.DOTALL,
            ).rstrip()
            + "\n"
        )
    template = _read(INDEX_TEMPLATE_ROOT / INDEX_SPECS[relative_dir])
    if not template:
        raise LifecycleError("index_template_missing", f"Missing index template for {relative_dir}")
    return template.replace("{{ entries }}", managed).rstrip() + "\n"


def _relative_link(index_path: str, target_path: str) -> str:
    start = Path(index_path).parent.as_posix() or "."
    return os.path.relpath(target_path, start=start).replace(os.sep, "/")


def _replace_managed_block(existing: str, managed: str, *, title: str) -> str:
    if existing:
        if INDEX_START not in existing or INDEX_END not in existing:
            raise LifecycleError("unmanaged_index_conflict", "Existing declared index has no managed index markers")
        return (
            re.sub(
                re.escape(INDEX_START) + r".*?" + re.escape(INDEX_END),
                f"{INDEX_START}\n{managed}\n{INDEX_END}",
                existing,
                count=1,
                flags=re.DOTALL,
            ).rstrip()
            + "\n"
        )
    return f"# {title}\n\n{INDEX_START}\n{managed}\n{INDEX_END}\n"


def _archive_entry_paths(root: Path, layout: ArchiveLayout, extra_files: set[str] | None = None) -> list[str]:
    extra_files = extra_files or set()
    entries: set[str] = set()
    directory = root / layout.archive_path
    if directory.is_dir() and not directory.is_symlink():
        for path in directory.iterdir():
            relative = path.relative_to(root).as_posix()
            if (
                path.is_file()
                and not path.is_symlink()
                and relative not in layout.indexes
                and path.suffix.lower() in {".md", ".rst", ".txt"}
            ):
                entries.add(relative)
    prefix = layout.archive_path.rstrip("/") + "/"
    for relative in extra_files:
        if relative.startswith(prefix) and "/" not in relative[len(prefix) :] and relative not in layout.indexes:
            entries.add(relative)
    return sorted(entries)


def _managed_body(text: str) -> str | None:
    match = re.search(
        re.escape(INDEX_START) + r"(?P<body>.*?)" + re.escape(INDEX_END),
        text,
        re.DOTALL,
    )
    return match.group("body").strip() if match else None


def _resolved_managed_links(root: Path, index_path: str, text: str) -> list[tuple[str, str]]:
    body = _managed_body(text)
    if body is None:
        return []
    resolved: list[tuple[str, str]] = []
    base = root / Path(index_path).parent
    for link in _links(body):
        if "://" in link or link.startswith("#"):
            continue
        target = (base / link).resolve()
        try:
            relative = target.relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = ""
        resolved.append((link, relative))
    return resolved


def planned_explicit_index_writes(
    root: Path,
    layout: ArchiveLayout,
    *,
    extra_files: set[str] | None = None,
) -> dict[str, bytes]:
    if not layout.explicit:
        raise LifecycleError("archive_ownership_ambiguous", "Explicit index planning requires an explicit layout")
    archive_entries = _archive_entry_paths(root, layout, extra_files)
    leaf = layout.indexes[0]
    leaf_existing = _read(root / leaf) if (root / leaf).exists() else ""
    leaf_lines = [f"- [{Path(relative).name}]({_relative_link(leaf, relative)})" for relative in archive_entries]
    writes = {
        leaf: _replace_managed_block(
            leaf_existing,
            "\n".join(leaf_lines) if leaf_lines else "No indexed documents yet.",
            title="Archived Plans",
        ).encode("utf-8")
    }
    child = leaf
    for parent in layout.indexes[1:]:
        existing = _read(root / parent) if (root / parent).exists() else ""
        body = _managed_body(existing)
        if existing and body is None:
            raise LifecycleError("unmanaged_index_conflict", f"Existing {parent} has no managed index markers")
        child_link = _relative_link(parent, child)
        matching = [link for link, resolved in _resolved_managed_links(root, parent, existing) if resolved == child]
        if len(matching) > 1:
            raise LifecycleError("archive_index_conflict", f"{parent} links {child} more than once")
        lines = [] if body == "No indexed documents yet." else (body.splitlines() if body else [])
        if not matching:
            lines.append(f"- [{Path(child).name}]({child_link})")
        managed = "\n".join(line for line in lines if line.strip()) or "No indexed documents yet."
        writes[parent] = _replace_managed_block(existing, managed, title="Documentation").encode("utf-8")
        child = parent
    return writes


def check_explicit_archive_graph(root: Path, layout: ArchiveLayout) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    entries = _archive_entry_paths(root, layout)
    leaf = layout.indexes[0]
    graph_exists = bool(entries) or (root / leaf).exists() or (root / leaf).is_symlink()
    child = leaf
    for parent in layout.indexes[1:]:
        target = root / parent
        if target.exists() or target.is_symlink():
            text = _read(target)
            body = _managed_body(text)
            if body is None or any(resolved == child for _, resolved in _resolved_managed_links(root, parent, text)):
                graph_exists = True
        child = parent
    if not graph_exists:
        return {"success": True, "required": [], "indexed": [], "errors": []}
    required = list(layout.indexes)
    indexed: list[str] = []
    for index_path in layout.indexes:
        target = root / index_path
        if not target.is_file():
            errors.append({"code": "index_missing", "path": index_path, "detail": layout.archive_path})
            continue
        if target.is_symlink():
            errors.append({"code": "index_unsafe", "path": index_path, "detail": "symbolic file"})
            continue
        text = _read(target)
        body = _managed_body(text)
        if body is None:
            errors.append({"code": "index_unmanaged", "path": index_path, "detail": "managed marker block missing"})
            continue
        for link, resolved in _resolved_managed_links(root, index_path, text):
            if not resolved:
                errors.append({"code": "index_link_escape", "path": index_path, "detail": link})
            elif not (root / resolved).exists():
                errors.append({"code": "index_link_missing", "path": index_path, "detail": link})
    leaf_text = _read(root / leaf)
    leaf_links = [resolved for _, resolved in _resolved_managed_links(root, leaf, leaf_text) if resolved]
    for relative in entries:
        count = leaf_links.count(relative)
        if count != 1:
            errors.append({"code": "archive_orphan", "path": leaf, "detail": f"{relative}:{count}"})
        else:
            indexed.append(relative)
    for relative in leaf_links:
        if relative not in entries:
            errors.append({"code": "index_orphan_entry", "path": leaf, "detail": relative})
    child = leaf
    for parent in layout.indexes[1:]:
        parent_text = _read(root / parent)
        links = [resolved for _, resolved in _resolved_managed_links(root, parent, parent_text) if resolved]
        count = links.count(child)
        if count != 1:
            errors.append({"code": "index_entry_mismatch", "path": parent, "detail": f"{child}:{count}"})
        child = parent
    return {"success": not errors, "required": required, "indexed": sorted(indexed), "errors": errors}


def _clear_active_plan(text: str) -> str:
    updated, count = re.subn(r"(?m)^active_plan:\s*[^#\n]*?(?:\s+#.*)?$", "active_plan: null", text, count=1)
    if count != 1:
        raise LifecycleError("archive_state_invalid", "active_plan is missing from explicit workflow state")
    return updated.rstrip() + "\n"


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


def check_archive_indexes(
    root: Path,
    *,
    relative_dirs: set[str] | None = None,
    allowed_extra_entries: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    allowed_extra_entries = allowed_extra_entries or {}
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
        allowed = allowed_extra_entries.get(relative_dir, set())
        for link in links:
            if "://" not in link and not link.startswith("#") and link not in expected and link not in allowed:
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
    has_active_plan = False
    if plans.exists():
        text = _read(plans)
        has_active_plan = "## Active Plan:" in text
        if has_active_plan:
            for issue in validate_plan_schema(text, declared_external_sources=bool(re.search(r"https?://", text))):
                errors.append({"code": "plan_schema", "path": "PLANS.md", "detail": issue})
            for issue in closure_issues(text):
                errors.append({"code": "plan_state", "path": "PLANS.md", "detail": issue})
    layout: ArchiveLayout | None = None
    try:
        layout = resolve_archive_layout(root)
    except LifecycleError as exc:
        errors.append({"code": exc.code, "path": STATE_MANIFEST_PATH, "detail": str(exc)})
    if layout is not None:
        errors.extend(_active_plan_state_errors(layout, has_active_plan=has_active_plan))
    archive_paths = {DEFAULT_ARCHIVE_PATH}
    if layout is not None:
        archive_paths.add(layout.archive_path)
    graph_indexes = set(layout.indexes) if layout is not None else set()
    for archive_relative in sorted(archive_paths):
        archive_dir = root / archive_relative
        if not archive_dir.is_dir() or archive_dir.is_symlink():
            continue
        for path in sorted(archive_dir.glob("*.md")):
            relative = path.relative_to(root).as_posix()
            if relative in graph_indexes or path.name == "README.md":
                continue
            text = _read(path)
            if _plan_version(text) == PLAN_SCHEMA_VERSION:
                for issue in validate_plan_schema(text, declared_external_sources=bool(re.search(r"https?://", text))):
                    errors.append({"code": "archive_plan_schema", "path": relative, "detail": issue})
                for issue in closure_issues(text, require_ready=True, archived=True):
                    errors.append({"code": "archive_plan_state", "path": relative, "detail": issue})
    state_text = _read(root / STATE_MANIFEST_PATH)
    agents_text = _read(root / "AGENTS.md")
    index_dirs = None
    managed_instruction_topology = bool(
        re.search(r"(?m)^instruction_contract_version:\s*[123]\s*$", state_text)
        or re.search(r"(?m)^instruction_contract_version:\s*[123]\s*$", agents_text)
    )
    if not managed_instruction_topology:
        index_dirs = {"docs", "docs/archive", "docs/archive/plans", "docs/archive/backlog"}
    allowed_extra_entries: dict[str, set[str]] = {}
    if layout is not None and layout.explicit:
        child = layout.indexes[0]
        for parent in layout.indexes[1:]:
            parent_path = Path(parent)
            relative_dir = parent_path.parent.as_posix()
            if parent_path.name == "README.md" and relative_dir in INDEX_SPECS:
                allowed = allowed_extra_entries.setdefault(relative_dir, set())
                allowed.add(_relative_link(parent, child))
                for link, resolved in _resolved_managed_links(root, parent, _read(root / parent)):
                    if resolved == child:
                        allowed.add(link)
            child = parent
    canonical_indexes = check_archive_indexes(
        root,
        relative_dirs=index_dirs,
        allowed_extra_entries=allowed_extra_entries,
    )
    explicit_indexes = (
        check_explicit_archive_graph(root, layout)
        if layout is not None and layout.explicit
        else {"success": True, "required": [], "indexed": [], "errors": []}
    )
    errors.extend(canonical_indexes["errors"])
    errors.extend(explicit_indexes["errors"])
    indexes = {
        "success": canonical_indexes["success"] and explicit_indexes["success"],
        "required": sorted(set(canonical_indexes["required"] + explicit_indexes["required"])),
        "indexed": sorted(set(canonical_indexes["indexed"] + explicit_indexes["indexed"])),
        "errors": [*canonical_indexes["errors"], *explicit_indexes["errors"]],
    }
    layout_result = None
    if layout is not None:
        layout_result = {
            "archive_path": layout.archive_path,
            "indexes": list(layout.indexes),
            "explicit": layout.explicit,
            "active_plan": layout.active_plan,
        }
    return {"success": not errors, "errors": errors, "archive_indexes": indexes, "archive_layout": layout_result}


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
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=f".{target.name}.restore.", delete=False
            ) as handle:
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
        old_entries = [
            line for line in completed_match.group("body").splitlines() if re.match(r"^- \[x\]", line, re.IGNORECASE)
        ]
    suffix = f"; [full archived plan]({archive_path})" if archive_path else ""
    new_entry = f"- [x] {date.today().isoformat()}: Completed {title}{suffix}."
    entries = [new_entry, *[item for item in old_entries if item != new_entry]][:10]
    return (
        "# Execution Plans\n\n"
        f"plan_schema_version: {PLAN_SCHEMA_VERSION}\n\n"
        "Use this file for active, blocked, ready-for-closure, or recently completed execution work. "
        "The canonical lifecycle is the installed `engineering-workflow` planning reference.\n\n"
        "## Recently Completed\n\n" + "\n".join(entries) + "\n"
    )


def close_plan(root: Path, disposition: str) -> dict[str, Any]:
    root = root.resolve()
    plans_path = root / "PLANS.md"
    text = _read(plans_path)
    if not text or "## Active Plan:" not in text:
        raise LifecycleError("active_plan_missing", "PLANS.md has no active plan")
    structural = validate_plan_schema(
        text, declared_external_sources=bool(re.search(r"https?://", text)), require_fidelity_passed=True
    )
    closing = closure_issues(text, require_ready=True)
    if structural or closing:
        raise LifecycleError("closure_gate_failed", "; ".join([*structural, *closing]))
    layout = resolve_archive_layout(root)
    state_errors = _active_plan_state_errors(layout, has_active_plan=True)
    if state_errors:
        raise LifecycleError("archive_active_plan_mismatch", state_errors[0]["detail"])
    title = _title(text)
    archive_relative: str | None = None
    writes: dict[str, bytes] = {}
    extra_files: set[str] = set()
    default_archive_root_existed = (root / "docs/archive").exists() or (root / "docs/archive").is_symlink()
    if disposition == "archive":
        archive_relative = f"{layout.archive_path}/{date.today().isoformat()}-{_slugify(title)}.md"
        if (root / archive_relative).exists():
            raise LifecycleError("archive_exists", archive_relative)
        archived = re.sub(r"(?m)^Status:\s*ready_for_closure\s*$", "Status: done", text, count=1)
        writes[archive_relative] = archived.encode("utf-8")
        extra_files.add(archive_relative)
    writes["PLANS.md"] = _compact_root(text, title, archive_relative).encode("utf-8")
    if disposition == "archive":
        if layout.explicit:
            writes.update(planned_explicit_index_writes(root, layout, extra_files=extra_files))
        else:
            writes.update(
                planned_index_writes(
                    root,
                    extra_files=extra_files,
                    relative_dirs={"docs", "docs/archive", "docs/archive/plans"},
                )
            )
    if layout.explicit:
        state_text = _read(root / (layout.state_path or STATE_MANIFEST_PATH))
        writes[layout.state_path or STATE_MANIFEST_PATH] = _clear_active_plan(state_text).encode("utf-8")
    result: dict[str, Any] = {}

    def validate_closed_state() -> None:
        nonlocal result
        result = check_plan_lifecycle(root)
        if not result["success"]:
            raise LifecycleError("post_close_validation_failed", json.dumps(result["errors"], sort_keys=True))
        if (
            layout.explicit
            and layout.archive_path != DEFAULT_ARCHIVE_PATH
            and not default_archive_root_existed
            and ((root / "docs/archive").exists() or (root / "docs/archive").is_symlink())
        ):
            raise LifecycleError("competing_archive_created", "Custom archive closure created docs/archive")

    apply_writes_atomically(root, writes, validate=validate_closed_state)
    return {
        "success": True,
        "status": "done",
        "disposition": disposition,
        "archive_path": archive_relative,
        "changed_paths": sorted(writes),
        "archive_indexes": result["archive_indexes"],
        "archive_layout": result.get("archive_layout"),
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
